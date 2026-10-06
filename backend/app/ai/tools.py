"""Tools read-only Fase 1 — AI hanya boleh BACA via fungsi ini.

Prinsip:
- Tidak ada INSERT/UPDATE/DELETE di file ini (SELECT only).
- Semua query wajib filter store_id (multi-toko).
- Role teknisi: TIDAK boleh lihat omzet/laba, hanya kerjaannya sendiri.
"""
import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .. import crud, models
from ..store_ctx import is_own_or_free, teknisi_scope_names


def _rp(n) -> str:
    try:
        return f"Rp {int(n or 0):,}".replace(",", ".")
    except Exception:
        return "Rp 0"


def detect_intent(q: str) -> List[str]:
    """Keyword matching Indonesia -> list intent. Bisa multi (mis. 'omset dan stok')."""
    t = (q or "").lower()
    intents: set = set()
    if any(k in t for k in ["omset", "omzet", "pendapatan", "laba", "untung", "kas", "uang", "pemasukan", "pengeluaran"]):
        intents.add("omset")
    if any(k in t for k in ["teknisi", "montir", "kerja", "komisi", " performa"]):
        intents.add("teknisi")
    if any(k in t for k in ["stok", "stock", "sparepart", "part", "habis", "menipis", "kosong", "sisa barang"]):
        intents.add("stok")
    if any(k in t for k in ["telat", "overdue", "deadline", "tempo", "jatuh", "garansi", "antri", "status", "proses", "selesai", "diambil"]):
        intents.add("status")
    if not intents:
        intents = {"overview"}
    return sorted(intents)


def _is_teknisi(role: Optional[str]) -> bool:
    return (role or "").lower() == "teknisi"


def get_overview(db: Session, store_id: Optional[int], role: Optional[str], current) -> Dict[str, Any]:
    s = crud.get_stats(db, store_id=store_id)
    out: Dict[str, Any] = {
        "total_masuk": s.get("total_masuk", 0),
        "dalam_proses": s.get("dalam_proses", 0),
        "antri": s.get("antri", 0),
        "dikerjakan": s.get("dikerjakan", 0),
        "menunggu_sparepart": s.get("menunggu_sparepart", 0),
        "selesai": s.get("selesai", 0),
        "overdue": s.get("overdue", 0),
        "deadline_hari_ini": s.get("deadline_hari_ini", 0),
    }
    # teknisi tidak boleh lihat estimasi pendapatan
    if not _is_teknisi(role):
        out["estimasi_pendapatan"] = s.get("estimasi_pendapatan", 0)
    return out


def get_omset(db: Session, store_id: Optional[int]) -> Dict[str, Any]:
    """Ringkasan uang: ledger (omzet/HPP/laba) + sales hari & bulan ini."""
    today = datetime.date.today()
    iso, ym = today.isoformat(), today.strftime("%Y-%m")
    # --- ledger (all-time per toko, prinsip mentor disederhanakan) ---
    q = db.query(models.LedgerEntry)
    if store_id is not None:
        q = q.filter(models.LedgerEntry.store_id == store_id)
    rows = q.all()
    omzet = hpp = operasional = 0
    for e in rows:
        try:
            from .. import ledger_meta as lm
            kel = lm.kelompok_of(e.kategori or "")
        except Exception:
            kel = ""
        n = int(e.nominal or 0)
        laba = e.masuk_laba is not False
        if (e.jenis or "") == "transfer":
            continue
        if (e.jenis or "") == "masuk" and laba and kel == "omzet":
            omzet += n
        elif (e.jenis or "") == "keluar" and laba and kel == "hpp":
            hpp += n
        elif (e.jenis or "") == "keluar" and laba and kel == "operasional":
            operasional += n
        elif (e.jenis or "") == "keluar" and laba and kel == "omzet":
            omzet -= n  # refund pengurang omzet
    # --- sales ---
    sq = db.query(models.Sale)
    if store_id is not None:
        sq = sq.filter(models.Sale.store_id == store_id)
    sales = sq.all()
    hari = [x for x in sales if str(x.tanggal or "") == iso]
    bln = [x for x in sales if str(x.tanggal or "")[:7] == ym]
    # --- service hari ini (estimasi, bukan kas) ---
    svc_q = db.query(models.Service)
    if store_id is not None:
        svc_q = svc_q.filter(models.Service.store_id == store_id)
    svc_hari = svc_q.filter(models.Service.date == today).all()
    return {
        "omzet_ledger": omzet,
        "hpp": hpp,
        "laba_kotor": omzet - hpp,
        "operasional": operasional,
        "laba_bersih": omzet - hpp - operasional,
        "penjualan_hari_ini": len(hari),
        "omzet_penjualan_hari_ini": sum(int(x.total or 0) for x in hari),
        "penjualan_bulan_ini": len(bln),
        "omzet_penjualan_bulan_ini": sum(int(x.total or 0) for x in bln),
        "service_masuk_hari_ini": len(svc_hari),
        "estimasi_service_hari_ini": sum(int(x.biaya or 0) for x in svc_hari),
    }


