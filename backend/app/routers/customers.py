from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud, models
from sqlalchemy import desc

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.get("", response_model=List[dict])
def list_customers(
    search: Optional[str] = None,
    device: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    customers = crud.get_customers(db, search=search, device=device, skip=skip, limit=limit)
    result = []
    for c in customers:
        total = db.query(models.Service).filter(models.Service.customer_id==c.id).count()
        last = db.query(models.Service).filter(models.Service.customer_id==c.id).order_by(desc(models.Service.date)).first()
        result.append({
            "id": c.id,
            "nama": c.nama,
            "wa": c.wa,
            "total_service": total,
            "terakhir_service": last.date if last else None,
            "last_device": last.device if last else None,
            "last_status": last.status if last else None,
            "created_at": c.created_at
        })
    return result

@router.get("/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    c, total, last = crud.get_customer_detail(db, customer_id) or (None, None, None)
    if not c:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    services = db.query(models.Service).filter(models.Service.customer_id==c.id).order_by(desc(models.Service.date)).all()
    return {
        "id": c.id,
        "nama": c.nama,
        "wa": c.wa,
        "total_service": total,
        "terakhir_service": last.date if last else None,
        "created_at": c.created_at,
        "services": services
    }

@router.post("", response_model=schemas.CustomerOut, status_code=201)
def create_customer(payload: schemas.CustomerCreate, db: Session = Depends(get_db)):
    exists = db.query(models.Customer).filter(models.Customer.wa==payload.wa).first()
    if exists:
        raise HTTPException(status_code=400, detail="WA sudah terdaftar")
    c = models.Customer(nama=payload.nama, wa=payload.wa)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
