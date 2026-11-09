"""Keuangan ekstraf: Kecelakaan Kerja + Refund Dana (Owner Space)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
import datetime
import json
import re

from ..database import get_db
from .. import models
from .. import crud
from ..audit import log_action
from ..store_ctx import resolve_store, store_role, default_store
from .. import engine_logic as el
from .. import ledger_meta as lm
from .auth import get_current_user

router = APIRouter(prefix="/finance", tags=["Finance"])

JENIS_ACC = ["part_rusak", "komponen_pelanggan", "catatan"]
SUMBER = ["persediaan", "beli_luar"]
SAPA_BAYAR = ["toko", "pelanggan"]
METODE = ["Tunai", "Transfer", "QRIS"]
KAT_EXPENSE = ["Sewa", "Listrik", "Internet", "Gaji", "Belanja Part", "Operasional", "Lainnya"]


def _ctx(db, current, store_id, need_role=True):
    """Resolve toko + pastikan role. Owner/admin/superadmin."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if store is None:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    role = store_role(db, current, store)
    if need_role and role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh buka modul ini")
    return store, role


def _ctx_write(db, current, store_id):
    """Tulis pengeluaran: owner/admin/kasir/superadmin.
    Kasir boleh catat operasional harian (listrik/wifi/belanja) langsung dari Kas Toko.
    Hapus tetap owner/admin (lihat delete_expense)."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if store is None:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin", "kasir"]:
        raise HTTPException(status_code=403, detail="Hanya tim toko yang boleh catat pengeluaran")
    return store, role


def _find_tech(db, store_id, payload):
    if payload.get("technician_id"):
        return db.query(models.Technician).filter(
            models.Technician.id == int(payload["technician_id"]),
            models.Technician.store_id == store_id).first()
    nama = (payload.get("teknisi") or "").strip()
    if nama:
        return db.query(models.Technician).filter(
            models.Technician.store_id == store_id,
            models.Technician.nama.ilike(nama)).first()
    return None


def _accident_row(db, a: models.WorkAccident):
    t = db.query(models.Technician).filter(models.Technician.id == a.technician_id).first()
    svc = db.query(models.Service).filter(models.Service.invoice == a.invoice).first() if a.invoice else None
    return {"id": a.id, "tanggal": a.tanggal, "invoice": a.invoice,
            "device": svc.device if svc else None,
            "pelanggan": svc.nama if svc else None,
            "teknisi": t.nama if t else None,
            "teknisi_id": a.technician_id,
            "level": (t.level or "junior") if t else None,
            "jenis": a.jenis, "kronologi": a.kronologi,
            "part_pengganti": a.part_pengganti,
            "sumber_pengganti": a.sumber_pengganti,
            "modal_pengganti": a.modal_pengganti,
            "siapa_bayar": a.siapa_bayar,
            "beban_persen": a.beban_persen,
            "beban_teknisi": a.beban_teknisi,
            "beban_toko": a.beban_toko,
            "nota_pelanggan": a.nota_pelanggan,
            "status": a.status, "dibuat_oleh": a.dibuat_oleh,
            "created_at": a.created_at}


# ================= KECELAKAHAAN KERJA =================
@router.get("/accidents")
def list_accidents(store_id: Optional[int] = Query(None), status: Optional[str] = Query(None),
                   technician_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx(db, current, store_id)
    q = db.query(models.WorkAccident).filter(models.WorkAccident.store_id == store.id)
    if status:
        q = q.filter(models.WorkAccident.status == status)
    if technician_id:
        q = q.filter(models.WorkAccident.technician_id == technician_id)
    rows = q.order_by(models.WorkAccident.id.desc()).limit(200).all()
    return [_accident_row(db, a) for a in rows]


@router.get("/accidents/ringkasan")
def ringkasan_accidents(store_id: Optional[int] = Query(None),
                        db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx(db, current, store_id)
    rows = db.query(models.WorkAccident).filter(models.WorkAccident.store_id == store.id).all()
    today = datetime.date.today()
    ym = today.strftime("%Y-%m")
    bln = [a for a in rows if str(a.tanggal or "")[:7] == ym]
    aktif = [a for a in rows if a.status != "selesai"]
    return {
        "total": len(rows),
        "total_rugi": sum(int(a.modal_pengganti or 0) for a in rows),
        "beban_teknisi": sum(int(a.beban_teknisi or 0) for a in rows),
        "beban_toko": sum(int(a.beban_toko or 0) for a in rows),
        "nota_pelanggan": sum(int(a.nota_pelanggan or 0) for a in rows),
        "bulan_ini": len(bln),
        "rugi_bulan_ini": sum(int(a.modal_pengganti or 0) for a in bln),
        "aktif": len(aktif),
        "sisa_aktif": sum(int(a.beban_teknisi or 0) for a in aktif),
    }


@router.post("/accidents")
def create_accident(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                    db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Catat kecelakaan kerja. Beban default 50% teknisi / 50% toko.
    Kalau siapa_bayar=pelanggan → teknisi & toko Rp 0, tagihan ke pelanggan.
    Beban teknisi > 0 → otomatis jadi TechDebt (cicilan max 20% jalan)."""
    store, _ = _ctx(db, current, store_id)
    invoice = (payload.get("invoice") or "").strip() or None
    svc = None
    if invoice:
        svc = db.query(models.Service).filter(models.Service.invoice == invoice).first()
        if not svc or svc.store_id != store.id:
            raise HTTPException(status_code=404, detail="Service tidak ditemukan di toko ini")
    jenis = (payload.get("jenis") or "part_rusak").strip().lower()
    if jenis not in JENIS_ACC:
        raise HTTPException(status_code=400, detail="jenis tidak dikenal")
    sumber = (payload.get("sumber_pengganti") or "persediaan").strip().lower()
    if sumber not in SUMBER:
        raise HTTPException(status_code=400, detail="sumber_pengganti harus persediaan atau beli_luar")
    bayar = (payload.get("siapa_bayar") or "toko").strip().lower()
    if bayar not in SAPA_BAYAR:
        raise HTTPException(status_code=400, detail="siapa_bayar harus toko atau pelanggan")
    modal = int(payload.get("modal_pengganti") or 0)
    if modal < 0:
        raise HTTPException(status_code=400, detail="modal_pengganti >= 0")
    try:
        persen = int(payload.get("beban_persen") if payload.get("beban_persen") is not None else 50)
    except Exception:
        raise HTTPException(status_code=400, detail="beban_persen harus angka")
    if persen not in (0, 25, 50, 75, 100):
        raise HTTPException(status_code=400, detail="beban_persen harus 0/25/50/75/100")
    tech = _find_tech(db, store.id, payload)
    kronologi = (payload.get("kronologi") or "").strip() or None
    if not kronologi:
        raise HTTPException(status_code=400, detail="kronologi wajib diisi")
    tanggal = _parse_tgl(payload.get("tanggal"))

    a = models.WorkAccident(store_id=store.id, invoice=invoice,
                            technician_id=tech.id if tech else None,
                            tanggal=tanggal, jenis=jenis, kronologi=kronologi,
                            part_pengganti=(payload.get("part_pengganti") or "").strip() or None,
                            sumber_pengganti=sumber, modal_pengganti=modal,
                            siapa_bayar=bayar, beban_persen=persen,
                            dibuat_oleh=getattr(current, "username", None))
    db.add(a)
    db.commit()
    db.refresh(a)

    # bagi beban
    if bayar == "pelanggan":
        a.nota_pelanggan = modal
        a.beban_teknisi = 0
        a.beban_toko = 0
        db.commit()
    elif tech is None:
        # tidak ada teknisi ditunjuk → 100% toko
        a.nota_pelanggan = 0
        a.beban_teknisi = 0
        a.beban_toko = modal
        db.commit()
    else:
        res = el.apply_teknisi_beban(db, store.id, tech, modal, persen=persen,
                                      sebab="kelalaian", invoice=invoice,
                                      label="Kecelakaan kerja")
        a.beban_teknisi = res["beban_teknisi"]
        a.beban_toko = res["beban_toko"]
        db.commit()
    db.refresh(a)
    log_action(db, "finance.kecelakaan", target=invoice or f"ACC-{a.id}",
               detail=f"{jenis} modal={modal} teknisi={tech.nama if tech else '-'} "
                      f"beban_teknisi={a.beban_teknisi} bayar={bayar}",
               actor=current, store_id=store.id)
    # Buku besar (prinsip mentor): beban TOKO kecelakaan = HPP (ikut komisi+modal).
    # sumber=beli_luar → kas keluar beneran; sumber=persediaan → HPP tanpa gerak kas
    # (stok berkurang dihitung via mutasi, kas tidak gerak — pola sama seperti pakai part).
    if int(a.beban_toko or 0) > 0:
        try:
            dari_stok = (sumber == "persediaan")
            _ledger_add(db, store.id, tanggal, "keluar", "B1",
                        f"Beban toko {invoice or f'ACC-{a.id}'}: {jenis}"
                        f"{f' {a.part_pengganti}' if a.part_pengganti else ''}"
                        f" ({sumber})",
                        int(a.beban_toko),
                        "stok" if dari_stok else lm.METODE_KE_MEDIA.get("Tunai", "kas_utama"),
                        ref_type="accident", ref_id=a.id,
                        oleh=getattr(current, "username", None),
                        masuk_laba=True, pengaruh_kas=not dari_stok)
            db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            print("ledger accident skip:", e)
    return _accident_row(db, a)


