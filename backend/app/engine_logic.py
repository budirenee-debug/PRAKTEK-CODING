"""Business Engine core: kategori auto, kuota 2:1, cair komisi + cicilan 20%."""
import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import models


def get_settings(db: Session, store_id: int) -> models.StoreSettings:
    s = db.query(models.StoreSettings).filter(models.StoreSettings.store_id == store_id).first()
    if not s:
        s = models.StoreSettings(store_id=store_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def suggest_kategori(keluhan: str, sett: models.StoreSettings) -> str:
    text = (keluhan or "").upper()
    berats = [(k.strip().upper()) for k in (sett.keyword_berat or "").split(",") if k.strip()]
    ringans = [(k.strip().upper()) for k in (sett.keyword_ringan or "").split(",") if k.strip()]
    for kw in berats:
        if kw and kw in text:
            return "berat"
    for kw in ringans:
        if kw and kw in text:
            return "ringan"
    return "ringan"


def tech_level(db: Session, store_id: int, teknisi_nama: str) -> str:
    if not teknisi_nama:
        return "junior"
    t = db.query(models.Technician).filter(
        models.Technician.store_id == store_id,
        models.Technician.nama.ilike(teknisi_nama)).first()
    return (t.level or "junior") if t else "junior"


def tech_id(db: Session, store_id: int, teknisi_nama: str):
    if not teknisi_nama:
        return None
    t = db.query(models.Technician).filter(
        models.Technician.store_id == store_id,
        models.Technician.nama.ilike(teknisi_nama)).first()
    return t.id if t else None


def check_quota(db: Session, store, teknisi_nama: str, kategori: str):
    """Enforce 2:1 harian untuk senior. Junior bebas. Raise 400 jika melanggar."""
    if not teknisi_nama or (kategori or "ringan") != "ringan":
        return
    if tech_level(db, store.id, teknisi_nama) != "senior":
        return
    sett = get_settings(db, store.id)
    rasio = sett.kuota_ringan_per_berat or 2
    today = datetime.date.today()
    berats = db.query(models.ServiceEngine).join(
        models.Service, models.Service.invoice == models.ServiceEngine.invoice
    ).filter(
        models.ServiceEngine.store_id == store.id,
        models.ServiceEngine.kategori == "berat",
        models.Service.date == today,
        models.Service.teknisi.ilike(f"%{teknisi_nama}%")).count()
    ringans = db.query(models.ServiceEngine).join(
        models.Service, models.Service.invoice == models.ServiceEngine.invoice
    ).filter(
        models.ServiceEngine.store_id == store.id,
        models.ServiceEngine.kategori == "ringan",
        models.Service.date == today,
        models.Service.teknisi.ilike(f"%{teknisi_nama}%")).count()
    if ringans >= berats * rasio:
        raise HTTPException(
            status_code=400,
            detail=f"Kuota ringan habis (2:1 harian). {teknisi_nama} berat={berats}, ringan={ringans}. Ambil kasus berat dulu.")


def ensure_engine_row(db: Session, svc: models.Service, kategori_manual, harga_up: int, modal: int):
    sett = get_settings(db, svc.store_id)
    kategori = (kategori_manual or "").lower() if kategori_manual else suggest_kategori(svc.keluhan, sett)
    if kategori not in ("berat", "ringan"):
        kategori = "ringan"
    harga_up = int(harga_up or 0)
    modal = int(modal or 0)
    jasa = max(0, int(svc.biaya or 0) - harga_up)
    lvl = tech_level(db, svc.store_id, svc.teknisi)
    pct = (sett.komisi_senior if lvl == "senior" else sett.komisi_junior) or 0
    komisi = jasa * pct // 100
    row = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == svc.invoice).first()
    if not row:
        row = models.ServiceEngine(invoice=svc.invoice, store_id=svc.store_id)
        db.add(row)
    row.kategori = kategori
    row.harga_part_up = harga_up
    row.modal_asli = modal
    row.jasa_bersih = jasa
    row.komisi_teknisi = komisi
    # status pending untuk baru; yg lama tetap (backfill sudah cair)
    if not row.komisi_status:
        row.komisi_status = "pending"
    db.commit()
    db.refresh(row)
    return row


def cairkan(db: Session, svc: models.Service, actor=None):
    """CAIR saat Sudah Diambil. Hitung ulang jasa/komisi, potong hutang max 20%, tulis ledger. Idempotent."""
    row = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == svc.invoice).first()
    if not row:
        row = ensure_engine_row(db, svc, None, 0, 0)
    if (row.komisi_status or "") == "cair":
        return row
    sett = get_settings(db, svc.store_id)
    # hitung ulang dari snapshot terakhir
    jasa = max(0, int(svc.biaya or 0) - int(row.harga_part_up or 0))
    lvl = tech_level(db, svc.store_id, svc.teknisi)
    pct = (sett.komisi_senior if lvl == "senior" else sett.komisi_junior) or 0
    komisi = jasa * pct // 100
    row.jasa_bersih = jasa
    row.komisi_teknisi = komisi
    tid = tech_id(db, svc.store_id, svc.teknisi)
    if not tid or komisi <= 0:
        row.komisi_status = "cair"
        db.commit()
        return row
    # hutang belum lunas
    debts = db.query(models.TechDebt).filter(
        models.TechDebt.technician_id == tid,
        models.TechDebt.status == "belum").order_by(models.TechDebt.id).all()
    sisa_total = sum((d.sisa or 0) for d in debts)
    potong_total = 0
    if sisa_total > 0:
        max_pot = komisi * (sett.cicilan_max_pct or 20) // 100
        sisa_budget = max_pot
        for d in debts:
            if sisa_budget <= 0:
                break
            ambil = min(d.sisa, sisa_budget)
            d.sisa -= ambil
            d.sudah_dicicil = (d.sudah_dicicil or 0) + ambil
            if d.sisa <= 0:
                d.sisa = 0
                d.status = "lunas"
            sisa_budget -= ambil
            potong_total += ambil
    today = datetime.date.today()
    sisa_sesudah = sisa_total - potong_total
    if komisi > 0:
        db.add(models.CommissionLedger(
            store_id=svc.store_id, technician_id=tid, tanggal=today, invoice=svc.invoice,
            tipe="komisi_cair", masuk_rp=komisi - potong_total, keluar_rp=0,
            sisa_hutang_saat_itu=sisa_sesudah,
            keterangan=f"{svc.invoice} {row.kategori} {pct}%"))
    if potong_total > 0:
        db.add(models.CommissionLedger(
            store_id=svc.store_id, technician_id=tid, tanggal=today, invoice=svc.invoice,
            tipe="potongan_cicilan", masuk_rp=0, keluar_rp=potong_total,
            sisa_hutang_saat_itu=sisa_sesudah,
            keterangan=f"Cicil hutang max {sett.cicilan_max_pct}% dari {svc.invoice}"))
    row.komisi_status = "cair"
    db.commit()
    db.refresh(row)
    return row
