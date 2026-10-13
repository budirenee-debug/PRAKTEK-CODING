"""Tabungan Operasional: sewa harian + celengan bulanan (wifi/listrik/gaji admin).

Prinsip: dana MEMO — tidak menyentuh komisi/teknisi (buku teknisi terpisah).
- Sewa: target harian, dipenuhi admin via Expense C2 seperti biasa (auto-deteksi).
- Wifi/Listrik/Gaji: celengan — sisih otomatis tiap Tutup Kas (memo, tanpa gerak kas),
  bayar oleh owner (Expense biasa + tautan ops, kas keluar tercatat sekali).
- Setting nominal: owner/superadmin. Baca status: semua tim (admin butuh utk tutup kas).
"""
import calendar
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from .. import models
from ..audit import log_action
from ..store_ctx import resolve_store, store_role, default_store
from .auth import get_current_user

router = APIRouter(prefix="/ops", tags=["Operasional"])

OPS_ITEMS = {
    "sewa": {"label": "Sewa tempat", "kategori": "C2"},
    "wifi": {"label": "Wifi", "kategori": "C3"},
    "listrik": {"label": "Listrik", "kategori": "C4"},
    "gaji_admin": {"label": "Gaji admin", "kategori": "C1"},
}
MONTHLY_ITEMS = ["wifi", "listrik", "gaji_admin"]