@router.post("/accidents/{acc_id}/selesai")
def close_accident(acc_id: int, db: Session = Depends(get_db), current=Depends(get_current_user),
                   store_id: Optional[int] = Query(None)):
    """Tandai kecelakaan selesai (part pengganti sudah terpasang)."""
    store, _ = _ctx(db, current, store_id)
    a = db.query(models.WorkAccident).filter(
        models.WorkAccident.id == acc_id, models.WorkAccident.store_id == store.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    a.status = "selesai"
    db.commit()
    db.refresh(a)
    log_action(db, "finance.kecelakaan_selesai", target=a.invoice or f"ACC-{a.id}",
               detail=f"ACC-{a.id} ditandai selesai", actor=current, store_id=store.id)
    return _accident_row(db, a)


def _ledger_add(db, store_id, tanggal, jenis, kategori, keterangan, nominal,
                media, media_tujuan=None, ref_type=None, ref_id=None, oleh=None,
                subkategori=None, masuk_laba=True, pengaruh_kas=True, skip_dup=False):
    """Tambah 1 baris buku besar (tanpa commit — caller yang commit).
    Guard duplikat dual-write via (ref_type, ref_id). Untuk gajian (ref_id=teknisi
    dipakai tiap minggu) guard ini dilewati; idempotensi dicek per week_start.
    Prinsip mentor: masuk_laba=False = persediaan (belum HPP); pengaruh_kas=False = tanpa gerak kas."""
    err = lm.validate_entry(kategori, jenis, nominal, media, media_tujuan)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if kategori == "D" and (subkategori or "") not in lm.SUB_D:
        raise HTTPException(status_code=400, detail="kategori D wajib subkategori: " + "/".join(lm.SUB_D))
    if not skip_dup and ref_type and ref_id is not None:
        dup = db.query(models.LedgerEntry).filter(
            models.LedgerEntry.store_id == store_id,
            models.LedgerEntry.ref_type == ref_type,
            models.LedgerEntry.ref_id == ref_id).first()
        if dup:
            return dup
    row = models.LedgerEntry(store_id=store_id, tanggal=tanggal, jenis=jenis,
                             kategori=kategori, keterangan=keterangan, nominal=nominal,
                             media=media, media_tujuan=media_tujuan,
                             ref_type=ref_type, ref_id=ref_id, dibuat_oleh=oleh,
                             subkategori=subkategori,
                             masuk_laba=bool(masuk_laba), pengaruh_kas=bool(pengaruh_kas))
    db.add(row)
    db.flush()
    return row


def _ledger_row(e: models.LedgerEntry):
    meta = lm.KATEGORI.get(e.kategori, {})
    return {"id": e.id, "tanggal": e.tanggal, "jenis": e.jenis,
            "kategori": e.kategori, "kategori_nama": meta.get("nama"),
            "kelompok": meta.get("kelompok"), "subkategori": e.subkategori,
            "masuk_laba": True if e.masuk_laba is None else bool(e.masuk_laba),
            "pengaruh_kas": True if e.pengaruh_kas is None else bool(e.pengaruh_kas),
            "keterangan": e.keterangan, "nominal": e.nominal,
            "media": e.media, "media_nama": lm.MEDIA.get(e.media),
            "media_tujuan": e.media_tujuan,
            "ref_type": e.ref_type, "ref_id": e.ref_id,
            "dibuat_oleh": e.dibuat_oleh, "created_at": e.created_at}


def _parse_tgl(v):
    if not v:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="tanggal harus format YYYY-MM-DD")


# ================= SATU MESIN HITUNG KEUANGAN =================
#_owner.html punya 3 tampilan arus kas yang dulu dihitung 3 rumus beda (ownArus, tren-bulanan,
# ringkasan). Semua sekarang lewat _agregat_ledger() supaya tidak bisa melenceng sendiri.
#
# DUA DIMENSI, jangan dicampur:
#   KAS  = uang benar-benar bergerak. Cuma baris pengaruh_kas=True. Inilah yang
#          dibandingkan fisik saat Tutup Kas.
#   LABA = hasil usaha. Cuma baris masuk_laba=True.
# Contoh yang bedanya nyata: komisi teknisi sudah jadi HPP (LABA) sejak service cair,
# tapi uangnya belum keluar sampai gajian (pengaruh_kas=False).
# Belanja stok: uang keluar (KAS) tapi bukan beban — baru jadi HPP saat part terpakai
# (masuk_laba=False saat beli, rudanya posts servicepart dengan masuk_laba=True).
_REF_PENJUALAN = ("sale", "sale_jasa")
_REF_HPP_BARANG = ("sale_hpp", "servicepart")


def _agregat_ledger(rows):
    """Agregasi baris buku besar jadi blok KAS dan blok LABA terpisah."""
    g = {
        # --- KAS: uang yang benar-benar masuk/keluar laci/bank ---
        "kas_masuk": 0, "kas_keluar": 0,
        "masuk_service": 0, "masuk_penjualan": 0, "masuk_modal": 0, "masuk_lain": 0,
        "keluar_gajian": 0, "keluar_operasional": 0, "keluar_belanja": 0,
        "keluar_refund": 0, "keluar_lain": 0,
        # --- LABA: hasil usaha ---
        "omzet_service": 0, "omzet_penjualan": 0, "omzet_lain": 0, "refund_omzet": 0,
        "hpp_komisi": 0, "hpp_modal_barang": 0, "hpp_part": 0, "hpp_beban": 0,
        "ops_biaya": 0, "ops_hadir": 0,
        "modal": 0, "prive": 0, "aset": 0, "non_masuk": 0, "non_keluar": 0,
        # --- Persediaan (belanja = aset, bukan beban) ---
        "persediaan": 0, "persediaan_per_kat": {"B1": 0, "B2": 0, "B3": 0},
        "transfer": 0,
    }
    for e in rows:
        n = int(e.nominal or 0)
        if not n:
            continue
        kat = e.kategori or ""
        kel = lm.kelompok_of(kat)
        ref = (e.ref_type or "manual")
        masuk = e.jenis == "masuk"
        keluar = e.jenis == "keluar"
        kas = True if e.pengaruh_kas is None else bool(e.pengaruh_kas)
        laba = True if e.masuk_laba is None else bool(e.masuk_laba)

        if e.jenis == "transfer":
            g["transfer"] += n  # F1 pindah media: bukan omzet, bukan biaya
            continue

        # ---------- dimensi KAS ----------
        if kas:
            if masuk:
                if ref == "service":
                    g["masuk_service"] += n
                elif ref in _REF_PENJUALAN:
                    g["masuk_penjualan"] += n
                elif kel == "owner":
                    g["masuk_modal"] += n      # E1 modal owner: masuk kas, bukan omzet
                else:
                    g["masuk_lain"] += n
                g["kas_masuk"] += n
            elif keluar:
                if ref == "gajian":
                    g["keluar_gajian"] += n
                elif ref == "refund" or kel == "omzet":
                    g["keluar_refund"] += n
                elif kel == "hpp":
                    g["keluar_belanja"] += n   # B1/B2 expense = beli stok, uang jadi keluar
                elif kel == "operasional":
                    g["keluar_operasional"] += n
                else:
                    g["keluar_lain"] += n      # prive / aset / beban langsung
                g["kas_keluar"] += n

        # ---------- dimensi LABA ----------
        if not laba:
            # masuk_laba=False: belanja barang. Kas keluar (kalau pengaruh_kas) tapi
            # belum beban — jadi persediaan, HPP-nya terbentuk saat terjual/terpakai.
            if keluar and kel == "hpp":
                g["persediaan"] += n
                if kat in g["persediaan_per_kat"]:
                    g["persediaan_per_kat"][kat] += n
            continue

        if masuk:
            if kel == "omzet":
                if ref == "service":
                    g["omzet_service"] += n
                elif ref in _REF_PENJUALAN:
                    g["omzet_penjualan"] += n
                else:
                    g["omzet_lain"] += n
            elif kel == "owner":
                g["modal"] += n
            elif kel == "non":
                g["non_masuk"] += n
        elif keluar:
            if kel == "hpp":
                if ref == "service_komisi":
                    g["hpp_komisi"] += n
                elif ref == "servicepart":
                    g["hpp_part"] += n
                elif ref == "servicepart_margin":
                    g["hpp_part"] += n
                elif ref in _REF_HPP_BARANG:
                    g["hpp_modal_barang"] += n
                else:
                    g["hpp_beban"] += n
            elif kel == "omzet":
                g["refund_omzet"] += n      # refund = pengurang omzet
            elif kel == "operasional":
                if ref == "allowance":
                    g["ops_hadir"] += n
                else:
                    g["ops_biaya"] += n
            elif kel == "aset":
                g["aset"] += n
            elif kel == "owner":
                g["prive"] += n
            elif kel == "non":
                g["non_keluar"] += n

    g["kas_bersih"] = g["kas_masuk"] - g["kas_keluar"]
    g["omzet"] = (g["omzet_service"] + g["omzet_penjualan"] + g["omzet_lain"]
                  - g["refund_omzet"])
    g["hpp"] = g["hpp_komisi"] + g["hpp_modal_barang"] + g["hpp_part"] + g["hpp_beban"]
    g["operasional"] = g["ops_biaya"] + g["ops_hadir"]
    g["laba_kotor"] = g["omzet"] - g["hpp"]
    g["laba_bersih"] = g["laba_kotor"] - g["operasional"]
    return g


def _saldo_media(rows):
    """Saldo kumulatif per media (transfer menggeser kedua sisi). Hanya pengaruh_kas."""
    saldo = {m: 0 for m in lm.MEDIA}
    for e in rows:
        if e.pengaruh_kas is False:
            continue
        n = int(e.nominal or 0)
        if e.jenis == "masuk" and e.media in saldo:
            saldo[e.media] += n
        elif e.jenis == "keluar" and e.media in saldo:
            saldo[e.media] -= n
        elif e.jenis == "transfer":
            if e.media in saldo:
                saldo[e.media] -= n
            if (e.media_tujuan or "") in saldo:
                saldo[e.media_tujuan] += n
    return saldo


MEDIA_UANG = [m for m in lm.MEDIA if m != "stok"]


def _week_bounds(tgl):
    """Minggu gajian = Senin..Sabtu. Hari Minggu masuk minggu yang baru tutup
    (sama dengan _gajiWeek() di frontend)."""
    if isinstance(tgl, datetime.datetime):
        tgl = tgl.date()
    wd = tgl.weekday()  # Senin=0 .. Minggu=6
    if wd == 6:
        start = tgl - datetime.timedelta(days=6)
    else:
        start = tgl - datetime.timedelta(days=wd)
    return start, start + datetime.timedelta(days=5)


