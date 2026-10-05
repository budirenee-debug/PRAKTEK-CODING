"""Keuangan ekstraf: Kecelakaan Kerja + Refund Dana (Owner Space)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
import datetime

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
                subkategori=None, masuk_laba=True, pengaruh_kas=True):
    """Tambah 1 baris buku besar (tanpa commit — caller yang commit).
    Guard duplikat dual-write via (ref_type, ref_id).
    Prinsip mentor: masuk_laba=False = persediaan (belum HPP); pengaruh_kas=False = tanpa gerak kas."""
    err = lm.validate_entry(kategori, jenis, nominal, media, media_tujuan)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if kategori == "D" and (subkategori or "") not in lm.SUB_D:
        raise HTTPException(status_code=400, detail="kategori D wajib subkategori: " + "/".join(lm.SUB_D))
    if ref_type and ref_id is not None:
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
    """5 angka mentor dari buku besar: omzet − HPP = laba kotor − operasional = laba bersih.
    Prinsip mentor: hanya baris masuk_laba yang hitung laba (persediaan dikecualikan);
    omzet = masuk − pengurang (refund); arus/media hanya yang pengaruh_kas."""
    store, _ = _ctx_read(db, current, store_id)
    rows = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store.id).all()
    g = {"omzet": 0, "hpp": 0, "operasional": 0, "aset": 0,
         "modal": 0, "prive": 0, "non_masuk": 0, "non_keluar": 0,
         "total_masuk": 0, "total_keluar": 0, "persediaan": 0}
    for e in rows:
        n = int(e.nominal or 0)
        kel = lm.kelompok_of(e.kategori or "")
        laba = e.masuk_laba is not False
        kas = e.pengaruh_kas is not False
        if e.jenis == "transfer":
            continue  # F1 pindah media, bukan omzet/biaya
        if e.jenis == "masuk":
            if kas:
                g["total_masuk"] += n
            if not laba:
                continue
            if kel == "omzet":
                g["omzet"] += n
            elif kel == "owner":
                g["modal"] += n
            elif kel == "non":
                g["non_masuk"] += n
        elif e.jenis == "keluar":
            if kas:
                g["total_keluar"] += n
            if kel == "hpp" and not laba:
                g["persediaan"] += n  # beli barang: kas keluar, stok bertambah, BELUM HPP
                continue
            if not laba:
                continue
            if kel == "hpp":
                g["hpp"] += n
            elif kel == "omzet":
                g["omzet"] -= n  # refund: pengurang omzet
            elif kel == "operasional":
                g["operasional"] += n
            elif kel == "aset":
                g["aset"] += n
            elif kel == "owner":
                g["prive"] += n
            elif kel == "non":
                g["non_keluar"] += n
    kotor = g["omzet"] - g["hpp"]
    return {**g, "laba_kotor": kotor, "laba_bersih": kotor - g["operasional"],
            "arus_bersih": g["total_masuk"] - g["total_keluar"],
            "per_media": _sistem_media(db, store.id), "count": len(rows)}


@router.get("/ledger")
def list_ledger(store_id: Optional[int] = Query(None), kategori: Optional[str] = Query(None),
                jenis: Optional[str] = Query(None), media: Optional[str] = Query(None),
                subkategori: Optional[str] = Query(None),
                masuk_laba: Optional[bool] = Query(None),
                since: Optional[str] = Query(None), limit: int = Query(300, le=1000),
                db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_read(db, current, store_id)
    q = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store.id)
    if kategori:
        q = q.filter(models.LedgerEntry.kategori == kategori)
    if subkategori:
        q = q.filter(models.LedgerEntry.subkategori == subkategori)
    if masuk_laba is not None:
        q = q.filter(models.LedgerEntry.masuk_laba == masuk_laba)
    if jenis:
        q = q.filter(models.LedgerEntry.jenis == jenis)
    if media:
        q = q.filter(models.LedgerEntry.media == media)
    if since:
        try:
            d0 = datetime.datetime.strptime(since[:10], "%Y-%m-%d").date()
            q = q.filter(models.LedgerEntry.tanggal >= d0)
        except Exception:
            raise HTTPException(status_code=400, detail="since harus YYYY-MM-DD")
    rows = q.order_by(models.LedgerEntry.tanggal.desc(), models.LedgerEntry.id.desc()).limit(limit).all()
    return [_ledger_row(e) for e in rows]


@router.post("/ledger")
def create_ledger(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Catat manual ke buku besar: wajib jenis + kategori A-G + media G.
    Karyawan (kasir) boleh catat harian; transfer F1 bukan omzet; DP F3 bukan omzet penuh."""
    store, _ = _ctx_write(db, current, store_id)
    jenis = (payload.get("jenis") or "").strip().lower()
    kategori = (payload.get("kategori") or "").strip().upper()
    try:
        nominal = int(payload.get("nominal") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="nominal harus angka")
    media = (payload.get("media") or "").strip().lower()
    mt = (payload.get("media_tujuan") or "").strip().lower() or None
    keterangan = (payload.get("keterangan") or "").strip() or None
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
    """Saldo sistem per media dari buku besar (transfer menggeser kedua sisi).
    Hanya baris pengaruh_kas (HPP terbentuk tanpa gerak kas dikecualikan)."""
    saldo = {m: 0 for m in lm.MEDIA.keys()}
    rows = db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store_id).all()
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
    """Ambil tutup kas tanggal tertentu + snapshot sistem per media saat ini."""
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
    return {"tanggal": tgl, "tutup": out, "sistem": _sistem_media(db, store.id)}


@router.post("/cash/close")
def post_cash_close(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                    db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Ritual TUTUP KAS malam: cocokkan fisik vs sistem per media. Selisih target Rp0.
    Tulis: owner/admin/kasir (kasir tutup kasirannya malam ini)."""
    store, _ = _ctx_write(db, current, store_id)
    tgl = _parse_tgl(payload.get("tanggal"))
    fisik = payload.get("fisik") or {}
    try:
        f = {m: int(fisik.get(m) or 0) for m in lm.MEDIA.keys()}
    except Exception:
        raise HTTPException(status_code=400, detail="fisik harus angka per media")
    if any(v < 0 for v in f.values()):
        raise HTTPException(status_code=400, detail="fisik tidak boleh negatif")
    sist = _sistem_media(db, store.id)
    selisih = sum(f.values()) - sum(sist.values())
    c = db.query(models.CashClose).filter(models.CashClose.store_id == store.id,
                                          models.CashClose.tanggal == tgl).first()
    if not c:
        c = models.CashClose(store_id=store.id, tanggal=tgl)
        db.add(c)
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
               detail=f"selisih={selisih} fisik={sum(f.values())} sistem={sum(sist.values())}",
               actor=current, store_id=store.id)
    return {"tanggal": c.tanggal, "sistem": sist, "fisik": f,
            "selisih": selisih, "ok": selisih == 0}


def _wa_quote(t: str) -> str:
    from urllib.parse import quote
    return quote(t or "")