def get_teknisi_perf(db: Session, store_id: Optional[int], role: Optional[str], current) -> List[Dict[str, Any]]:
    tq = db.query(models.Technician).filter(models.Technician.is_active == 1)
    if store_id is not None:
        tq = tq.filter(models.Technician.store_id == store_id)
    techs = tq.all()
    # teknisi hanya lihat dirinya sendiri
    if _is_teknisi(role):
        names = teknisi_scope_names(current)
        techs = [t for t in techs if (t.nama or "") in names]
    out = []
    for t in techs:
        sq = db.query(models.Service).filter(models.Service.technician_id == t.id)
        if store_id is not None:
            sq = sq.filter(models.Service.store_id == store_id)
        total = sq.count()
        selesai = sq.filter(models.Service.status.in_(["Selesai", "Service Sukses", "Sudah Diambil"])).count()
        proses = sq.filter(models.Service.status.in_(["Antri", "Dikerjakan", "Menunggu Sparepart"])).count()
        out.append({
            "nama": t.nama, "level": t.level or "junior",
            "total": total, "selesai": selesai, "proses": proses,
            "persen": round(selesai / total * 100) if total else 0,
        })
    return sorted(out, key=lambda x: -x["total"])[:10]


def get_stok_menipis(db: Session, store_id: Optional[int], batas: int = 5) -> List[Dict[str, Any]]:
    q = db.query(models.Sparepart).filter(models.Sparepart.stok <= batas)
    if store_id is not None:
        q = q.filter(models.Sparepart.store_id == store_id)
    rows = q.order_by(models.Sparepart.stok.asc()).limit(20).all()
    return [{"nama": r.nama, "merk": r.merk, "stok": int(r.stok or 0),
             "harga_jual": int(r.harga or 0)} for r in rows]


def get_status(db: Session, store_id: Optional[int], role: Optional[str], current) -> Dict[str, Any]:
    sq = db.query(models.Service)
    if store_id is not None:
        sq = sq.filter(models.Service.store_id == store_id)
    names = teknisi_scope_names(current) if _is_teknisi(role) else None
    if names is not None:
        from sqlalchemy import or_ as _or
        from ..store_ctx import UNASSIGNED_TEKNISI
        sq = sq.filter(_or(
            models.Service.teknisi.in_(list(names)),
            models.Service.teknisi.is_(None),
            models.Service.teknisi.in_(list(UNASSIGNED_TEKNISI)),
        ))
    today = datetime.date.today()
    by_status = dict(sq.with_entities(models.Service.status, func.count(models.Service.invoice)).group_by(models.Service.status).all())
    overdue_q = sq.filter(models.Service.deadline != None).filter(
        models.Service.deadline < today).filter(
        models.Service.status.notin_(list(crud.TERMINAL_STATUSES)))
    overdue = overdue_q.order_by(models.Service.deadline.asc()).limit(10).all()
    today_q = sq.filter(models.Service.deadline == today).limit(10).all()
    return {
        "by_status": by_status,
        "overdue_count": overdue_q.count(),
        "overdue": [{"invoice": s.invoice, "nama": s.nama, "device": s.device,
                     "teknisi": s.teknisi, "deadline": str(s.deadline or ""),
                     "status": s.status} for s in overdue],
        "deadline_hari_ini": [{"invoice": s.invoice, "nama": s.nama, "device": s.device,
                               "teknisi": s.teknisi, "status": s.status} for s in today_q],
    }


