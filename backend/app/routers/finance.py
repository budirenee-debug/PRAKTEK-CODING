"""Keuangan ekstraf: Kecelakaan Kerja + Refund Dana (Owner Space)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from ..database import get_db
from .. import models
from ..audit import log_action
from ..store_ctx import resolve_store, store_role, default_store
from .. import engine_logic as el
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
        q = q.filter(models.Expense.kategori == kategori)
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
    """Catat pengeluaran operasional. Tulis: owner/admin/kasir/superadmin (kasir dari Kas Toko). Hapus tetap owner/admin."""
    store, _ = _ctx_write(db, current, store_id)
    keperluan = (payload.get("keperluan") or "").strip()
    if not keperluan:
        raise HTTPException(status_code=400, detail="keperluan wajib diisi")
    nominal = int(payload.get("nominal") or 0)
    if nominal <= 0:
        raise HTTPException(status_code=400, detail="nominal harus > 0")
    kategori = (payload.get("kategori") or "Operasional").strip()
    if kategori not in KAT_EXPENSE:
        raise HTTPException(status_code=400, detail="kategori harus: " + "/".join(KAT_EXPENSE))
    metode = (payload.get("metode") or "Tunai").strip()
    if metode not in METODE:
        raise HTTPException(status_code=400, detail="metode harus Tunai/Transfer/QRIS")
    e = models.Expense(store_id=store.id, tanggal=_parse_tgl(payload.get("tanggal")),
                       kategori=kategori, keperluan=keperluan, nominal=nominal,
                       metode=metode,
                       keterangan=(payload.get("keterangan") or "").strip() or None,
                       dibuat_oleh=getattr(current, "username", None))
    db.add(e)
    db.commit()
    db.refresh(e)
    log_action(db, "finance.expense", target=f"EXP-{e.id}",
               detail=f"{kategori} {keperluan} nominal={nominal} metode={metode}",
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
    db.delete(e)
    db.commit()
    log_action(db, "finance.income_hapus", target=f"IN-{inc_id}",
               detail=info, actor=current, store_id=store.id)
    return {"ok": True, "id": inc_id}


def _wa_quote(t: str) -> str:
    from urllib.parse import quote
    return quote(t or "")
