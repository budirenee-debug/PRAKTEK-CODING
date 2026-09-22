from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud
from ..store_ctx import resolve_store, ensure_in_store
from .auth import get_current_user

router = APIRouter(prefix="/technicians", tags=["Technicians"])

def _sid(store) -> Optional[int]:
    return store.id if store is not None else None

@router.get("", response_model=List[schemas.TechnicianOut])
def list_technicians(
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    return crud.get_technicians(db, store_id=_sid(store))

@router.post("", response_model=schemas.TechnicianOut, status_code=201)
def create_technician(
    payload: schemas.TechnicianCreate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    from .. import models
    store = resolve_store(db, current, store_id)
    if store is None:
        from ..store_ctx import default_store
        store = default_store(db)
    tq = db.query(models.Technician).filter(models.Technician.nama==payload.nama)
    if store is not None:
        tq = tq.filter(models.Technician.store_id == store.id)
    exists = tq.first()
    if exists:
        raise HTTPException(status_code=400, detail="Teknisi sudah ada di toko ini")
    return crud.create_technician(db, payload, store_id=store.id if store else None)

@router.get("/{tech_id}/stats")
def technician_stats(
    tech_id: int,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    from .. import models
    store = resolve_store(db, current, store_id)
    tech = db.query(models.Technician).filter(models.Technician.id==tech_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Teknisi tidak ditemukan")
    ensure_in_store(tech, store, "Teknisi")
    sq = db.query(models.Service).filter(models.Service.technician_id==tech_id)
    if store is not None:
        sq = sq.filter(models.Service.store_id == store.id)
    total = sq.count()
    selesai = sq.filter(models.Service.status.in_(["Selesai","Service Sukses"])).count()
    proses = sq.filter(models.Service.status.in_(["Antri","Menunggu Konfirmasi","Dikerjakan","Menunggu Sparepart"])).count()
    persen = round((selesai/total*100) if total else 0)
    return {"id": tech.id, "nama": tech.nama, "total": total, "selesai": selesai, "proses": proses, "persen": persen}