def _ctx(db, current, store_id):
    """Toko aktif + peran. Butuh login."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if store is None:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    return store, store_role(db, current, store)


def _ctx_owner(db, current, store_id):
    store, role = _ctx(db, current, store_id)
    if role not in ["superadmin", "owner"]:
        raise HTTPException(status_code=403, detail="Hanya owner yang boleh ubah tabungan operasional")
    return store, role


def _get_setting(db, store_id) -> Optional[models.OpsSetting]:
    return db.query(models.OpsSetting).filter(models.OpsSetting.store_id == store_id).first()


def _setting_out(s) -> dict:
    if not s:
        return {"sewa_harian": 0, "wifi_nominal": 0, "wifi_tgl": 20,
                "listrik_nominal": 0, "listrik_tgl": 15,
                "gaji_nominal": 0, "gaji_tgl": 1, "configured": False}
    return {"sewa_harian": s.sewa_harian or 0, "wifi_nominal": s.wifi_nominal or 0,
            "wifi_tgl": s.wifi_tgl or 20, "listrik_nominal": s.listrik_nominal or 0,
            "listrik_tgl": s.listrik_tgl or 15, "gaji_nominal": s.gaji_nominal or 0,
            "gaji_tgl": s.gaji_tgl or 1, "configured": True,
            "updated_oleh": s.updated_oleh}


@router.get("/settings")
def get_settings(store_id: Optional[int] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx(db, current, store_id)
    return {"store_id": store.id, **_setting_out(_get_setting(db, store.id))}


@router.put("/settings")
def put_settings(payload: dict = Body(...),
                 store_id: Optional[int] = Query(None),
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx_owner(db, current, store_id)

    def _int(v, default=0, lo=0, hi=999_999_999):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, n))

    def _tgl(v, default):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return default
        return max(1, min(28, n))

    s = _get_setting(db, store.id)
    if not s:
        s = models.OpsSetting(store_id=store.id)
        db.add(s)
    s.sewa_harian = _int(payload.get("sewa_harian"))
    s.wifi_nominal = _int(payload.get("wifi_nominal"))
    s.wifi_tgl = _tgl(payload.get("wifi_tgl"), 20)
    s.listrik_nominal = _int(payload.get("listrik_nominal"))
    s.listrik_tgl = _tgl(payload.get("listrik_tgl"), 15)
    s.gaji_nominal = _int(payload.get("gaji_nominal"))
    s.gaji_tgl = _tgl(payload.get("gaji_tgl"), 1)
    s.updated_oleh = current.username
    db.commit()
    db.refresh(s)
    log_action(db, "ops.settings", target=f"store:{store.id}",
               detail=f"sewa/hari={s.sewa_harian} wifi={s.wifi_nominal}/tgl{s.wifi_tgl} "
                      f"listrik={s.listrik_nominal}/tgl{s.listrik_tgl} gaji={s.gaji_nominal}/tgl{s.gaji_tgl}",
               actor=current, store_id=store.id)
    return {"store_id": store.id, **_setting_out(s)}


def _month_bounds(today: datetime.date):
    first = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    return first, today.replace(day=last_day), last_day


@router.get("/status")
def get_status(store_id: Optional[int] = Query(None), tanggal: Optional[str] = Query(None),
               db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Status tabungan: sewa hari ini + celengan bulanan + jatuh tempo terdekat."""
    store, _ = _ctx(db, current, store_id)
    try:
        today = datetime.date.fromisoformat(tanggal) if tanggal else datetime.date.today()
    except ValueError:
        today = datetime.date.today()
    ym = today.strftime("%Y-%m")
    first, _, _ = _month_bounds(today)
    s = _setting_out(_get_setting(db, store.id))

    # --- Sewa harian: deteksi dari Expense C2 hari ini yang menyebut sewa ---
    sewa_target = s["sewa_harian"]
    exp_c2 = db.query(models.Expense).filter(
        models.Expense.store_id == store.id,
        models.Expense.tanggal == today,
        models.Expense.kategori == "C2").all()
    sewa_rows = [e for e in exp_c2 if "sewa" in (e.keperluan or "").lower()]
    sewa_paid = sum(e.nominal or 0 for e in (sewa_rows or exp_c2))
    sewa_ok = sewa_target > 0 and sewa_paid >= sewa_target

    # --- Celengan bulanan ---
    items = []
    need_total = sisih_total = bayar_total = 0
    for key in MONTHLY_ITEMS:
        nominal = s[f"{key}_nominal"] if key != "gaji_admin" else s["gaji_nominal"]
        due_day = s[f"{key}_tgl"] if key != "gaji_admin" else s["gaji_tgl"]
        due = today.replace(day=min(due_day, calendar.monthrange(today.year, today.month)[1]))
        sisih = sum(r.nominal or 0 for r in db.query(models.OpsEntry).filter(
            models.OpsEntry.store_id == store.id, models.OpsEntry.item == key,
            models.OpsEntry.arah == "sisih",
            models.OpsEntry.tanggal >= first, models.OpsEntry.tanggal <= today).all())
        bayar = sum(r.nominal or 0 for r in db.query(models.OpsEntry).filter(
            models.OpsEntry.store_id == store.id, models.OpsEntry.item == key,
            models.OpsEntry.arah == "bayar",
            models.OpsEntry.tanggal >= first).all())
        need_total += nominal
        sisih_total += sisih
        bayar_total += bayar
        if bayar >= nominal and nominal > 0:
            st = "lunas"
        elif today > due and nominal > 0:
            st = "terlambat"
        elif nominal <= 0:
            st = "belum_diatur"
        else:
            st = "menunggu"
        items.append({"item": key, "label": OPS_ITEMS[key]["label"], "nominal": nominal,
                      "jatuh_tempo": due.isoformat(), "sisih": sisih, "dibayar": bayar,
                      "status": st})

    # Sisa ngendap dari bulan-bulan lalu (sisih - bayar sebelum bulan ini)
    sisih_lalu = sum(r.nominal or 0 for r in db.query(models.OpsEntry).filter(
        models.OpsEntry.store_id == store.id, models.OpsEntry.arah == "sisih",
        models.OpsEntry.tanggal < first).all())
    bayar_lalu = sum(r.nominal or 0 for r in db.query(models.OpsEntry).filter(
        models.OpsEntry.store_id == store.id, models.OpsEntry.arah == "bayar",
        models.OpsEntry.tanggal < first).all())
    ngendap = sisih_lalu - bayar_lalu

    # Jatuh tempo terdekat yang belum lunas
    terdekat = None
    for it in sorted(items, key=lambda x: x["jatuh_tempo"]):
        if it["status"] in ("menunggu", "terlambat"):
            terdekat = it
            break

    return {"store_id": store.id, "tanggal": today.isoformat(), "bulan": ym,
            "sewa": {"target_harian": sewa_target, "terbayar": sewa_paid, "ok": sewa_ok},
            "bulanan": {"need": need_total, "sisih": sisih_total, "dibayar": bayar_total,
                        "ngendap": ngendap, "items": items, "terdekat": terdekat}}


