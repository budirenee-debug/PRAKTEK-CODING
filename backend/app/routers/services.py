from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud

router = APIRouter(prefix="/services", tags=["Services"])

@router.get("", response_model=List[schemas.ServiceOut])
def list_services(
    skip: int = 0,
    limit: int = Query(100, le=200),
    status: Optional[str] = None,
    search: Optional[str] = None,
    device: Optional[str] = None,
    db: Session = Depends(get_db)
):
    data = crud.get_services(db, skip=skip, limit=limit, status=status, search=search, device=device)
    return data

@router.get("/{invoice}", response_model=schemas.ServiceOut)
def get_service(invoice: str, db: Session = Depends(get_db)):
    svc = crud.get_service(db, invoice)
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    return svc

@router.post("", response_model=schemas.ServiceOut, status_code=201)
def create_service(payload: schemas.ServiceCreate, db: Session = Depends(get_db)):
    svc = crud.create_service(db, payload)
    return svc

@router.patch("/{invoice}", response_model=schemas.ServiceOut)
def update_service(invoice: str, payload: schemas.ServiceUpdate, db: Session = Depends(get_db)):
    svc = crud.update_service(db, invoice, payload)
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    return svc

@router.put("/{invoice}/status", response_model=schemas.ServiceOut)
def update_status(invoice: str, status: str = Query(..., description="Antri|Dikerjakan|Menunggu Sparepart|Selesai|Dibatalkan|Bisa Diambil|Sudah Diambil|Service Failed|Garansi"), db: Session = Depends(get_db)):
    allowed = ["Antri","Dikerjakan","Menunggu Sparepart","Selesai","Dibatalkan","Bisa Diambil","Sudah Diambil","Service Failed","Garansi"]
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status harus {allowed}")
    svc = crud.get_service(db, invoice)
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    svc.status = status
    db.commit()
    db.refresh(svc)
    return svc

@router.delete("/{invoice}")
def delete_service(invoice: str, db: Session = Depends(get_db)):
    ok = crud.delete_service(db, invoice)
    if not ok:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    return {"message": f"{invoice} dihapus"}