def gather(db: Session, intents: List[str], store_id: Optional[int], role: Optional[str], current) -> Dict[str, Any]:
    """Kumpulkan konteks read-only sesuai intent. Teknisi: omzet dikunci."""
    data: Dict[str, Any] = {"intents": intents}
    want_all = "overview" in intents
    if want_all or "status" in intents:
        data["overview"] = get_overview(db, store_id, role, current)
    if "omset" in intents or want_all:
        if _is_teknisi(role):
            data["omset"] = {"locked": True, "pesan": "Hanya owner/admin/kasir yang boleh lihat omzet."}
        else:
            data["omset"] = get_omset(db, store_id)
    if "teknisi" in intents or want_all:
        data["teknisi"] = get_teknisi_perf(db, store_id, role, current)
    if "stok" in intents or want_all:
        data["stok_menipis"] = get_stok_menipis(db, store_id)
    if "status" in intents or want_all:
        data["status"] = get_status(db, store_id, role, current)
    return data


def fallback_answer(data: Dict[str, Any], role: Optional[str]) -> str:
    """Ringkasan tanpa LLM (Ollama mati) — tetap rapi, angka sama."""
    L = []
    if "overview" in data:
        o = data["overview"]
        L.append(f"📊 Service: {o.get('total_masuk',0)} masuk, {o.get('dalam_proses',0)} proses "
                 f"(antri {o.get('antri',0)} / dikerjakan {o.get('dikerjakan',0)} / sparepart {o.get('menunggu_sparepart',0)}), "
                 f"selesai {o.get('selesai',0)}, telat {o.get('overdue',0)}.")
    if isinstance(data.get("omset"), dict) and not data["omset"].get("locked"):
        m = data["omset"]
        L.append(f"💰 Omzet ledger {_rp(m.get('omzet_ledger'))}, laba kotor {_rp(m.get('laba_kotor'))}, "
                 f"bersih {_rp(m.get('laba_bersih'))}. Penjualan hari ini {m.get('penjualan_hari_ini',0)} struk "
                 f"({_rp(m.get('omzet_penjualan_hari_ini'))}), bulan ini {_rp(m.get('omzet_penjualan_bulan_ini'))}.")
    elif isinstance(data.get("omset"), dict) and data["omset"].get("locked"):
        L.append("💰 Omzet dikunci untuk akun teknisi.")
    if isinstance(data.get("teknisi"), list) and data["teknisi"]:
        top = data["teknisi"][:3]
        L.append("🔧 Teknisi: " + ", ".join(f"{t['nama']} ({t['selesai']}/{t['total']})" for t in top) + ".")
    if isinstance(data.get("stok_menipis"), list):
        st = data["stok_menipis"]
        if st:
            L.append("📦 Stok menipis: " + ", ".join(f"{s['nama']} (sisa {s['stok']})" for s in st[:5]) + ".")
        else:
            L.append("📦 Stok aman, tidak ada yang ≤5.")
    if isinstance(data.get("status"), dict):
        s = data["status"]
        L.append(f"⏰ Telat: {s.get('overdue_count',0)}, deadline hari ini {len(s.get('deadline_hari_ini',[]))}.")
        if s.get("overdue"):
            first = s["overdue"][0]
            L.append(f"Contoh telat: {first['invoice']} {first['device']} ({first['nama']}, {first['teknisi']}).")
    return "\n".join(L) if L else "Belum ada data untuk pertanyaan itu."
