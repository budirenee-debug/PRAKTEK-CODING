from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import datetime
from ..database import get_db
from .. import schemas, crud
from ..audit import log_action
from ..store_ctx import resolve_store, ensure_in_store, store_role, teknisi_scope_names, is_own_or_free
from .auth import require_superadmin, get_current_user

router = APIRouter(prefix="/services", tags=["Services"])

def _sid(store) -> Optional[int]:
    return store.id if store is not None else None

def _teknisi_scope(db, current, store):
    """Set nama milik teknisi jika requester role teknisi, else None (bebas)."""
    if store_role(db, current, store) == "teknisi":
        return teknisi_scope_names(current)
    return None

@router.get("", response_model=List[schemas.ServiceOut])
def list_services(
    skip: int = 0,
    limit: int = Query(100, le=200),
    status: Optional[str] = None,
    search: Optional[str] = None,
    device: Optional[str] = None,
    deadline_type: Optional[str] = Query(None, description="harian/mingguan"),
    overdue: Optional[bool] = Query(None, description="true=overdue saja, false=tidak overdue"),
    store_id: Optional[int] = Query(None, description="ID toko aktif (multi-toko BOS)"),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    data = crud.get_services(db, skip=skip, limit=limit, status=status, search=search, device=device, deadline_type=deadline_type, overdue=overdue, store_id=_sid(store), teknisi_scope=_teknisi_scope(db, current, store))
    return data

@router.get("/{invoice}", response_model=schemas.ServiceOut)
def get_service(
    invoice: str,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    svc = crud.get_service(db, invoice, store_id=_sid(store))
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    scope = _teknisi_scope(db, current, store)
    if scope is not None and not is_own_or_free(svc.teknisi, scope):
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    return svc

@router.post("", response_model=schemas.ServiceOut, status_code=201)
def create_service(
    payload: schemas.ServiceCreate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login — token required")
    store = resolve_store(db, current, store_id)
    if store is None:
        # superadmin tanpa store_id -> pakai toko default
        from ..store_ctx import default_store
        store = default_store(db)
        if not store:
            raise HTTPException(status_code=400, detail="Belum ada toko — buat dulu via /api/stores")
    scope = _teknisi_scope(db, current, store)
    if scope is not None:
        # teknisi hanya boleh buat service untuk dirinya sendiri
        if payload.teknisi and payload.teknisi not in scope:
            raise HTTPException(status_code=403, detail="Teknisi hanya bisa buat service untuk diri sendiri")
        if not payload.teknisi:
            payload.teknisi = current.username
    svc = crud.create_service(db, payload, store_id=store.id, store=store)
    return svc

@router.patch("/{invoice}", response_model=schemas.ServiceOut)
def update_service(
    invoice: str,
    payload: schemas.ServiceUpdate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login — token required")
    store = resolve_store(db, current, store_id)
    existing = db.query(crud.models.Service).filter(crud.models.Service.invoice == invoice).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    ensure_in_store(existing, store, "Service")
    scope = _teknisi_scope(db, current, store)
    if scope is not None:
        if not is_own_or_free(existing.teknisi, scope):
            raise HTTPException(status_code=404, detail="Service tidak ditemukan")
        new_tek = payload.model_dump(exclude_unset=True).get("teknisi")
        if new_tek and new_tek not in scope:
            raise HTTPException(status_code=403, detail="Teknisi hanya bisa oper ke diri sendiri")
    svc = crud.update_service(db, invoice, payload)
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    return svc

@router.put("/{invoice}/status", response_model=schemas.ServiceOut)
def update_status(
    invoice: str,
    status: str = Query(..., description="Antri|Menunggu Konfirmasi|Dikerjakan|Menunggu Sparepart|Selesai|Service Sukses|Dibatalkan|Bisa Diambil|Sudah Diambil|Service Failed|Garansi"),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    allowed = ["Antri","Menunggu Konfirmasi","Dikerjakan","Menunggu Sparepart","Selesai","Service Sukses","Dibatalkan","Bisa Diambil","Sudah Diambil","Service Failed","Garansi"]
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status harus {allowed}")
    # normalisasi legacy Selesai -> Service Sukses agar konsisten dengan schemas.py
    if status == "Selesai":
        status = "Service Sukses"
    store = resolve_store(db, current, store_id)
    svc = db.query(crud.models.Service).filter(crud.models.Service.invoice == invoice).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    ensure_in_store(svc, store, "Service")
    scope = _teknisi_scope(db, current, store)
    if scope is not None and not is_own_or_free(svc.teknisi, scope):
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    svc.status = status
    # tgl pengambilan: dicatat persis saat jadi Sukses/Sudah Diambil
    if status in ("Sudah Diambil", "Service Sukses", "Selesai"):
        svc.diambil_at = datetime.datetime.now()
    # garansi: saat diambil/sukses & punya masa garansi tapi belum ada batas -> isi otomatis
    if status in ("Sudah Diambil", "Service Sukses") and svc.garansi_hari and not svc.garansi_sampai:
        try:
            svc.garansi_sampai = datetime.date.today() + datetime.timedelta(days=int(svc.garansi_hari or 0))
        except Exception:
            pass
    db.commit()
    db.refresh(svc)
    return crud.enrich_service(svc)

@router.post("/{invoice}/klaim-garansi", response_model=schemas.ServiceOut, status_code=201)
def klaim_garansi(
    invoice: str,
    payload: schemas.KlaimGaransiIn,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """Klaim garansi tanpa input baru: copy data service yg Sudah Diambil jadi service Antri.
    Jendela garansi mengikuti service ASAL (root) — klaim berulang tidak memperpanjang masa."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    orig = db.query(crud.models.Service).filter(crud.models.Service.invoice == invoice).first()
    if not orig:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    ensure_in_store(orig, store, "Service")
    scope = _teknisi_scope(db, current, store)
    if scope is not None:
        if not is_own_or_free(orig.teknisi, scope):
            raise HTTPException(status_code=404, detail="Service tidak ditemukan")
        if payload.teknisi and payload.teknisi not in scope:
            raise HTTPException(status_code=403, detail="Teknisi hanya bisa klaim untuk diri sendiri")
    if orig.status not in ("Sudah Diambil", "Service Sukses", "Selesai", "Garansi"):
        raise HTTPException(status_code=400, detail="Klaim garansi hanya dari status Sukses/Sudah Diambil/Garansi")
    # telusuri ke root (klaim dari klaim mengikuti garansi aslinya)
    root = orig
    for _ in range(20):
        if not root.garansi_dari:
            break
        parent = db.query(crud.models.Service).filter(crud.models.Service.invoice == root.garansi_dari).first()
        if not parent:
            break
        root = parent
    if not root.garansi_hari:
        raise HTTPException(status_code=400, detail="Service ini belum punya masa garansi — isi dulu di kartu Sudah Diambil")
    sampai = root.garansi_sampai
    if not sampai:
        try:
            base = root.updated_at.date() if getattr(root, "updated_at", None) else datetime.date.today()
        except Exception:
            base = datetime.date.today()
        sampai = base + datetime.timedelta(days=int(root.garansi_hari or 0))
        root.garansi_sampai = sampai
        db.commit()
    if sampai < datetime.date.today():
        raise HTTPException(status_code=400, detail=f"Masa garansi sudah habis ({sampai}) — buat service baru biasa")
    sid = store.id if store is not None else orig.store_id
    store_obj = store
    if store_obj is None and sid is not None:
        store_obj = db.query(crud.models.Store).filter(crud.models.Store.id == sid).first()
    new_payload = schemas.ServiceCreate(
        nama=orig.nama, wa=orig.wa, device=orig.device, imei=orig.imei,
        keluhan=payload.keluhan,
        kelengkapan=crud.kelengkapan_from_str(orig.kelengkapan),
        biaya=payload.biaya or 0,
        teknisi=payload.teknisi or orig.teknisi,
        status="Antri",
    )
    new_svc = crud.create_service(db, new_payload, store_id=sid, store=store_obj)
    new_svc.garansi_dari = orig.invoice
    db.commit()
    db.refresh(new_svc)
    log_action(db, "service.klaim_garansi", target=new_svc.invoice,
               detail=f"dari={orig.invoice} root={root.invoice} biaya={new_svc.biaya}",
               actor=current, store_id=new_svc.store_id)
    return crud.enrich_service(new_svc)


@router.delete("/{invoice}")
def delete_service(
    invoice: str,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(require_superadmin),
):
    store = resolve_store(db, current, store_id)
    svc = db.query(crud.models.Service).filter(crud.models.Service.invoice == invoice).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    ensure_in_store(svc, store, "Service")
    ok = crud.delete_service(db, invoice)
    if not ok:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    return {"message": f"{invoice} dihapus"}
