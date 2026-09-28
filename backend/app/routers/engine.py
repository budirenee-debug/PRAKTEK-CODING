"""Business Engine: settings + attendance + kuota 2:1 + garansi oper + nombok 50:50."""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from ..database import get_db
from .. import models, schemas
from ..audit import log_action
from ..store_ctx import resolve_store, store_role, default_store
from .auth import get_current_user
from .stores import _require_store_manager

router = APIRouter(prefix="/engine", tags=["Engine"])


def _get_settings(db: Session, store_id: int) -> models.StoreSettings:
    s = db.query(models.StoreSettings).filter(models.StoreSettings.store_id == store_id).first()
    if not s:
        s = models.StoreSettings(store_id=store_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _parse_hhmm(v: str) -> tuple[int, int]:
    try:
        h, m = (v or "09:00").strip().split(":")
        return int(h), int(m)
    except Exception:
        return 9, 0


def _resolve_my_technician(db: Session, store, current) -> models.Technician:
    """Cari Technician milik user login. Auto-create jika belum ada (agar invite baru bisa check-in)."""
    names = []
    if getattr(current, "username", None):
        names.append(current.username)
    if getattr(current, "nama", None):
        names.append(current.nama)
    q = db.query(models.Technician).filter(models.Technician.store_id == store.id)
    tech = None
    for n in names:
        if not n:
            continue
        tech = q.filter(models.Technician.nama.ilike(n)).first()
        if tech:
            break
    if not tech:
        disp = getattr(current, "nama", None) or getattr(current, "username", None) or "Teknisi"
        tech = models.Technician(nama=disp, store_id=store.id, level="junior", is_active=1)
        db.add(tech)
        db.commit()
        db.refresh(tech)
    return tech


@router.get("/settings", response_model=schemas.StoreSettingsOut)
def get_settings(store_id: Optional[int] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if not store:
        raise HTTPException(status_code=404, detail="Belum ada toko aktif")
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh lihat settings engine")
    return _get_settings(db, store.id)


@router.put("/settings", response_model=schemas.StoreSettingsOut)
def update_settings(payload: schemas.StoreSettingsUpdate, store_id: Optional[int] = Query(None),
                    db: Session = Depends(get_db), current=Depends(get_current_user)):
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if not store:
        raise HTTPException(status_code=404, detail="Belum ada toko aktif")
    # owner only (superadmin lolos)
    if current.role != "superadmin":
        from .. import models as _m
        m = db.query(_m.Membership).filter(
            _m.Membership.user_id == current.id,
            _m.Membership.store_id == store.id,
            _m.Membership.is_active == True).first()
        if not m or m.role != "owner":
            raise HTTPException(status_code=403, detail="Hanya owner yang boleh ubah aturan engine")
    s = _get_settings(db, store.id)
    changed = []
    for f in ["uang_hadir", "jam_masuk", "toleransi_mnt", "komisi_senior", "komisi_junior",
              "kuota_ringan_per_berat", "cicilan_max_pct", "toleransi_junior_rp",
              "keyword_berat", "keyword_ringan"]:
        v = getattr(payload, f, None)
        if v is not None and v != getattr(s, f):
            setattr(s, f, v)
            changed.append(f)
    if payload.jam_masuk is not None:
        h, mnt = _parse_hhmm(payload.jam_masuk)
        s.jam_masuk = f"{h:02d}:{mnt:02d}"
    db.commit()
    db.refresh(s)
    if changed:
        log_action(db, "engine.settings", target=f"store={store.kode}",
                   detail=f"ubah: {','.join(changed)}", actor=current, store_id=store.id)
    return s


@router.post("/check-in", response_model=schemas.AttendanceOut)
def check_in(store_id: Optional[int] = Query(None),
             db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Check-in harian teknisi. Tepat waktu -> allowance otomatis + ledger."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if not store:
        raise HTTPException(status_code=404, detail="Belum ada toko aktif")
    tech = _resolve_my_technician(db, store, current)
    today = datetime.date.today()
    ex = db.query(models.Attendance).filter(
        models.Attendance.technician_id == tech.id,
        models.Attendance.tanggal == today).first()
    if ex:
        return {"id": ex.id, "technician_id": tech.id, "technician_nama": tech.nama,
                "tanggal": ex.tanggal, "jam_checkin": ex.jam_checkin,
                "on_time": ex.on_time, "allowance_rp": ex.allowance_rp}
    sett = _get_settings(db, store.id)
    now = datetime.datetime.now()
    jam_now = f"{now.hour:02d}:{now.minute:02d}"
    jh, jm = _parse_hhmm(sett.jam_masuk)
    batas = now.replace(hour=jh, minute=jm, second=0, microsecond=0) + datetime.timedelta(minutes=(sett.toleransi_mnt or 0))
    on_time = now <= batas
    allowance = (sett.uang_hadir or 0) if on_time else 0
    row = models.Attendance(store_id=store.id, technician_id=tech.id, tanggal=today,
                            jam_checkin=jam_now, on_time=on_time, allowance_rp=allowance)
    db.add(row)
    db.commit()
    db.refresh(row)
    if allowance > 0:
        # sisa hutang saat itu untuk transparansi
        debts = db.query(models.TechDebt).filter(
            models.TechDebt.technician_id == tech.id,
            models.TechDebt.status == "belum").all()
        sisa = sum((d.sisa or 0) for d in debts)
        db.add(models.CommissionLedger(
            store_id=store.id, technician_id=tech.id, tanggal=today, invoice=None,
            tipe="allowance", masuk_rp=allowance, keluar_rp=0,
            sisa_hutang_saat_itu=sisa, keterangan=f"Uang hadir {jam_now}"))
        db.commit()
    log_action(db, "engine.checkin", target=tech.nama,
               detail=f"{jam_now} on_time={on_time} allowance={allowance}",
               actor=current, store_id=store.id)
    return {"id": row.id, "technician_id": tech.id, "technician_nama": tech.nama,
            "tanggal": row.tanggal, "jam_checkin": row.jam_checkin,
            "on_time": row.on_time, "allowance_rp": row.allowance_rp}


@router.get("/kuota/me")
def my_quota(store_id: Optional[int] = Query(None),
             db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Sisa kuota ringan hari ini untuk senior (2:1, reset 00:00). Junior bebas ringan."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    tech = _resolve_my_technician(db, store, current)
    sett = _get_settings(db, store.id)
    today = datetime.date.today()
    rasio = sett.kuota_ringan_per_berat or 2
    if (tech.level or "junior") != "senior":
        return {"nama": tech.nama, "level": tech.level or "junior",
                "berat_hari_ini": 0, "ringan_hari_ini": 0,
                "kuota_max": None, "sisa": None, "note": "Junior bebas ambil ringan"}
    berats = db.query(models.ServiceEngine).join(
        models.Service, models.Service.invoice == models.ServiceEngine.invoice
    ).filter(
        models.ServiceEngine.store_id == store.id,
        models.ServiceEngine.kategori == "berat",
        models.Service.date == today,
        models.Service.teknisi.ilike(f"%{tech.nama}%")).count()
    ringans = db.query(models.ServiceEngine).join(
        models.Service, models.Service.invoice == models.ServiceEngine.invoice
    ).filter(
        models.ServiceEngine.store_id == store.id,
        models.ServiceEngine.kategori == "ringan",
        models.Service.date == today,
        models.Service.teknisi.ilike(f"%{tech.nama}%")).count()
    kuota_max = berats * rasio
    sisa = max(0, kuota_max - ringans)
    return {"nama": tech.nama, "level": "senior", "berat_hari_ini": berats,
            "ringan_hari_ini": ringans, "kuota_max": kuota_max, "sisa": sisa,
            "rasio": f"{rasio}:1", "reset": "00:00"}


def _kas_summary(db: Session, store_id: int, technician_id: int):
    leds = db.query(models.CommissionLedger).filter(
        models.CommissionLedger.store_id == store_id,
        models.CommissionLedger.technician_id == technician_id).all()
    komisi = sum((l.masuk_rp or 0) for l in leds if l.tipe == "komisi_cair")
    allowance = sum((l.masuk_rp or 0) for l in leds if l.tipe == "allowance")
    potong = sum((l.keluar_rp or 0) for l in leds if l.tipe == "potongan_cicilan")
    refund = sum((l.keluar_rp or 0) for l in leds if l.tipe == "refund_balik")
    # komisi_cair di ledger sudah NET dari cicilan hutang (masuk = komisi - potong).
    # Jadi komisi_bruto = komisi + cicilan; potongan = cicilan + refund balik.
    potongan = potong + refund
    komisi_bruto = komisi + potong
    total_diterima = komisi + allowance
    netto = total_diterima - refund
    debts = db.query(models.TechDebt).filter(
        models.TechDebt.technician_id == technician_id,
        models.TechDebt.status == "belum").all()
    sisa = sum((d.sisa or 0) for d in debts)
    pendings = db.query(models.ServiceEngine).join(
        models.Service, models.Service.invoice == models.ServiceEngine.invoice).filter(
        models.ServiceEngine.store_id == store_id,
        models.ServiceEngine.komisi_status == "pending").all()
    # pending milik teknisi ini saja (by nama)
    tech = db.query(models.Technician).filter(models.Technician.id == technician_id).first()
    tname = tech.nama if tech else ""
    mypend = []
    for se in pendings:
        svc = db.query(models.Service).filter(models.Service.invoice == se.invoice).first()
        if svc and svc.teknisi and tname and tname.lower() in (svc.teknisi or "").lower():
            mypend.append({"invoice": se.invoice, "kategori": se.kategori,
                           "jasa_bersih": se.jasa_bersih, "komisi": se.komisi_teknisi,
                           "status_service": svc.status})
    return {"komisi_cair": komisi, "komisi_bruto": komisi_bruto,
            "allowance": allowance, "potongan_cicilan": potong,
            "potongan_refund": refund, "potongan": potongan,
            "total_diterima": komisi + allowance, "netto": netto,
            "sisa_hutang": sisa,
            "pending_count": len(mypend), "pending": mypend,
            "riwayat": [{"id": l.id, "tanggal": l.tanggal, "invoice": l.invoice, "tipe": l.tipe,
                         "masuk": l.masuk_rp, "keluar": l.keluar_rp,
                         "sisa_hutang": l.sisa_hutang_saat_itu, "ket": l.keterangan}
                        for l in sorted(leds, key=lambda x: x.id or 0, reverse=True)[:100]]}


@router.get("/kas/saya")
def kas_saya(store_id: Optional[int] = Query(None),
             db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Buku kas milik teknisi login saja (privat)."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    tech = _resolve_my_technician(db, store, current)
    out = _kas_summary(db, store.id, tech.id)
    out.update({"nama": tech.nama, "level": tech.level or "junior"})
    return out


@router.get("/kas/teknisi/{technician_id}")
def kas_teknisi(technician_id: int, store_id: Optional[int] = Query(None),
                db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Buku kas per teknisi (owner/admin only)."""
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh lihat kas teknisi")
    tech = db.query(models.Technician).filter(models.Technician.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Teknisi tidak ditemukan")
    out = _kas_summary(db, store.id, tech.id)
    out.update({"nama": tech.nama, "level": tech.level or "junior"})
    return out


@router.get("/service/{invoice}")
def engine_detail(invoice: str, store_id: Optional[int] = Query(None),
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Detail engine per invoice. modal_asli hanya owner/superadmin."""
    store = resolve_store(db, current, store_id)
    se = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == invoice).first()
    if not se:
        raise HTTPException(status_code=404, detail="Engine tidak ditemukan")
    role = store_role(db, current, store)
    out = {"invoice": se.invoice, "kategori": se.kategori, "harga_part_up": se.harga_part_up,
           "jasa_bersih": se.jasa_bersih, "komisi_teknisi": se.komisi_teknisi,
           "komisi_status": se.komisi_status, "dioper_dari": se.dioper_dari,
           "dioper_ke": se.dioper_ke, "dioper_oleh": se.dioper_oleh}
    if role in ["superadmin", "owner"]:
        out["modal_asli"] = se.modal_asli
    return out


@router.post("/garansi/{invoice}/oper")
def oper_garansi(invoice: str, to_teknisi: str = Body(..., embed=True),
                 store_id: Optional[int] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Oper garansi ke teknisi lain. Boleh admin/kasir/owner (operasional cepat).
    Biaya part/ongkos dibebankan ke teknisi lama (ledger hutang via nombok terpisah)."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin", "kasir"]:
        raise HTTPException(status_code=403, detail="Hanya admin/kasir/owner yang boleh oper garansi")
    svc = db.query(models.Service).filter(models.Service.invoice == invoice).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    if store and svc.store_id != store.id:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan di toko ini")
    to_teknisi = (to_teknisi or "").strip()
    if not to_teknisi:
        raise HTTPException(status_code=400, detail="to_teknisi wajib diisi")
    target = db.query(models.Technician).filter(
        models.Technician.store_id == store.id,
        models.Technician.nama.ilike(to_teknisi)).first()
    if not target:
        raise HTTPException(status_code=404, detail=f"Teknisi {to_teknisi} tidak ditemukan di toko ini")
    dari = svc.teknisi or "-"
    svc.teknisi = target.nama
    svc.technician_id = target.id
    se = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == invoice).first()
    if se:
        se.dioper_dari = dari
        se.dioper_ke = target.nama
        se.dioper_oleh = current.username
    db.commit()
    log_action(db, "engine.oper_garansi", target=invoice,
               detail=f"dari={dari} ke={target.nama} oleh={current.username}. Biaya dibebankan ke {dari}",
               actor=current, store_id=store.id if store else None)
    return {"invoice": invoice, "dari": dari, "ke": target.nama, "oleh": current.username,
            "note": f"Biaya part/ongkos oper dibebankan ke {dari} via nombok"}


@router.post("/nombok")
def input_nombok(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Input kelalaian/nombok. Owner/admin only.
    Body: {technician_id atau teknisi, invoice_penyebab, total_rugi, sebab=kelalaian/cacat_pabrik}
    - cacat_pabrik: 100% toko, teknisi tidak dipotong.
    - kelalaian: 50:50. Junior proteksi 1x/bln max setting ditanggung toko 100%."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh input nombok")
    sett = _get_settings(db, store.id)
    total = int(payload.get("total_rugi") or 0)
    if total <= 0:
        raise HTTPException(status_code=400, detail="total_rugi harus > 0")
    sebab = (payload.get("sebab") or "kelalaian").strip().lower()
    if sebab not in ["kelalaian", "cacat_pabrik"]:
        raise HTTPException(status_code=400, detail="sebab harus kelalaian atau cacat_pabrik")
    invoice = (payload.get("invoice_penyebab") or "").strip() or None
    tech = None
    if payload.get("technician_id"):
        tech = db.query(models.Technician).filter(models.Technician.id == payload["technician_id"]).first()
    elif payload.get("teknisi"):
        tech = db.query(models.Technician).filter(
            models.Technician.store_id == store.id,
            models.Technician.nama.ilike(payload["teknisi"].strip())).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Teknisi tidak ditemukan")
    today = datetime.date.today()
    if sebab == "cacat_pabrik":
        # toko 100%, teknisi tidak dipotong. Catat ledger toleransi untuk transparansi.
        db.add(models.CommissionLedger(
            store_id=store.id, technician_id=tech.id, tanggal=today, invoice=invoice,
            tipe="toleransi_toko", masuk_rp=0, keluar_rp=0, sisa_hutang_saat_itu=0,
            keterangan=f"Cacat pabrik {invoice or ''} Rp{total} ditanggung toko 100% (retur supplier)"))
        db.commit()
        log_action(db, "engine.nombok_pabrik", target=tech.nama,
                   detail=f"{invoice} Rp{total} toko 100%", actor=current, store_id=store.id)
        return {"teknisi": tech.nama, "sebab": sebab, "total_rugi": total,
                "beban_teknisi": 0, "beban_toko": total, "note": "Cacat pabrik: teknisi tidak dipotong"}
    # kelalaian -> proteksi junior?
    beban_teknisi = total // 2
    beban_toko = total - beban_teknisi
    proteksi = False
    if (tech.level or "junior") == "junior":
        # sudah pakai toleransi bulan ini?
        awal_bulan = today.replace(day=1)
        used = db.query(models.TechDebt).filter(
            models.TechDebt.technician_id == tech.id,
            models.TechDebt.created_at >= datetime.datetime(awal_bulan.year, awal_bulan.month, 1),
            models.TechDebt.beban_teknisi == 0,
            models.TechDebt.beban_toko > 0).count()
        if used == 0 and total <= (sett.toleransi_junior_rp or 100000):
            beban_teknisi = 0
            beban_toko = total
            proteksi = True
    d = models.TechDebt(store_id=store.id, technician_id=tech.id, invoice_penyebab=invoice,
                        total_rugi=total, beban_teknisi=beban_teknisi, beban_toko=beban_toko,
                        sudah_dicicil=0, sisa=beban_teknisi,
                        sebab=sebab, status="lunas" if beban_teknisi == 0 else "belum")
    db.add(d)
    db.commit()
    db.refresh(d)
    # ledger hutang_baru agar muncul di Kas Saya
    if beban_teknisi > 0:
        db.add(models.CommissionLedger(
            store_id=store.id, technician_id=tech.id, tanggal=today, invoice=invoice,
            tipe="hutang_baru", masuk_rp=0, keluar_rp=0, sisa_hutang_saat_itu=beban_teknisi,
            keterangan=f"Nombok {invoice or ''} 50:50, beban Rp{beban_teknisi} cicil max {sett.cicilan_max_pct}%"))
    else:
        db.add(models.CommissionLedger(
            store_id=store.id, technician_id=tech.id, tanggal=today, invoice=invoice,
            tipe="toleransi_toko", masuk_rp=0, keluar_rp=0, sisa_hutang_saat_itu=0,
            keterangan=f"Proteksi junior Rp{total} ditanggung toko 100%"))
    db.commit()
    log_action(db, "engine.nombok", target=tech.nama,
               detail=f"{invoice} total={total} beban_teknisi={beban_teknisi} proteksi={proteksi}",
               actor=current, store_id=store.id)
    return {"teknisi": tech.nama, "level": tech.level, "sebab": sebab, "total_rugi": total,
            "beban_teknisi": beban_teknisi, "beban_toko": beban_toko,
            "sisa": beban_teknisi, "proteksi_junior": proteksi, "debt_id": d.id}


@router.put("/service/{invoice}/part")
def update_part(invoice: str, payload: dict = Body(...), store_id: Optional[int] = Query(None),
                db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Set Harga Part UP (+ modal asli owner) sebelum cair. Dipakai di fase Sukses/Bisa Diambil.
    Teknisi/kasir boleh isi harga UP, modal_asli hanya owner."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin", "kasir", "teknisi"]:
        raise HTTPException(status_code=403, detail="Login dulu")
    se = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == invoice).first()
    if not se:
        raise HTTPException(status_code=404, detail="Engine tidak ditemukan")
    if (se.komisi_status or "") == "cair":
        raise HTTPException(status_code=400, detail="Sudah cair — part dikunci. Hubungi owner untuk revisi.")
    svc = db.query(models.Service).filter(models.Service.invoice == invoice).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    harga = payload.get("harga_part_up")
    if harga is None:
        raise HTTPException(status_code=400, detail="harga_part_up wajib diisi")
    harga = int(harga or 0)
    if harga < 0:
        raise HTTPException(status_code=400, detail="harga_part_up >= 0")
    se.harga_part_up = harga
    if "modal_asli" in payload and payload["modal_asli"] is not None:
        if role not in ["superadmin", "owner"]:
            raise HTTPException(status_code=403, detail="modal_asli hanya owner")
        se.modal_asli = int(payload["modal_asli"] or 0)
    if "kategori" in payload and payload["kategori"]:
        kat = str(payload["kategori"]).strip().lower()
        if kat in ["berat", "ringan"]:
            se.kategori = kat
    # hitung ulang jasa + komisi (masih pending)
    from .. import engine_logic as _el
    sett = _el.get_settings(db, se.store_id or (store.id if store else None))
    jasa = max(0, int(svc.biaya or 0) - harga)
    lvl = _el.tech_level(db, se.store_id, svc.teknisi)
    pct = (sett.komisi_senior if lvl == "senior" else sett.komisi_junior) or 0
    se.jasa_bersih = jasa
    se.komisi_teknisi = jasa * pct // 100
    db.commit()
    db.refresh(se)
    log_action(db, "engine.set_part", target=invoice,
               detail=f"part_up={harga} jasa={jasa} komisi={se.komisi_teknisi}",
               actor=current, store_id=se.store_id)
    return {"invoice": invoice, "kategori": se.kategori, "harga_part_up": se.harga_part_up,
            "jasa_bersih": se.jasa_bersih, "komisi_teknisi": se.komisi_teknisi,
            "komisi_status": se.komisi_status}


@router.get("/debts")
def list_debts(store_id: Optional[int] = Query(None), status: Optional[str] = Query(None),
               db: Session = Depends(get_db), current=Depends(get_current_user)):
    """List hutang nombok (owner/admin). Teknisi lihat via kas/saya."""
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh lihat hutang")
    q = db.query(models.TechDebt).filter(models.TechDebt.store_id == store.id)
    if status:
        q = q.filter(models.TechDebt.status == status)
    rows = q.order_by(models.TechDebt.id.desc()).limit(200).all()
    out = []
    for d in rows:
        t = db.query(models.Technician).filter(models.Technician.id == d.technician_id).first()
        out.append({"id": d.id, "teknisi": t.nama if t else d.technician_id,
                    "invoice": d.invoice_penyebab, "total": d.total_rugi,
                    "beban_teknisi": d.beban_teknisi, "beban_toko": d.beban_toko,
                    "dicicil": d.sudah_dicicil, "sisa": d.sisa,
                    "sebab": d.sebab, "status": d.status, "created_at": d.created_at})
    return out


@router.get("/potongans")
def list_potongans(store_id: Optional[int] = Query(None), technician_id: Optional[int] = Query(None),
                   tipe: Optional[str] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Semua POTONGAN dari buku kas teknisi (keluar_rp > 0): cicilan hutang + refund balik.
    Owner/admin. Sisa hutang per teknisi ikut dilampirkan."""
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh lihat potongan")
    sid = store.id if store else None
    q = db.query(models.CommissionLedger).filter(
        models.CommissionLedger.keluar_rp > 0)
    if sid:
        q = q.filter(models.CommissionLedger.store_id == sid)
    if technician_id:
        q = q.filter(models.CommissionLedger.technician_id == technician_id)
    if tipe:
        q = q.filter(models.CommissionLedger.tipe == tipe)
    leds = q.order_by(models.CommissionLedger.id.desc()).limit(300).all()
    techs = {t.id: t for t in db.query(models.Technician).all()}
    rows = []
    for l in leds:
        t = techs.get(l.technician_id)
        rows.append({"id": l.id, "tanggal": l.tanggal, "teknisi": t.nama if t else f"#{l.technician_id}",
                     "technician_id": l.technician_id,
                     "level": (t.level or "junior") if t else None,
                     "invoice": l.invoice, "tipe": l.tipe, "keluar": l.keluar_rp,
                     "sisa_hutang": l.sisa_hutang_saat_itu, "keterangan": l.keterangan})
    # ringkasan: seluruh toko (tidak ikut filter) supaya kartu stat stabil
    base = db.query(models.CommissionLedger).filter(models.CommissionLedger.keluar_rp > 0)
    if sid:
        base = base.filter(models.CommissionLedger.store_id == sid)
    alls = base.all()
    cicil = sum(int(l.keluar_rp or 0) for l in alls if l.tipe == "potongan_cicilan")
    refund = sum(int(l.keluar_rp or 0) for l in alls if l.tipe == "refund_balik")
    debts = db.query(models.TechDebt).filter(models.TechDebt.status == "belum")
    if sid:
        debts = debts.filter(models.TechDebt.store_id == sid)
    sisa = sum(int(d.sisa or 0) for d in debts.all())
    per_tech = {}
    for l in alls:
        nm = techs[l.technician_id].nama if l.technician_id in techs else f"#{l.technician_id}"
        per_tech[nm] = per_tech.get(nm, 0) + int(l.keluar_rp or 0)
    today = datetime.date.today()
    bln = sum(int(l.keluar_rp or 0) for l in alls
              if str(l.tanggal or "")[:7] == today.strftime("%Y-%m"))
    return {"rows": rows,
            "ringkasan": {"total": sum(int(l.keluar_rp or 0) for l in alls),
                          "cicilan": cicil, "refund": refund, "lainnya": sum(int(l.keluar_rp or 0) for l in alls
                          if l.tipe not in ("potongan_cicilan", "refund_balik")),
                          "jumlah": len(alls), "bulan_ini": bln,
                          "sisa_hutang": sisa, "per_teknisi": per_tech}}
