from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud
from ..store_ctx import resolve_store, ensure_in_store
from .auth import require_superadmin, get_current_user

router = APIRouter(prefix="/services", tags=["Services"])

def _sid(store) -> Optional[int]:
    return store.id if store is not None else None

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
    data = crud.get_services(db, skip=skip, limit=limit, status=status, search=search, device=device, deadline_type=deadline_type, overdue=overdue, store_id=_sid(store))
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
    svc.status = status
    db.commit()
    db.refresh(svc)
    return crud.enrich_service(svc)

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