def _gajian_week_of(row):
    """Ambil week_start (Senin) dari keterangan 'Gajian <nama> YYYY-MM-DD ...'."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", row.keterangan or "")
    if not m:
        return None
    try:
        return datetime.date.fromisoformat(m.group(1))
    except Exception:
        return None


def _weekly_tech_rows(db, store_id, week_start, week_end):
    """Jatah minggu Senin..Sabtu + tunggakan lama per teknisi.

    `sisa` = total yang harus dibayar sekarang (tunggakan minggu lalu + jatah
    minggu ini - payout minggu ini). Ini yang membuat saldo teknisi nol setelah
    tutup buku, bukan hanya minggu berjalan.
    """
    techs = db.query(models.Technician).filter(
        models.Technician.store_id == store_id).order_by(models.Technician.nama).all()
    out = []
    for t in techs:
        # --- tampilan minggu ini ---
        leds = db.query(models.CommissionLedger).filter(
            models.CommissionLedger.store_id == store_id,
            models.CommissionLedger.technician_id == t.id,
            models.CommissionLedger.tanggal >= week_start,
            models.CommissionLedger.tanggal <= week_end).all()
        komisi = sum(int(l.masuk_rp or 0) for l in leds if l.tipe == "komisi_cair")
        cicilan = sum(int(l.keluar_rp or 0) for l in leds if l.tipe == "potongan_cicilan")
        hadir = sum(int(l.masuk_rp or 0) for l in leds if l.tipe == "allowance")
        refund = sum(int(l.keluar_rp or 0) for l in leds if l.tipe == "refund_balik")
        hpp = sum(int(l.hpp_rp or 0) for l in leds)
        netto = komisi + hadir - refund

        # --- akumulasi s/d akhir minggu (termasuk minggu-minggu lalu) ---
        all_leds = db.query(models.CommissionLedger).filter(
            models.CommissionLedger.store_id == store_id,
            models.CommissionLedger.technician_id == t.id,
            models.CommissionLedger.tanggal <= week_end).all()
        prev_leds = [l for l in all_leds if l.tanggal < week_start]
        def _acc(rows):
            h = sum(int(l.masuk_rp or 0) for l in rows if l.tipe == "komisi_cair")
            r = sum(int(l.keluar_rp or 0) for l in rows if l.tipe == "refund_balik")
            o = sum(int(l.masuk_rp or 0) for l in rows if l.tipe == "allowance")
            return max(0, h - r) + max(0, o)
        accrued_all = _acc(all_leds)
        accrued_prev = _acc(prev_leds)

        # --- payout: pisahkan minggu ini vs minggu sebelumnya ---
        all_payouts = db.query(models.LedgerEntry).filter(
            models.LedgerEntry.store_id == store_id,
            models.LedgerEntry.ref_type == "gajian",
            models.LedgerEntry.ref_id == t.id).all()
        paid_week = paid_prev = 0
        paid_rows = []
        for p in all_payouts:
            w = _gajian_week_of(p)
            if w == week_start:
                paid_week += int(p.nominal or 0)
                paid_rows.append(p)
            elif w is not None and w < week_start:
                paid_prev += int(p.nominal or 0)
            elif w is None and p.tanggal and p.tanggal <= week_end:
                paid_prev += int(p.nominal or 0)
        tunggakan = max(0, accrued_prev - paid_prev)
        sisa = max(0, accrued_all - paid_prev - paid_week)

        debts = db.query(models.TechDebt).filter(
            models.TechDebt.technician_id == t.id,
            models.TechDebt.status == "belum").all()
        hutang = sum(int(d.sisa or 0) for d in debts)
        if netto == 0 and paid_week == 0 and tunggakan == 0 and sisa == 0 and hutang == 0:
            continue
        out.append({
            "technician_id": t.id, "nama": t.nama, "level": t.level or "junior",
            "komisi": komisi, "cicilan": cicilan, "hadir": hadir,
            "refund": refund, "hpp": hpp, "netto": netto,
            "sudah_dibayar": paid_week, "total_dibayar": paid_prev + paid_week,
            "tunggakan": tunggakan, "sisa": sisa,
            "kelebihan": max(0, paid_prev + paid_week - accrued_all),
            "sisa_hutang": hutang,
            "payout": [{"id": p.id, "tanggal": p.tanggal, "nominal": p.nominal,
                        "media": p.media, "oleh": p.dibuat_oleh}
                       for p in paid_rows],
        })
    return out


def _weekly_cash(db, store_id):
    sist = _sistem_media(db, store_id)
    return {m: int(sist.get(m, 0)) for m in MEDIA_UANG}


def _nempel_teknisi(db, store_id, d0=None, d1=None):
    """Utang gajian yang BELUM dibayar (bukan cuma baris kas=False).

    Sumbernya CommissionLedger seperti slip Gajian Sabtu:
      hpp = komisi_cair (sudah net cicilan) - refund_balik
      ops = uang hadir
      dikurangi payout gajian (LedgerEntry ref_type=gajian).
    Part terpakai & beban kecelakaan TIDAK ikut — itu bukan utang ke teknisi.
    """
    q = db.query(models.CommissionLedger).filter(
        models.CommissionLedger.store_id == store_id)
    if d0:
        q = q.filter(models.CommissionLedger.tanggal >= d0)
    if d1:
        q = q.filter(models.CommissionLedger.tanggal <= d1)
    per = {}
    for l in q.all():
        t = per.setdefault(l.technician_id, {"hpp": 0, "ops": 0, "paid": 0})
        if l.tipe == "komisi_cair":
            t["hpp"] += int(l.masuk_rp or 0)
        elif l.tipe == "refund_balik":
            t["hpp"] -= int(l.keluar_rp or 0)
        elif l.tipe == "allowance":
            t["ops"] += int(l.masuk_rp or 0)
    pq = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.store_id == store_id,
        models.LedgerEntry.ref_type == "gajian")
    if d0:
        pq = pq.filter(models.LedgerEntry.tanggal >= d0)
    if d1:
        pq = pq.filter(models.LedgerEntry.tanggal <= d1)
    for p in pq.all():
        t = per.setdefault(p.ref_id, {"hpp": 0, "ops": 0, "paid": 0})
        t["paid"] += int(p.nominal or 0)
    out_hpp = out_ops = 0
    for t in per.values():
        hpp = max(0, t["hpp"])
        ops = max(0, t["ops"])
        total = hpp + ops
        sisa = max(0, total - t["paid"])
        if not sisa or not total:
            continue
        bagian_hpp = int(round(sisa * hpp / total))
        out_hpp += bagian_hpp
        out_ops += sisa - bagian_hpp
    return {"hpp": out_hpp, "operasional": out_ops}


# ================= REFUND DANA =================
@router.get("/refunds")
def list_refunds(store_id: Optional[int] = Query(None), status: Optional[str] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx(db, current, store_id)
    q = db.query(models.Refund).filter(models.Refund.store_id == store.id)
    if status:
        q = q.filter(models.Refund.status == status)
    rows = q.order_by(models.Refund.id.desc()).limit(200).all()
    out = []
    for r in rows:
        t = db.query(models.Technician).filter(models.Technician.id == r.technician_id).first()
        svc = db.query(models.Service).filter(models.Service.invoice == r.invoice).first() if r.invoice else None
        out.append({"id": r.id, "kode": r.kode, "tanggal": r.tanggal, "invoice": r.invoice,
                    "device": svc.device if svc else None,
                    "pelanggan": svc.nama if svc else None,
                    "teknisi": t.nama if t else None,
                    "alasan": r.alasan, "nominal": r.nominal, "metode": r.metode,
                    "dari_pendapatan": r.dari_pendapatan,
                    "jadi_pengeluaran": r.jadi_pengeluaran,
                    "komisi_dibalik": r.komisi_dibalik,
                    "status": r.status, "catatan": r.catatan,
                    "dibuat_oleh": r.dibuat_oleh, "created_at": r.created_at})
    return out


@router.get("/refunds/ringkasan")
def ringkasan_refunds(store_id: Optional[int] = Query(None),
                      db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx(db, current, store_id)
    rows = db.query(models.Refund).filter(models.Refund.store_id == store.id).all()
    today = datetime.date.today()
    ym = today.strftime("%Y-%m")
    bln = [r for r in rows if str(r.tanggal or "")[:7] == ym]
    hari = [r for r in rows if str(r.tanggal or "") == today.isoformat()]
    return {
        "total": len(rows),
        "total_refund": sum(int(r.nominal or 0) for r in rows),
        "dari_pendapatan": sum(int(r.dari_pendapatan or 0) for r in rows),
        "jadi_pengeluaran": sum(int(r.jadi_pengeluaran or 0) for r in rows),
        "komisi_dibalik": sum(int(r.komisi_dibalik or 0) for r in rows),
        "bulan_ini": len(bln),
        "refund_bulan_ini": sum(int(r.nominal or 0) for r in bln),
        "hari_ini": len(hari),
        "refund_hari_ini": sum(int(r.nominal or 0) for r in hari),
    }


@router.post("/refunds")
def create_refund(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Refund klaim garansi: penuh/sebagian.
    - komisi teknisi dibalik proporsional (nominal / biaya)
    - sumber dana: omzet hari ini; kurang → jadi pengeluaran
    - tuyut_klaim: tutup service klaim jadi Service Failed + alasannya"""
    store, _ = _ctx(db, current, store_id)
    invoice = (payload.get("invoice") or "").strip() or None
    svc = None
    if invoice:
        svc = db.query(models.Service).filter(models.Service.invoice == invoice).first()
        if not svc or svc.store_id != store.id:
            raise HTTPException(status_code=404, detail="Service tidak ditemukan di toko ini")
    nominal = int(payload.get("nominal") or 0)
    if nominal <= 0:
        raise HTTPException(status_code=400, detail="nominal harus > 0")
    if svc and int(svc.biaya or 0) > 0 and nominal > int(svc.biaya or 0):
        raise HTTPException(status_code=400, detail="nominal melebihi biaya service")
    alasan = (payload.get("alasan") or "").strip() or None
    if not alasan:
        raise HTTPException(status_code=400, detail="alasan wajib diisi")
    metode = (payload.get("metode") or "Tunai").strip()
    if metode not in METODE:
        raise HTTPException(status_code=400, detail="metode harus Tunai/Transfer/QRIS")
    tanggal = _parse_tgl(payload.get("tanggal"))
    tuyut = payload.get("tutup_klaim")
    tutup_klaim = True if tuyut is None else bool(tuyut)

    # komisi dibalik proporsional
    komisi_dibalik = 0
    se = None
    if svc:
        se = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == svc.invoice).first()
    if se and int(se.komisi_teknisi or 0) > 0:
        basis = int(svc.biaya or 0) or 1
        komisi_dibalik = int(se.komisi_teknisi) * min(nominal, basis) // basis
    # sumber dana
    income = el.cek_penghasilan_hari_ini(db, store.id)
    dari_pendapatan = min(nominal, income)
    jadi_pengeluaran = nominal - dari_pendapatan

    tech = _find_tech(db, store.id, payload) or (db.query(models.Technician).filter(
        models.Technician.id == svc.technician_id).first() if svc else None)
    r = models.Refund(store_id=store.id, invoice=invoice,
                      technician_id=tech.id if tech else None,
                      tanggal=tanggal, alasan=alasan, nominal=nominal, metode=metode,
                      dari_pendapatan=dari_pendapatan, jadi_pengeluaran=jadi_pengeluaran,
                      komisi_dibalik=komisi_dibalik, status="selesai",
                      catatan=(payload.get("catatan") or "").strip() or None,
                      dibuat_oleh=getattr(current, "username", None))
    db.add(r)
    db.commit()
    db.refresh(r)
    r.kode = f"RFD-{tanggal.strftime('%Y%m')}-{r.id:04d}"
    db.commit()
    db.refresh(r)

    # ledger teknisi: komisi dibalik
    if komisi_dibalik > 0 and tech:
        db.add(models.CommissionLedger(
            store_id=store.id, technician_id=tech.id, tanggal=tanggal, invoice=invoice,
            tipe="refund_balik", masuk_rp=0, keluar_rp=komisi_dibalik, sisa_hutang_saat_itu=0,
            keterangan=f"Refund {r.kode} {nominal} dari {invoice or '-'} - komisi dibalik proporsional"))
        db.commit()

    # tutup klaim garansi
    if tutup_klaim and svc and (svc.status or "") == "Garansi":
        svc.status = "Service Failed"
        svc.hasil = "TIDAK"
        svc.keterangan = ((svc.keterangan or "") + f" | Refund {r.kode}: {alasan}").strip(" |")
        db.commit()

    # buku besar: refund = PENGURANG omzet (keluar kelompok omzet, kas ikut keluar)
    try:
        _ledger_add(db, store.id, tanggal, "keluar", "A1",
                    f"Refund {r.kode} {invoice or '-'}: {alasan}", nominal,
                    lm.METODE_KE_MEDIA.get(metode, "kas_utama"),
                    ref_type="refund", ref_id=r.id, oleh=getattr(current, "username", None),
                    masuk_laba=True, pengaruh_kas=True)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print("ledger refund skip:", e)

    log_action(db, "finance.refund", target=invoice or r.kode,
               detail=f"{r.kode} nominal={nominal} metode={metode} "
                      f"dari_pendapatan={dari_pendapatan} komisi_dibalik={komisi_dibalik}",
               actor=current, store_id=store.id)
    return {"id": r.id, "kode": r.kode, "invoice": r.invoice, "nominal": r.nominal,
            "metode": r.metode, "dari_pendapatan": r.dari_pendapatan,
            "jadi_pengeluaran": r.jadi_pengeluaran, "komisi_dibalik": komisi_dibalik,
            "status": r.status, "tanggal": r.tanggal,
            "omzet_hari_ini": income,
            "wa_link": f"https://wa.me/?text=" + _wa_quote(
                f"Refund {r.kode}\nInvoice: {invoice or '-'}\nNominal: Rp{nominal} ({metode})\n"
                f"Alasan: {alasan}\nKomisi teknisi dibalik: Rp{komisi_dibalik}")}


