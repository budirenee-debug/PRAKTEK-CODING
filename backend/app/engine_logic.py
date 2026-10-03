"""Business Engine core: kategori auto, kuota 2:1, cair komisi + cicilan 20%."""
import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import models
from . import ledger_meta as lm


def _ledger_post_safe(db: Session, store_id, tanggal, jenis, kategori, keterangan,
                      nominal, media, ref_type, invoice, oleh,
                      subkategori=None, masuk_laba=True, pengaruh_kas=True):
    """Post buku besar anti-gagal: tidak boleh menggagalkan alur cair/service.
    Service ber-PK invoice string → guard duplikat via ref_type + invoice di keterangan."""
    try:
        from .routers.finance import _ledger_add
        dup = db.query(models.LedgerEntry).filter(
            models.LedgerEntry.store_id == store_id,
            models.LedgerEntry.ref_type == ref_type,
            models.LedgerEntry.keterangan.like(f"%{invoice}%")).first()
        if dup:
            return dup
        return _ledger_add(db, store_id, tanggal, jenis, kategori, keterangan,
                           nominal, media, None, ref_type, None, oleh,
                           subkategori=subkategori,
                           masuk_laba=masuk_laba, pengaruh_kas=pengaruh_kas)
    except Exception as e:
        print("ledger auto-post skip:", ref_type, invoice, e)
        return None


def _svc_media(svc) -> str:
    return lm.METODE_KE_MEDIA.get((svc.metode_bayar or "").strip(), "kas_utama")


def _svc_tanggal(svc):
    d = svc.diambil_at or datetime.date.today()
    try:
        if isinstance(d, datetime.datetime):
            return d.date()
        if isinstance(d, str):
            return datetime.datetime.strptime(d[:10], "%Y-%m-%d").date()
        return d
    except Exception:
        return datetime.date.today()


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


def apply_teknisi_beban(db: Session, store_id: int, tech: models.Technician, total: int,
                        persen: int = 50, sebab: str = "kelalaian", invoice: str = None,
                        label: str = "Nombok"):
    """Bagi beban_my ke teknisi sesuai persen + proteksi junior 1x/bulan.
    Tulis TechDebt (biar cicilan 20% jalan) + CommissionLedger (biar muncul di Kas Saya).
    Return dict: beban_teknisi, beban_toko, proteksi, debt_id."""
    total = int(total or 0)
    persen = max(0, min(100, int(persen or 0)))
    beban_teknisi = total * persen // 100
    beban_toko = total - beban_teknisi
    proteksi = False
    sett = get_settings(db, store_id)
    if beban_teknisi > 0 and (tech.level or "junior") == "junior":
        # junior: 1x/bulan kalau rp-nya <= toleransi_junior_rp → ditanggung toko 100%
        today = datetime.date.today()
        awal = datetime.datetime(today.year, today.month, 1)
        used = db.query(models.TechDebt).filter(
            models.TechDebt.technician_id == tech.id,
            models.TechDebt.created_at >= awal,
            models.TechDebt.beban_teknisi == 0,
            models.TechDebt.beban_toko > 0).count()
        if used == 0 and total <= (sett.toleransi_junior_rp or 100000):
            beban_teknisi = 0
            beban_toko = total
            proteksi = True
    debt = None
    if beban_teknisi > 0:
        debt = models.TechDebt(store_id=store_id, technician_id=tech.id, invoice_penyebab=invoice,
                               total_rugi=total, beban_teknisi=beban_teknisi,
                               beban_toko=beban_toko, sudah_dicicil=0, sisa=beban_teknisi,
                               sebab=sebab, status="belum")
        db.add(debt)
        db.commit()
        db.refresh(debt)
        db.add(models.CommissionLedger(
            store_id=store_id, technician_id=tech.id, tanggal=datetime.date.today(),
            invoice=invoice, tipe="hutang_baru", masuk_rp=0, keluar_rp=0,
            sisa_hutang_saat_itu=beban_teknisi,
            keterangan=f"{label} {invoice or ''} beban Rp{beban_teknisi} "
                       f"cicil max {sett.cicilan_max_pct}%"))
    else:
        db.add(models.CommissionLedger(
            store_id=store_id, technician_id=tech.id, tanggal=datetime.date.today(),
            invoice=invoice, tipe="toleransi_toko", masuk_rp=0, keluar_rp=0,
            sisa_hutang_saat_itu=0,
            keterangan=f"{label} {invoice or ''} Rp{total} ditanggung toko 100%"))
    db.commit()
    return {"beban_teknisi": beban_teknisi, "beban_toko": beban_toko,
            "proteksi": proteksi, "debt_id": debt.id if debt else None}


def cek_penghasilan_hari_ini(db: Session, store_id: int):
    """Omzet service yang sudah cair HARI INI (dasar sumber dana refund)."""
    today = datetime.date.today()
    rows = db.query(models.Service).filter(
        models.Service.store_id == store_id,
        models.Service.status.in_(["Service Sukses", "Sudah Diambil", "Selesai"])).all()
    total = 0
    for s in rows:
        d = str(s.diambil_at or s.updated_at or s.date or "")[:10]
        if d == today.isoformat():
            total += int(s.biaya or 0)
    return total


def cairkan(db: Session, svc: models.Service, actor=None):
    """CAIR saat Service Sukses (deal + bayar) atau Sudah Diambil. Hitung ulang jasa/komisi, potong hutang max 20%, tulis ledger. Idempotent."""
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
        # Sukses TANPA komisi: omzet jasa tetap terbentuk di buku besar.
        _ledger_post_safe(db, svc.store_id, _svc_tanggal(svc), "masuk", "A1",
                          f"Service {svc.invoice}: {svc.device or ''}",
                          max(0, int(svc.biaya or 0)), _svc_media(svc),
                          "service", svc.invoice, getattr(actor, "username", None))
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
    # Buku besar (prinsip mentor): SUKSES = omzet jasa terbentuk + HPP komisi terbentuk.
    _ledger_post_safe(db, svc.store_id, _svc_tanggal(svc), "masuk", "A1",
                      f"Service {svc.invoice}: {svc.device or ''}",
                      max(0, int(svc.biaya or 0)), _svc_media(svc),
                      "service", svc.invoice, getattr(actor, "username", None))
    if komisi > 0:
        _ledger_post_safe(db, svc.store_id, _svc_tanggal(svc), "keluar", "B1",
                          f"Komisi {svc.teknisi or ''} {svc.invoice} ({pct}%)",
                          komisi, _svc_media(svc),
                          "service_komisi", svc.invoice, getattr(actor, "username", None),
                          subkategori="Komisi")
    db.commit()
    db.refresh(row)
    return row