@router.post("/sisih-otomatis")
def sisih_otomatis(payload: dict = Body(...),
                   store_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Sisihkan celengan bulanan utk 1 tanggal (dipanggil saat Tutup Kas).
    Idempoten per (toko, tanggal, item). Tanpa gerak kas (memo)."""
    store, role = _ctx(db, current, store_id)
    if role not in ["superadmin", "owner", "admin", "kasir"]:
        raise HTTPException(status_code=403, detail="Hanya tim toko yang boleh tutup kas")
    try:
        tgl = datetime.date.fromisoformat(payload.get("tanggal")) if payload.get("tanggal") else datetime.date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Format tanggal YYYY-MM-DD")
    s = _setting_out(_get_setting(db, store.id))
    days = calendar.monthrange(tgl.year, tgl.month)[1]
    made = []
    for key in MONTHLY_ITEMS:
        nominal = s[f"{key}_nominal"] if key != "gaji_admin" else s["gaji_nominal"]
        if nominal <= 0:
            continue
        exists = db.query(models.OpsEntry).filter(
            models.OpsEntry.store_id == store.id, models.OpsEntry.item == key,
            models.OpsEntry.arah == "sisih", models.OpsEntry.tanggal == tgl).first()
        if exists:
            continue
        # Hari terakhir: genapkan sisa agar total sebulan pas = nominal
        first = tgl.replace(day=1)
        sudah = sum(r.nominal or 0 for r in db.query(models.OpsEntry).filter(
            models.OpsEntry.store_id == store.id, models.OpsEntry.item == key,
            models.OpsEntry.arah == "sisih",
            models.OpsEntry.tanggal >= first, models.OpsEntry.tanggal < tgl).all())
        if tgl.day >= days:
            bagian = max(0, nominal - sudah)
        else:
            bagian = nominal // days
        if bagian <= 0:
            continue
        r = models.OpsEntry(store_id=store.id, tanggal=tgl, item=key, arah="sisih",
                            nominal=bagian, keterangan="Auto tutup kas (memo, tanpa gerak kas)",
                            dibuat_oleh=current.username)
        db.add(r)
        made.append({"item": key, "nominal": bagian})
    db.commit()
    if made:
        log_action(db, "ops.sisih", target=f"store:{store.id}",
                   detail=" + ".join(f"{m['item']}={m['nominal']}" for m in made),
                   actor=current, store_id=store.id)
    return {"tanggal": tgl.isoformat(), "disisihkan": made}


@router.post("/bayar")
def bayar(payload: dict = Body(...),
          store_id: Optional[int] = Query(None),
          db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Bayar tagihan dari tabungan (owner). Membuat Expense biasa (kas keluar
    tercatat sekali) + tautan OpsEntry agar saldo celengan berkurang."""
    store, _ = _ctx_owner(db, current, store_id)
    item = (payload.get("item") or "").strip()
    if item not in OPS_ITEMS:
        raise HTTPException(status_code=400, detail="item harus: " + "/".join(OPS_ITEMS))
    try:
        nominal = int(payload.get("nominal") or 0)
    except (TypeError, ValueError):
        nominal = 0
    if nominal <= 0:
        raise HTTPException(status_code=400, detail="Nominal harus > 0")
    try:
        tgl = datetime.date.fromisoformat(payload.get("tanggal")) if payload.get("tanggal") else datetime.date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Format tanggal YYYY-MM-DD")
    metode = (payload.get("metode") or "Tunai").strip() or "Tunai"
    ket = (payload.get("keterangan") or "").strip()
    label = OPS_ITEMS[item]["label"]
    kategori = OPS_ITEMS[item]["kategori"]
    keperluan = f"[OPS] {label} {tgl.strftime('%b %Y')}" + (f" — {ket}" if ket else "")
    e = models.Expense(store_id=store.id, tanggal=tgl, kategori=kategori,
                       keperluan=keperluan, nominal=nominal, metode=metode,
                       keterangan="Dibayar dari tabungan operasional",
                       dibuat_oleh=current.username)
    db.add(e)
    db.flush()
    r = models.OpsEntry(store_id=store.id, tanggal=tgl, item=item, arah="bayar",
                        nominal=nominal, expense_id=e.id,
                        keterangan=keperluan, dibuat_oleh=current.username)
    db.add(r)
    db.commit()
    log_action(db, "ops.bayar", target=f"store:{store.id}",
               detail=f"{label} {nominal} via {metode} (expense #{e.id})",
               actor=current, store_id=store.id)
    return {"item": item, "nominal": nominal, "expense_id": e.id, "ops_id": r.id}