# ================= PENGELUARAN OPERASIONAL =================
def _ctx_read(db, current, store_id):
    """Baca pengeluaran: kasir boleh lihat (agar Kas Toko jujur), tulis tetap owner/admin."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if store is None:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin", "kasir"]:
        raise HTTPException(status_code=403, detail="Hanya tim toko yang boleh lihat pengeluaran")
    return store, role


def _expense_row(e: models.Expense):
    return {"id": e.id, "tanggal": e.tanggal, "kategori": e.kategori,
            "keperluan": e.keperluan, "nominal": e.nominal, "metode": e.metode,
            "keterangan": e.keterangan, "dibuat_oleh": e.dibuat_oleh,
            "created_at": e.created_at}


@router.get("/expenses")
def list_expenses(store_id: Optional[int] = Query(None), kategori: Optional[str] = Query(None),
                  since: Optional[str] = Query(None),
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    q = db.query(models.Expense).filter(models.Expense.store_id == store.id)
    if kategori:
        # kompatibel: filter nama lama ikut mencocokkan kode mentornya
        legacy = {"Sewa": "C2", "Listrik": "C2", "Internet": "C3", "Gaji": "C1",
                  "Belanja Part": "B1", "Operasional": "C4", "Lainnya": "C4"}
        codes = {kategori}
        if kategori in legacy:
            codes.add(legacy[kategori])
        q = q.filter(models.Expense.kategori.in_(codes))
    if since:
        try:
            d0 = datetime.datetime.strptime(since[:10], "%Y-%m-%d").date()
            q = q.filter(models.Expense.tanggal >= d0)
        except Exception:
            raise HTTPException(status_code=400, detail="since harus YYYY-MM-DD")
    rows = q.order_by(models.Expense.tanggal.desc(), models.Expense.id.desc()).limit(300).all()
    return [_expense_row(e) for e in rows]


@router.get("/expenses/ringkasan")
def ringkasan_expenses(store_id: Optional[int] = Query(None),
                       db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    rows = db.query(models.Expense).filter(models.Expense.store_id == store.id).all()
    today = datetime.date.today()
    iso, ym = today.isoformat(), today.strftime("%Y-%m")
    hari = [e for e in rows if str(e.tanggal or "") == iso]
    bln = [e for e in rows if str(e.tanggal or "")[:7] == ym]
    per_kat = {}
    for e in rows:
        k = e.kategori or "Lainnya"
        per_kat[k] = per_kat.get(k, 0) + int(e.nominal or 0)
    return {
        "total": len(rows),
        "total_nominal": sum(int(e.nominal or 0) for e in rows),
        "hari_ini": len(hari),
        "nominal_hari_ini": sum(int(e.nominal or 0) for e in hari),
        "bulan_ini": len(bln),
        "nominal_bulan_ini": sum(int(e.nominal or 0) for e in bln),
        "per_kategori": per_kat,
    }


@router.post("/expenses")
def create_expense(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Catat pengeluaran: kode mentor (B1/B2/C1-C6/D) atau nama lama (kompatibel).
    Tulis: owner/admin/kasir/superadmin (kasir dari Kas Toko). Hapus tetap owner/admin."""
    store, _ = _ctx_write(db, current, store_id)
    keperluan = (payload.get("keperluan") or "").strip()
    if not keperluan:
        raise HTTPException(status_code=400, detail="keperluan wajib diisi")
    nominal = int(payload.get("nominal") or 0)
    if nominal <= 0:
        raise HTTPException(status_code=400, detail="nominal harus > 0")
    kat_in = (payload.get("kategori") or "C4").strip()
    # nama lama -> kode mentor (kompatibel data/form lama)
    kat_legacy = {"Sewa": "C2", "Listrik": "C2", "Internet": "C3", "Gaji": "C1",
                  "Belanja Part": "B1", "Operasional": "C4", "Lainnya": "C4"}
    if kat_in in lm.KAT_EXPENSE_NEW:
        kode = kat_in
    elif kat_in in kat_legacy:
        kode = kat_legacy[kat_in]
    else:
        raise HTTPException(status_code=400, detail="kategori harus kode mentor: " + "/".join(sorted(lm.KAT_EXPENSE_NEW.keys())))
    kategori = kode  # simpan kode mentor (C4, B1, D, ...)
    metode = (payload.get("metode") or "Tunai").strip()
    if metode not in METODE:
        raise HTTPException(status_code=400, detail="metode harus Tunai/Transfer/QRIS")
    subkategori = (payload.get("subkategori") or "").strip() or None
    if kode == "D" and (subkategori or "") not in lm.SUB_D:
        raise HTTPException(status_code=400, detail="kategori D wajib subkategori: " + "/".join(lm.SUB_D))
    e = models.Expense(store_id=store.id, tanggal=_parse_tgl(payload.get("tanggal")),
                       kategori=kategori, keperluan=keperluan, nominal=nominal,
                       metode=metode,
                       keterangan=(payload.get("keterangan") or "").strip() or None,
                       dibuat_oleh=getattr(current, "username", None))
    db.add(e)
    db.flush()
    # dual-write ke buku besar pusat (kode mentor, media dari metode bayar).
    # Prinsip mentor: belanja barang (B1/B2) = PERSEDIAAN (masuk_laba=False), HPP saat terjual/terpakai.
    label = lm.KAT_EXPENSE_NEW.get(kode, kode)
    is_belanja = kode in ("B1", "B2")
    _ledger_add(db, store.id, e.tanggal, "keluar", kode,
                f"{label}: {keperluan}", nominal,
                lm.METODE_KE_MEDIA.get(metode, "kas_utama"),
                ref_type="expense", ref_id=e.id, oleh=getattr(current, "username", None),
                subkategori=subkategori, masuk_laba=not is_belanja, pengaruh_kas=True)
    # Prinsip mentor: beli = uang berkurang + STOK BERTAMBAH (opsional, pilih barangnya).
    stok_info = ""
    if is_belanja:
        ts = payload.get("tambah_stok") or {}
        try:
            sp_id = int(ts.get("sparepart_id") or 0)
            qty = int(ts.get("qty") or 0)
        except Exception:
            sp_id, qty = 0, 0
        if sp_id and qty > 0:
            sp = db.query(models.Sparepart).filter(
                models.Sparepart.id == sp_id,
                models.Sparepart.store_id == store.id).first()
            if not sp:
                raise HTTPException(status_code=404, detail="barang stok tidak ditemukan di toko ini")
            sp, err = crud.masuk_part(db, sp, qty, actor=current, ref=f"EXP-{e.id}")
            if err:
                raise HTTPException(status_code=400, detail=err)
            stok_info = f" + stok {sp.nama} +{qty}"
    db.commit()
    db.refresh(e)
    log_action(db, "finance.expense", target=f"EXP-{e.id}",
               detail=f"{kategori} {keperluan} nominal={nominal} metode={metode}{stok_info}",
               actor=current, store_id=store.id)
    return _expense_row(e)


@router.delete("/expenses/{exp_id}")
def delete_expense(exp_id: int, store_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Hapus salah input. Tulis: owner/admin/superadmin saja."""
    store, _ = _ctx(db, current, store_id)
    e = db.query(models.Expense).filter(models.Expense.id == exp_id,
                                        models.Expense.store_id == store.id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Pengeluaran tidak ditemukan di toko ini")
    info = f"{e.kategori} {e.keperluan} nominal={e.nominal}"
    db.query(models.LedgerEntry).filter(
        models.LedgerEntry.store_id == store.id,
        models.LedgerEntry.ref_type == "expense",
        models.LedgerEntry.ref_id == exp_id).delete()
    db.delete(e)
    db.commit()
    log_action(db, "finance.expense_hapus", target=f"EXP-{exp_id}",
               detail=info, actor=current, store_id=store.id)
    return {"ok": True, "id": exp_id}


# ================= BEBAN TOKO HARIAN (setting: isi sekali, berlaku tiap hari) =================
def _beban_out(s):
    import json as _json
    custom = []
    try:
        custom = _json.loads(s.custom or "[]")
        if not isinstance(custom, list):
            custom = []
    except Exception:
        custom = []
    custom = [{"nama": str(c.get("nama") or "")[:60], "nominal": int(c.get("nominal") or 0)}
              for c in custom if isinstance(c, dict) and str(c.get("nama") or "").strip()]
    total = (int(s.sewa_harian or 0) + int(s.listrik_harian or 0) + int(s.wifi_harian or 0)
             + int(s.gaji_harian or 0) + sum(c["nominal"] for c in custom))
    return {"sewa_harian": int(s.sewa_harian or 0), "listrik_harian": int(s.listrik_harian or 0),
            "wifi_harian": int(s.wifi_harian or 0), "gaji_harian": int(s.gaji_harian or 0),
            "custom": custom, "total_hari": total,
            "configured": total > 0, "updated_oleh": s.updated_oleh}


@router.get("/beban-toko")
def get_beban_toko(store_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    s = db.query(models.StoreBeban).filter(models.StoreBeban.store_id == store.id).first()
    if not s:
        return {"store_id": store.id, "sewa_harian": 0, "listrik_harian": 0, "wifi_harian": 0,
                "gaji_harian": 0, "custom": [], "total_hari": 0, "configured": False, "updated_oleh": None}
    return {"store_id": store.id, **_beban_out(s)}


@router.put("/beban-toko")
def put_beban_toko(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Simpan beban toko harian (owner only). Full-replace: ganti = berlaku mulai hari ini."""
    store, role = _ctx(db, current, store_id)
    if role not in ["superadmin", "owner"]:
        raise HTTPException(status_code=403, detail="Hanya owner yang boleh ubah beban toko")

    def _int(v):
        try:
            return max(0, min(999_999_999, int(v)))
        except (TypeError, ValueError):
            return 0

    custom = payload.get("custom") or []
    if not isinstance(custom, list) or len(custom) > 20:
        raise HTTPException(status_code=400, detail="custom maksimal 20 item")
    clean = []
    for c in custom:
        if not isinstance(c, dict):
            continue
        nama = str(c.get("nama") or "").strip()[:60]
        if not nama:
            continue
        clean.append({"nama": nama, "nominal": _int(c.get("nominal"))})
    s = db.query(models.StoreBeban).filter(models.StoreBeban.store_id == store.id).first()
    if not s:
        s = models.StoreBeban(store_id=store.id)
        db.add(s)
    s.sewa_harian = _int(payload.get("sewa_harian"))
    s.listrik_harian = _int(payload.get("listrik_harian"))
    s.wifi_harian = _int(payload.get("wifi_harian"))
    s.gaji_harian = _int(payload.get("gaji_harian"))
    s.custom = json.dumps(clean)
    s.updated_oleh = current.username
    db.commit()
    db.refresh(s)
    out = _beban_out(s)
    log_action(db, "beban_toko", target=f"store:{store.id}",
               detail=f"total/hari={out['total_hari']} sewa={out['sewa_harian']} listrik={out['listrik_harian']} "
                      f"wifi={out['wifi_harian']} gaji={out['gaji_harian']} custom={len(clean)}",
               actor=current, store_id=store.id)
    return {"store_id": store.id, **out}


# ================= PEMASUKAN MANUAL (modal awal / tambahan modal / lain) =================
KAT_INCOME = ["Modal Awal", "Tambahan Modal", "Pemasukan Lain"]


def _income_row(e: models.CashIncome):
    return {"id": e.id, "tanggal": e.tanggal, "kategori": e.kategori,
            "sumber": e.sumber, "nominal": e.nominal, "metode": e.metode,
            "keterangan": e.keterangan, "dibuat_oleh": e.dibuat_oleh,
            "created_at": e.created_at}


@router.get("/incomes")
def list_incomes(store_id: Optional[int] = Query(None), kategori: Optional[str] = Query(None),
                 since: Optional[str] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    q = db.query(models.CashIncome).filter(models.CashIncome.store_id == store.id)
    if kategori:
        q = q.filter(models.CashIncome.kategori == kategori)
    if since:
        try:
            d0 = datetime.datetime.strptime(since[:10], "%Y-%m-%d").date()
            q = q.filter(models.CashIncome.tanggal >= d0)
        except Exception:
            raise HTTPException(status_code=400, detail="since harus YYYY-MM-DD")
    rows = q.order_by(models.CashIncome.tanggal.desc(), models.CashIncome.id.desc()).limit(300).all()
    return [_income_row(e) for e in rows]


@router.get("/incomes/ringkasan")
def ringkasan_incomes(store_id: Optional[int] = Query(None),
                      db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    rows = db.query(models.CashIncome).filter(models.CashIncome.store_id == store.id).all()
    today = datetime.date.today()
    iso, ym = today.isoformat(), today.strftime("%Y-%m")
    hari = [e for e in rows if str(e.tanggal or "") == iso]
    bln = [e for e in rows if str(e.tanggal or "")[:7] == ym]
    per_kat = {}
    for e in rows:
        k = e.kategori or "Lainnya"
        per_kat[k] = per_kat.get(k, 0) + int(e.nominal or 0)
    return {
        "total": len(rows),
        "total_nominal": sum(int(e.nominal or 0) for e in rows),
        "hari_ini": len(hari),
        "nominal_hari_ini": sum(int(e.nominal or 0) for e in hari),
        "bulan_ini": len(bln),
        "nominal_bulan_ini": sum(int(e.nominal or 0) for e in bln),
        "per_kategori": per_kat,
    }


@router.post("/incomes")
def create_income(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Catat pemasukan manual (modal awal / tambahan modal / lain). Tulis: owner/admin/kasir/superadmin."""
    store, _ = _ctx_write(db, current, store_id)
    sumber = (payload.get("sumber") or "").strip()
    if not sumber:
        raise HTTPException(status_code=400, detail="sumber wajib diisi (mis. Modal awal laci kasir)")
    nominal = int(payload.get("nominal") or 0)
    if nominal <= 0:
        raise HTTPException(status_code=400, detail="nominal harus > 0")
    kategori = (payload.get("kategori") or "Modal Awal").strip()
    if kategori not in KAT_INCOME:
        raise HTTPException(status_code=400, detail="kategori harus: " + "/".join(KAT_INCOME))
    metode = (payload.get("metode") or "Tunai").strip()
    if metode not in METODE:
        raise HTTPException(status_code=400, detail="metode harus Tunai/Transfer/QRIS")
    e = models.CashIncome(store_id=store.id, tanggal=_parse_tgl(payload.get("tanggal")),
                          kategori=kategori, sumber=sumber, nominal=nominal,
                          metode=metode,
                          keterangan=(payload.get("keterangan") or "").strip() or None,
                          dibuat_oleh=getattr(current, "username", None))
    db.add(e)
    db.flush()
    # dual-write ke buku besar pusat (E1 modal / A4 pendapatan lain)
    _ledger_add(db, store.id, e.tanggal, "masuk", lm.INCOME_CAT_MAP.get(kategori, "A4"),
                f"{kategori}: {sumber}", nominal,
                lm.METODE_KE_MEDIA.get(metode, "kas_utama"),
                ref_type="income", ref_id=e.id, oleh=getattr(current, "username", None))
    db.commit()
    db.refresh(e)
    log_action(db, "finance.income", target=f"IN-{e.id}",
               detail=f"{kategori} {sumber} nominal={nominal} metode={metode}",
               actor=current, store_id=store.id)
    return _income_row(e)


@router.delete("/incomes/{inc_id}")
def delete_income(inc_id: int, store_id: Optional[int] = Query(None),
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Hapus salah input. Tulis: owner/admin/superadmin saja."""
    store, _ = _ctx(db, current, store_id)
    e = db.query(models.CashIncome).filter(models.CashIncome.id == inc_id,
                                           models.CashIncome.store_id == store.id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Pemasukan tidak ditemukan di toko ini")
    info = f"{e.kategori} {e.sumber} nominal={e.nominal}"
    db.query(models.LedgerEntry).filter(
        models.LedgerEntry.store_id == store.id,
        models.LedgerEntry.ref_type == "income",
        models.LedgerEntry.ref_id == inc_id).delete()
    db.delete(e)
    db.commit()
    log_action(db, "finance.income_hapus", target=f"IN-{inc_id}",
               detail=info, actor=current, store_id=store.id)
    return {"ok": True, "id": inc_id}


# ================= BUKU BESAR PUSAT (pondasi mentor A-G) =================
@router.get("/kategori")
def get_kategori(current=Depends(get_current_user)):
    """Peta kategori mentor A-G + media G untuk dropdown frontend. Login saja cukup."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    return {"kategori": lm.KATEGORI, "kelompok": lm.KELOMPOK, "media": lm.MEDIA,
            "jenis": lm.JENIS, "expense_map": lm.EXPENSE_CAT_MAP,
            "income_map": lm.INCOME_CAT_MAP,
            "expense_codes": lm.KAT_EXPENSE_NEW, "sub_d": lm.SUB_D,
            "kas_kecil_default": lm.KAS_KECIL_DEFAULT}


@router.get("/ledger/ringkasan")
def ringkasan_ledger(store_id: Optional[int] = Query(None),
                     db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Semua masa lalu, dari buku besar. Lihat /ledger/periode untuk rentang tertentu.
    Prinsip mentor: hanya baris masuk_laba yang hitung laba (persediaan dikecualikan);
    hanya baris pengaruh_kas yang gerakkan kas (transfer tidak masuk omzet/biaya)."""
    store, _ = _ctx_read(db, current, store_id)
    rows = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store.id).all()
    g = _agregat_ledger(rows)
    nempel = _nempel_teknisi(db, store.id)
    return {
        "omzet": g["omzet"], "hpp": g["hpp"], "operasional": g["operasional"],
        "aset": g["aset"], "modal": g["modal"], "prive": g["prive"],
        "non_masuk": g["non_masuk"], "non_keluar": g["non_keluar"],
        "total_masuk": g["kas_masuk"], "total_keluar": g["kas_keluar"],
        "arus_bersih": g["kas_bersih"],
        "laba_kotor": g["laba_kotor"], "laba_bersih": g["laba_bersih"],
        "persediaan": g["persediaan"], "persediaan_per_kat": g["persediaan_per_kat"],
        "nempel_hpp": nempel["hpp"], "nempel_ops": nempel["operasional"],
        "per_media": {m: v for m, v in _sistem_media(db, store.id).items() if m in MEDIA_UANG},
        "count": len(rows),
    }


@router.get("/ledger/periode")
def ringkasan_periode(dari: Optional[str] = Query(None), sampai: Optional[str] = Query(None),
                      bulan: Optional[str] = Query(None, description="YYYY-MM, ringkas 1 bulan"),
                      store_id: Optional[int] = Query(None),
                      db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Ringkasan KAS + LABA untuk satu rentang tanggal. INI sumber angka tunggal untuk
    kartu Arus Kas / Laba-Rugi owner.

    Para: agar Tutup Kas dan kartu Kas tidak pernah beda, keduanya wajib pakai fungsi ini
    (atau /ledger/ringkasan untuk saldo kumulatif) — jangan hitung ulang di frontend.

    - Tanpa parameter -> semua masa lalu.
    - ?bulan=YYYY-MM -> 1 bulan penuh.
    - ?dari=&sampai= -> rentang bebas (sampai opsional).
    Return `saldo_awal` = saldo per media SEBELUM tanggal mulai, jadi `saldo_akhir` bisa
    dipakai langsung membandingkan fisik Tutup Kas.
    """
    store, _ = _ctx_read(db, current, store_id)
    today = datetime.date.today()
    d0 = _parse_tgl(dari) if dari else None
    d1 = _parse_tgl(sampai) if sampai else None
    if bulan:
        try:
            y, m = int(str(bulan)[:4]), int(str(bulan)[5:7])
            d0 = datetime.date(y, m, 1)
            d1 = (datetime.date(y + 1, 1, 1) - datetime.timedelta(days=1)) if m == 12 \
                else datetime.date(y, m + 1, 1) - datetime.timedelta(days=1)
        except Exception:
            raise HTTPException(status_code=400, detail="bulan harus format YYYY-MM")
    if d1 and d0 and d1 < d0:
        d0, d1 = d1, d0
    if d1 and d1 > today:
        d1 = today

    allrows = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.store_id == store.id).order_by(
        models.LedgerEntry.tanggal, models.LedgerEntry.id).all()

    def _d(e):
        v = e.tanggal
        if isinstance(v, datetime.datetime):
            return v.date()
        if isinstance(v, str):
            try:
                return datetime.datetime.strptime(v[:10], "%Y-%m-%d").date()
            except Exception:
                return None
        return v

    if d0:
        awal = [e for e in allrows if (_d(e) or today) < d0]
        rows = [e for e in allrows if d0 <= (_d(e) or today) <= (d1 or today)]
    else:
        awal = []
        rows = allrows

    g = _agregat_ledger(rows)
    nempel = _nempel_teknisi(db, store.id, d0, d1)
    # saldo_awal = posisi laci SEBELUM rentang; saldo_akhir = posisi s/d batas akhir.
    # Bandingkan saldo_akhir dengan fisik saat Tutup Kas tanggal tersebut.
    if d0:
        saldo_awal = _saldo_media(awal)
        saldo_akhir = _saldo_media(awal + rows)
    else:
        saldo_awal = {m: 0 for m in lm.MEDIA}
        saldo_akhir = _saldo_media(allrows)

    return {
        "store_id": store.id,
        "dari": d0, "sampai": d1 or today, "bulan": (d0.strftime("%Y-%m") if d0 else None),
        "jumlah_baris": len(rows),
        "kas": {
            "masuk": g["kas_masuk"], "keluar": g["kas_keluar"], "bersih": g["kas_bersih"],
            "masuk_service": g["masuk_service"], "masuk_penjualan": g["masuk_penjualan"],
            "masuk_modal": g["masuk_modal"], "masuk_lain": g["masuk_lain"],
            "keluar_gajian": g["keluar_gajian"], "keluar_operasional": g["keluar_operasional"],
            "keluar_belanja": g["keluar_belanja"], "keluar_refund": g["keluar_refund"],
            "keluar_lain": g["keluar_lain"],
        },
        "laba": {
            "omzet": g["omzet"], "hpp": g["hpp"], "kotor": g["laba_kotor"],
            "operasional": g["operasional"], "bersih": g["laba_bersih"],
            "omzet_service": g["omzet_service"], "omzet_penjualan": g["omzet_penjualan"],
            "omzet_lain": g["omzet_lain"], "refund": g["refund_omzet"],
            "hpp_komisi": g["hpp_komisi"], "hpp_modal_barang": g["hpp_modal_barang"],
            "hpp_part": g["hpp_part"], "hpp_beban": g["hpp_beban"],
            "ops_biaya": g["ops_biaya"], "ops_hadir": g["ops_hadir"],
            "modal": g["modal"], "prive": g["prive"], "aset": g["aset"],
        },
        "nempel": nempel,
        "persediaan": g["persediaan"], "persediaan_per_kat": g["persediaan_per_kat"],
        "saldo_awal": {m: (saldo_awal or {}).get(m, 0) for m in MEDIA_UANG},
        "saldo_akhir": {m: (saldo_akhir or {}).get(m, 0) for m in MEDIA_UANG},
    }


@router.get("/tren-bulanan")
def tren_bulanan(store_id: Optional[int] = Query(None), bulan: int = Query(6, ge=2, le=12),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Tren N bulan terakhir untuk Owner Space: omzet/hpp/operasional dari BUKU BESAR
    (sumber angka yang sama dengan kartu Arus Kas — lihat /ledger/periode), plus volume
    unit per bulan yang tetap dibaca dari tabel (tidak ada di ledger).

    Dulu rumus tren dihitung terpisah dari tabel Service/Sale/Expense, sehingga
    belanja stok ikut terhitung operasional dan HPP part terpakai hilang. Sekarang
    semua lewat _agregat_ledger() per bulan.
    """
    store, _ = _ctx_read(db, current, store_id)
    n = max(2, min(12, int(bulan or 6)))
    today = datetime.date.today()
    yms = []
    y, m = today.year, today.month
    for _ in range(n):
        yms.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    yms.reverse()
    NAMA_BLN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    b = {ym: {"ym": ym, "label": f"{NAMA_BLN[int(ym[5:7])]} {ym[2:4]}",
              "omzet": 0, "hpp": 0, "operasional": 0, "kotor": 0, "bersih": 0,
              "kas_masuk": 0, "kas_keluar": 0, "kas_bersih": 0,
              "masuk": 0, "sukses": 0, "struk": 0} for ym in yms}

    # --- angka uang: dari buku besar, dikelompokkan per bulan ---
    def _ym_of(v):
        if isinstance(v, datetime.datetime):
            return v.strftime("%Y-%m")
        if isinstance(v, str):
            return v[:7]
        if v:
            return v.strftime("%Y-%m")
        return None

    led = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store.id).all()
    per_bulan = {ym: [] for ym in yms}
    for e in led:
        ym = _ym_of(e.tanggal)
        if ym in per_bulan:
            per_bulan[ym].append(e)
    for ym, rows_ in per_bulan.items():
        if not rows_:
            continue
        g = _agregat_ledger(rows_)
        b[ym]["omzet"] = g["omzet"]
        b[ym]["hpp"] = g["hpp"]
        b[ym]["operasional"] = g["operasional"]
        b[ym]["kas_masuk"] = g["kas_masuk"]
        b[ym]["kas_keluar"] = g["kas_keluar"]
        b[ym]["kas_bersih"] = g["kas_bersih"]

    # --- volume unit: dari tabel (ledger tidak nyimpan "unit") ---
    SUKSES = {"Service Sukses", "Sudah Diambil", "Selesai"}
    for s in db.query(models.Service).filter(models.Service.store_id == store.id).all():
        ym_in = _ym_of(s.date)
        if ym_in in b:
            b[ym_in]["masuk"] += 1
        if (s.status or "") in SUKSES:
            ym_ac = _ym_of(s.diambil_at or s.updated_at or s.date)
            if ym_ac in b:
                b[ym_ac]["sukses"] += 1
    for sl in db.query(models.Sale).filter(models.Sale.store_id == store.id).all():
        ym = _ym_of(sl.tanggal)
        if ym in b:
            b[ym]["struk"] += 1
    out = []
    for ym in yms:
        r = b[ym]
        r["kotor"] = r["omzet"] - r["hpp"]
        r["bersih"] = r["kotor"] - r["operasional"]
        out.append(r)
    return {"store_id": store.id, "bulan": out}


@router.get("/ledger")
def list_ledger(store_id: Optional[int] = Query(None), kategori: Optional[str] = Query(None),
                jenis: Optional[str] = Query(None), media: Optional[str] = Query(None),
                subkategori: Optional[str] = Query(None),
                masuk_laba: Optional[bool] = Query(None),
                since: Optional[str] = Query(None), sampai: Optional[str] = Query(None),
                q: Optional[str] = Query(None, description="cari keterangan"),
                page: Optional[int] = Query(None, ge=1, description="1 = mode ber halaman"),
                per_page: int = Query(50, ge=10, le=200),
                db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Buku besar. Tanpa `page` -> array (perilaku lama, kompat).
    Dengan `page` -> {items, total, page, per_page, total_halaman} supaya tabel owner
    tidak diam-diam memotong di 300 baris.
    `since` = mulai tanggal, `sampai` = akhir tanggal (sebelumnya cuma ada since)."""
    store, _ = _ctx_read(db, current, store_id)
    qy = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store.id)
    if kategori:
        qy = qy.filter(models.LedgerEntry.kategori == kategori)
    if subkategori:
        qy = qy.filter(models.LedgerEntry.subkategori == subkategori)
    if masuk_laba is not None:
        qy = qy.filter(models.LedgerEntry.masuk_laba == masuk_laba)
    if jenis:
        qy = qy.filter(models.LedgerEntry.jenis == jenis)
    if media:
        qy = qy.filter(models.LedgerEntry.media == media)
    if since:
        try:
            d0 = datetime.datetime.strptime(since[:10], "%Y-%m-%d").date()
            qy = qy.filter(models.LedgerEntry.tanggal >= d0)
        except Exception:
            raise HTTPException(status_code=400, detail="since harus YYYY-MM-DD")
    if sampai:
        try:
            d1 = datetime.datetime.strptime(sampai[:10], "%Y-%m-%d").date()
            qy = qy.filter(models.LedgerEntry.tanggal <= d1)
        except Exception:
            raise HTTPException(status_code=400, detail="sampai harus YYYY-MM-DD")
    if q:
        qy = qy.filter(models.LedgerEntry.keterangan.like("%" + q.strip() + "%"))

    qy = qy.order_by(models.LedgerEntry.tanggal.desc(), models.LedgerEntry.id.desc())
    if page is None:
        rows = qy.limit(300).all()
        return [_ledger_row(e) for e in rows]
    total = qy.count()
    total_hal = max(1, -(-total // per_page))
    rows = qy.limit(per_page).offset((page - 1) * per_page).all()
    return {"items": [_ledger_row(e) for e in rows], "total": total, "page": page,
            "per_page": per_page, "total_halaman": total_hal}


@router.post("/ledger")
def create_ledger(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Catat manual ke buku besar: wajib jenis + kategori A-G + media G.
    Karyawan (kasir) boleh catat harian; transfer F1 bukan omzet; DP F3 bukan omzet penuh."""
    store, role = _ctx_write(db, current, store_id)
    jenis = (payload.get("jenis") or "").strip().lower()
    kategori = (payload.get("kategori") or "").strip().upper()
    try:
        nominal = int(payload.get("nominal") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="nominal harus angka")
    media = (payload.get("media") or "").strip().lower()
    mt = (payload.get("media_tujuan") or "").strip().lower() or None
    keterangan = (payload.get("keterangan") or "").strip() or None
    # Transfer antar kas = kewenangan owner/admin (bukan kasir/teknisi).
    if kategori == "F1" or jenis == "transfer":
        if role not in ("superadmin", "owner", "admin"):
            raise HTTPException(status_code=403,
                                detail="Hanya owner/admin yang boleh transfer antar kas")
        if media not in MEDIA_UANG or mt not in MEDIA_UANG:
            raise HTTPException(status_code=400,
                                detail="Transfer hanya antar media uang (bukan stok)")
        saldo_asal = int(_sistem_media(db, store.id).get(media, 0) or 0)
        if nominal > saldo_asal:
            fmt = lambda x: f"{int(x):,}".replace(",", ".")
            raise HTTPException(
                status_code=400,
                detail=(f"Saldo {lm.MEDIA.get(media, media)} tidak cukup: "
                        f"tersedia Rp{fmt(max(0, saldo_asal))}, diminta Rp{fmt(nominal)}"))
    subkategori = (payload.get("subkategori") or "").strip() or None
    masuk_laba = payload.get("masuk_laba", True)
    masuk_laba = False if masuk_laba is False or str(masuk_laba).lower() in ("0", "false", "no") else True
    pengaruh_kas = payload.get("pengaruh_kas", True)
    pengaruh_kas = False if pengaruh_kas is False or str(pengaruh_kas).lower() in ("0", "false", "no") else True
    # Prinsip mentor: media stok = persediaan, bukan uang tunai — paksa tanpa gerak kas
    # agar saldo per media + selisih tutup kas tidak kotor.
    if media == "stok":
        pengaruh_kas = False
    row = _ledger_add(db, store.id, _parse_tgl(payload.get("tanggal")), jenis, kategori,
                      keterangan, nominal, media, mt,
                      ref_type="manual", ref_id=None, oleh=getattr(current, "username", None),
                      subkategori=subkategori, masuk_laba=masuk_laba, pengaruh_kas=pengaruh_kas)
    db.commit()
    db.refresh(row)
    log_action(db, "finance.ledger", target=f"LED-{row.id}",
               detail=f"{jenis} {kategori} {nominal} via {media}",
               actor=current, store_id=store.id)
    return _ledger_row(row)


@router.delete("/ledger/{led_id}")
def delete_ledger(led_id: int, store_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Hapus baris MANUAL saja. Baris auto (expense/income) dihapus dari modul sumbernya."""
    store, _ = _ctx(db, current, store_id)
    e = db.query(models.LedgerEntry).filter(models.LedgerEntry.id == led_id,
                                            models.LedgerEntry.store_id == store.id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Baris buku besar tidak ditemukan di toko ini")
    if (e.ref_type or "manual") != "manual":
        raise HTTPException(status_code=400, detail=f"Baris auto dari {e.ref_type} — hapus dari modul sumbernya")
    info = f"{e.jenis} {e.kategori} nominal={e.nominal}"
    db.delete(e)
    db.commit()
    log_action(db, "finance.ledger_hapus", target=f"LED-{led_id}",
               detail=info, actor=current, store_id=store.id)
    return {"ok": True, "id": led_id}


def _sistem_media(db, store_id: int):
    """Saldo sistem per media dari buku besar s/d HARI INI (transfer menggeser kedua sisi).
    Hanya baris pengaruh_kas (HPP terbentuk tanpa gerak kas dikecualikan)."""
    rows = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store_id).all()
    return _saldo_media(rows)


def _sistem_media_sampai(db, store_id: int, sampai):
    """Saldo sistem per media s/d tanggal tertentu — untuk Tutup Kas tanggal lama,
    supaya kolom 'Sistem' bukan lagi saldo hari ini."""
    rows = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store_id).all()
    upto = []
    for e in rows:
        v = e.tanggal
        if isinstance(v, datetime.datetime):
            v = v.date()
        if isinstance(v, str):
            try:
                v = datetime.datetime.strptime(v[:10], "%Y-%m-%d").date()
            except Exception:
                continue
        if v and v <= sampai:
            upto.append(e)
    return _saldo_media(upto)


@router.get("/cash/config")
def get_cash_config(store_id: Optional[int] = Query(None),
                    db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    cfg = db.query(models.CashConfig).filter(models.CashConfig.store_id == store.id).first()
    return {"store_id": store.id,
            "kas_kecil_limit": cfg.kas_kecil_limit if cfg else lm.KAS_KECIL_DEFAULT,
            "disetel": bool(cfg)}


@router.put("/cash/config")
def put_cash_config(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                    db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Set limit Kas Kecil (petty cash mentor). Owner/admin saja."""
    store, _ = _ctx(db, current, store_id)
    try:
        limit = int(payload.get("kas_kecil_limit") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="kas_kecil_limit harus angka")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="kas_kecil_limit harus > 0")
    cfg = db.query(models.CashConfig).filter(models.CashConfig.store_id == store.id).first()
    if not cfg:
        cfg = models.CashConfig(store_id=store.id)
        db.add(cfg)
    cfg.kas_kecil_limit = limit
    cfg.updated_oleh = getattr(current, "username", None)
    db.commit()
    db.refresh(cfg)
    log_action(db, "finance.kas_kecil", target=f"store-{store.id}",
               detail=f"limit kas kecil = {limit}", actor=current, store_id=store.id)
    return {"store_id": store.id, "kas_kecil_limit": cfg.kas_kecil_limit, "disetel": True}


@router.get("/cash/close")
def get_cash_close(tanggal: Optional[str] = Query(None), store_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Tutup kas tanggal tertentu + snapshot sistem per media S/D TANGGAL ITU.

    Penting: 'sistem' dulu selalu dihitung s/d HARI INI, jadi buka tanggal lama
    menampilkan angka hari ini (Rp4 juta selisih buat data 9 Okt). Sekarang as-of tanggal.
    """
    store, _ = _ctx_read(db, current, store_id)
    tgl = _parse_tgl(tanggal) if tanggal else datetime.date.today()
    c = db.query(models.CashClose).filter(models.CashClose.store_id == store.id,
                                          models.CashClose.tanggal == tgl).first()
    out = None
    if c:
        out = {"tanggal": c.tanggal, "sistem": {"kas_utama": c.kas_utama_sistem,
               "kas_kecil": c.kas_kecil_sistem, "bank": c.bank_sistem, "qris": c.qris_sistem},
               "fisik": {"kas_utama": c.kas_utama_fisik, "kas_kecil": c.kas_kecil_fisik,
               "bank": c.bank_fisik, "qris": c.qris_fisik},
               "selisih": c.selisih, "catatan": c.catatan, "ditutup_oleh": c.ditutup_oleh}
    # Hanya media uang — samakan bentuknya dengan POST /cash/close yang menghitung
    # selisih dari MEDIA_UANG. 'stok' bukan tempat uang (selalu 0, bukan kas fisik).
    sistem = {m: v for m, v in _sistem_media_sampai(db, store.id, tgl).items() if m in MEDIA_UANG}
    return {"tanggal": tgl, "tutup": out, "sistem": sistem}


@router.get("/cash/close/riwayat")
def riwayat_tutup_kas(limit: int = Query(30, ge=1, le=365),
                      store_id: Optional[int] = Query(None),
                      db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Daftar tutup kas terakhir + statistik disiplin (berapa hari telat / sering selisih).

    Tanpa ini tidak ada cara lihat "toko ini rutin selisih atau tidak" — ritual yang
    tidak dipantau tidak pernah dikerjakan.
    """
    store, _ = _ctx_read(db, current, store_id)
    rows = (db.query(models.CashClose)
              .filter(models.CashClose.store_id == store.id)
              .order_by(models.CashClose.tanggal.desc())
              .limit(limit).all())
    today = datetime.date.today()
    items = []
    for c in rows:
        f = sum(int(x or 0) for x in (c.kas_utama_fisik, c.kas_kecil_fisik, c.bank_fisik, c.qris_fisik))
        items.append({
            "tanggal": c.tanggal, "fisik": f, "selisih": int(c.selisih or 0),
            "sistem": sum(int(x or 0) for x in (c.kas_utama_sistem, c.kas_kecil_sistem,
                                                c.bank_sistem, c.qris_sistem)),
            "catatan": c.catatan, "ditutup_oleh": c.ditutup_oleh,
        })
    n = len(items)
    bersih = sum(1 for i in items if i["selisih"] == 0)
    # hari tanpa tutup kas dalam 30 hari terakhir
    ada = {i["tanggal"] for i in items}
    bolong = []
    for k in range(1, 31):
        d = today - datetime.timedelta(days=k)
        if d not in ada:
            bolong.append(d)
    return {
        "items": items, "jumlah": n, "selisih_nol": bersih,
        "persen_bersih": round(bersih * 100 / n) if n else 0,
        "rata_selisih": round(sum(abs(i["selisih"]) for i in items) / n) if n else 0,
        "hari_bolong_30": len(bolong),
        "bolong_contoh": sorted(bolong, reverse=True)[:10],
        "hari_ini_sudah": today in ada,
    }


@router.post("/cash/close")
def post_cash_close(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                    db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Ritual TUTUP KAS malam: cocokkan fisik vs sistem per media. Selisih target Rp0.
    Tulis: owner/admin/kasir (kasir tutup kasirannya malam ini).
    Sistem dihitung AS-OF tanggal yang dipilih, bukan s/d hari ini."""
    store, _ = _ctx_write(db, current, store_id)
    tgl = _parse_tgl(payload.get("tanggal"))
    fisik = payload.get("fisik") or {}
    try:
        # cuma media uang — 'stok' bukan tempat uang, jangan ikut dijumlahkan
        f = {m: int(fisik.get(m) or 0) for m in MEDIA_UANG}
    except Exception:
        raise HTTPException(status_code=400, detail="fisik harus angka per media")
    if any(v < 0 for v in f.values()):
        raise HTTPException(status_code=400, detail="fisik tidak boleh negatif")
    sist_all = _sistem_media_sampai(db, store.id, tgl)
    sist = {m: int(sist_all.get(m, 0)) for m in MEDIA_UANG}
    selisih = sum(f.values()) - sum(sist.values())
    c = db.query(models.CashClose).filter(models.CashClose.store_id == store.id,
                                          models.CashClose.tanggal == tgl).first()
    baru = c is None
    if not c:
        c = models.CashClose(store_id=store.id, tanggal=tgl)
        db.add(c)
    elif (int(c.selisih or 0) or 0) != selisih:
        # koreksi tutup kas sebelumnya = jejak, jangan ditimpa diam-diam
        log_action(db, "finance.tutup_kas_koreksi", target=str(tgl),
                   detail=f"selisih {c.selisih} -> {selisih}; fisik lama "
                          f"{sum(int(x or 0) for x in (c.kas_utama_fisik, c.kas_kecil_fisik, c.bank_fisik, c.qris_fisik))} -> {sum(f.values())}",
                   actor=current, store_id=store.id)
    c.kas_utama_sistem = sist["kas_utama"]
    c.kas_kecil_sistem = sist["kas_kecil"]
    c.bank_sistem = sist["bank"]
    c.qris_sistem = sist["qris"]
    c.kas_utama_fisik = f["kas_utama"]
    c.kas_kecil_fisik = f["kas_kecil"]
    c.bank_fisik = f["bank"]
    c.qris_fisik = f["qris"]
    c.selisih = selisih
    c.catatan = (payload.get("catatan") or "").strip() or None
    c.ditutup_oleh = getattr(current, "username", None)
    db.commit()
    db.refresh(c)
    log_action(db, "finance.tutup_kas", target=str(tgl),
               detail=f"{'buat' if baru else 'koreksi'} selisih={selisih} "
                      f"fisik={sum(f.values())} sistem={sum(sist.values())}",
               actor=current, store_id=store.id)
    return {"tanggal": c.tanggal, "sistem": sist, "fisik": f,
            "selisih": selisih, "ok": selisih == 0, "baru": baru}


# ================= TUTUP BUKU MINGGUAN =================
@router.get("/weekly-close/preview")
def weekly_close_preview(tanggal: Optional[str] = Query(None),
                         store_id: Optional[int] = Query(None),
                         db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Pratinjau tutup buku minggu Senin..Sabtu: jatah teknisi, kas saat ini,
    dan sisa yang akan disetor ke owner. Tidak mengubah apa pun."""
    store, _ = _ctx_read(db, current, store_id)
    tgl = _parse_tgl(tanggal) if tanggal else datetime.date.today()
    week_start, week_end = _week_bounds(tgl)
    today = datetime.date.today()
    rows = _weekly_tech_rows(db, store.id, week_start, week_end)
    cash = _weekly_cash(db, store.id)
    butuh = sum(max(0, int(r["sisa"] or 0)) for r in rows)
    kas_utama = int(cash.get("kas_utama", 0))
    kas_tersedia = sum(max(0, int(v or 0)) for v in cash.values())
    kurang = max(0, butuh - max(0, kas_utama))
    kurang_total = max(0, butuh - kas_tersedia)
    wc = db.query(models.WeeklyClose).filter(
        models.WeeklyClose.store_id == store.id,
        models.WeeklyClose.week_start == week_start).first()
    return {
        "store_id": store.id, "tanggal": today,
        "week_start": week_start, "week_end": week_end,
        # Jendela setor kas: Jumat (persiapan) s/d Minggu (menyusul).
        "aktif": -1 <= (today - week_end).days <= 1,
        "boleh_proses": week_start <= today,
        "teknisi": rows,
        "total_netto": sum(r["netto"] for r in rows),
        "total_tunggakan": sum(r["tunggakan"] for r in rows),
        "total_sisa": butuh,
        "sudah_dibayar": sum(r["sudah_dibayar"] for r in rows),
        "butuh_gajian": butuh, "kas_utama": kas_utama,
        "kas_tersedia": kas_tersedia,
        "kurang_gajian": kurang, "kurang_total": kurang_total,
        "cukup_gajian": kurang == 0,
        "kas": cash, "kas_total": sum(cash.values()),
        "sudah_ditutup": {
            "id": wc.id, "tanggal": wc.week_end, "total_gajian": wc.total_gajian,
            "total_prive": wc.total_prive, "saldo_akhir": wc.saldo_akhir,
            "catatan": wc.catatan, "ditutup_oleh": wc.ditutup_oleh,
            "created_at": wc.created_at,
        } if wc else None,
    }


@router.post("/weekly-close")
def weekly_close(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Tutup buku manual: bayar jatah teknisi minggu ini (yang belum dibayar) lalu
    setor sisa kas ke owner (E2 Prive) agar Senin saldo kembali nol.

    - Nominal SELALU dihitung server, bukan dari frontend.
    - Gajian yang sudah dibayar tidak dobel; kalau masih kurang, baris payout
      minggu itu ditambah (koreksi), bukan dibuat baris baru.
    - Setor kas hanya untuk minggu aktif (Sabtu/Minggu) agar tidak menyapu kas
      minggu berjalan saat menutup minggu lama.
    """
    store, _ = _ctx_write(db, current, store_id)
    tgl = _parse_tgl(payload.get("tanggal")) if payload.get("tanggal") else datetime.date.today()
    week_start, week_end = _week_bounds(tgl)
    today = datetime.date.today()
    if week_start > today:
        raise HTTPException(status_code=400, detail="Minggu belum berjalan")
    # Gajian boleh dibayar lebih awal (mis. Jumat), tetapi setor kas hanya
    # dalam jendela Jumat..Minggu supaya kas minggu berjalan tidak tersapu.
    aktif = -1 <= (today - week_end).days <= 1
    bayar = bool(payload.get("bayar_gajian", True))
    setor = bool(payload.get("setor_kas", True))
    boleh_setor = setor and aktif
    try:
        keep = {m: max(0, int((payload.get("sisakan") or {}).get(m) or 0)) for m in MEDIA_UANG}
    except Exception:
        raise HTTPException(status_code=400, detail="sisakan harus angka per media")
    catatan = (payload.get("catatan") or "").strip() or None
    oleh = getattr(current, "username", None)

    rows = _weekly_tech_rows(db, store.id, week_start, week_end)
    # Jangan pernah membuat kas utama minus: gajian dibayar dari kas utama.
    butuh = sum(max(0, int(t["sisa"] or 0)) for t in rows) if bayar else 0
    kas_awal = _weekly_cash(db, store.id)
    kas_utama = int(kas_awal.get("kas_utama", 0))
    if bayar and butuh > max(0, kas_utama):
        kurang = butuh - max(0, kas_utama)
        fmt = lambda x: f"{int(x):,}".replace(",", ".")
        raise HTTPException(
            status_code=400,
            detail=("Kas utama tidak cukup untuk membayar tunggakan teknisi. "
                    f"Butuh Rp{fmt(butuh)}, tersedia Rp{fmt(max(0, kas_utama))}, "
                    f"kurang Rp{fmt(kurang)}. Setor dana ke kas utama dulu, "
                    "lalu ulangi tutup buku."))
    total_gajian = 0
    paid_detail = []
    if bayar:
        for t in rows:
            sisa = int(t["sisa"] or 0)
            if sisa <= 0:
                continue
            ex = db.query(models.LedgerEntry).filter(
                models.LedgerEntry.store_id == store.id,
                models.LedgerEntry.ref_type == "gajian",
                models.LedgerEntry.ref_id == t["technician_id"],
                models.LedgerEntry.keterangan.like(f"%{week_start.isoformat()}%")).all()
            if ex:
                row = ex[0]
                row.nominal = int(row.nominal or 0) + sisa
                row.dibuat_oleh = oleh
                topup = True
            else:
                row = _ledger_add(db, store.id, today, "keluar", "C1",
                                  f"Gajian {t['nama']} {week_start.isoformat()} (komisi+hadir)",
                                  sisa, "kas_utama", ref_type="gajian",
                                  ref_id=t["technician_id"], oleh=oleh,
                                  masuk_laba=False, pengaruh_kas=True, skip_dup=True)
                topup = False
            total_gajian += sisa
            paid_detail.append({"technician_id": t["technician_id"], "nama": t["nama"],
                                "nominal": sisa, "topup": topup})
    if total_gajian:
        db.flush()

    kas_sebelum = _weekly_cash(db, store.id)
    total_prive = 0
    sweep = {}
    if boleh_setor:
        for m in MEDIA_UANG:
            sisa_setor = int(kas_sebelum.get(m, 0)) - int(keep.get(m, 0))
            if sisa_setor <= 0:
                continue
            _ledger_add(db, store.id, today, "keluar", "E2",
                        f"Tutup buku {week_start.isoformat()}: setor kas {m} ke owner",
                        sisa_setor, m, oleh=oleh, masuk_laba=True, pengaruh_kas=True)
            sweep[m] = sisa_setor
            total_prive += sisa_setor
        if total_prive:
            db.flush()

    saldo_akhir = _weekly_cash(db, store.id)
    # Total minggu (termasuk pembayaran manual sebelum tutup buku), bukan cuma run ini.
    week_paid = sum(int(p.nominal or 0) for p in db.query(models.LedgerEntry).filter(
        models.LedgerEntry.store_id == store.id,
        models.LedgerEntry.ref_type == "gajian",
        models.LedgerEntry.keterangan.like(f"%{week_start.isoformat()}%")).all())
    week_prive = sum(int(p.nominal or 0) for p in db.query(models.LedgerEntry).filter(
        models.LedgerEntry.store_id == store.id,
        models.LedgerEntry.kategori == "E2",
        models.LedgerEntry.keterangan.like(f"Tutup buku {week_start.isoformat()}%")).all())
    detail = {
        "teknisi": rows, "kas_sebelum": kas_sebelum, "sisakan": keep,
        "setor": sweep, "gajian": paid_detail,
    }
    wc = db.query(models.WeeklyClose).filter(
        models.WeeklyClose.store_id == store.id,
        models.WeeklyClose.week_start == week_start).first()
    if not wc:
        wc = models.WeeklyClose(store_id=store.id, week_start=week_start)
        db.add(wc)
    wc.week_end = week_end
    wc.total_gajian = week_paid
    wc.total_prive = week_prive
    wc.saldo_akhir = sum(saldo_akhir.values())
    wc.detail_json = json.dumps(detail, default=str)
    wc.catatan = catatan
    wc.ditutup_oleh = oleh
    db.commit()
    db.refresh(wc)
    log_action(db, "finance.tutup_buku", target=week_start.isoformat(),
               detail=f"gajian={total_gajian} prive={total_prive} saldo_akhir={wc.saldo_akhir} "
                      f"aktif={aktif} setor={setor}",
               actor=current, store_id=store.id)
    return {
        "ok": True, "week_start": week_start, "week_end": week_end,
        "total_gajian": total_gajian, "total_prive": total_prive,
        "total_gajian_minggu": week_paid, "total_prive_minggu": week_prive,
        "gajian": paid_detail, "setor": sweep, "sisakan": keep,
        "saldo_akhir": saldo_akhir, "saldo_total": wc.saldo_akhir,
        "boleh_setor": boleh_setor,
        "pesan": ("Saldo kas sudah disetor. Senin mulai dari nol."
                  if boleh_setor and total_prive else
                  ("Minggu lama: kas tidak disetor agar kas minggu berjalan tidak ikut tersapu."
                   if setor and not aktif else "Tutup buku tersimpan.")),
    }


@router.get("/weekly-close/riwayat")
def weekly_close_riwayat(limit: int = Query(12, ge=1, le=104),
                         store_id: Optional[int] = Query(None),
                         db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    rows = (db.query(models.WeeklyClose)
              .filter(models.WeeklyClose.store_id == store.id)
              .order_by(models.WeeklyClose.week_start.desc())
              .limit(limit).all())
    return {"items": [{
        "id": w.id, "week_start": w.week_start, "week_end": w.week_end,
        "total_gajian": w.total_gajian, "total_prive": w.total_prive,
        "saldo_akhir": w.saldo_akhir, "catatan": w.catatan,
        "ditutup_oleh": w.ditutup_oleh, "created_at": w.created_at,
    } for w in rows]}


def _wa_quote(t: str) -> str:
    from urllib.parse import quote
    return quote(t or "")
