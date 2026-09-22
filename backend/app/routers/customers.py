from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud, models
from ..store_ctx import resolve_store, ensure_in_store
from .auth import get_current_user
from sqlalchemy import desc

router = APIRouter(prefix="/customers", tags=["Customers"])

def _sid(store) -> Optional[int]:
    return store.id if store is not None else None

@router.get("", response_model=List[dict])
def list_customers(
    search: Optional[str] = None,
    device: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    sid = _sid(store)
    customers = crud.get_customers(db, search=search, device=device, skip=skip, limit=limit, store_id=sid)
    result = []
    for c in customers:
        sq = db.query(models.Service).filter(models.Service.customer_id==c.id)
        if sid is not None:
            sq = sq.filter(models.Service.store_id == sid)
        total = sq.count()
        last = sq.order_by(desc(models.Service.date)).first()
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
def get_customer(
    customer_id: int,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    c, total, last = crud.get_customer_detail(db, customer_id, store_id=_sid(store)) or (None, None, None)
    if not c:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    sq = db.query(models.Service).filter(models.Service.customer_id==c.id)
    if store is not None:
        sq = sq.filter(models.Service.store_id == store.id)
    services = sq.order_by(desc(models.Service.date)).all()
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
def create_customer(
    payload: schemas.CustomerCreate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    if store is None:
        from ..store_ctx import default_store
        store = default_store(db)
    cq = db.query(models.Customer).filter(models.Customer.wa==payload.wa)
    if store is not None:
        cq = cq.filter(models.Customer.store_id == store.id)
    exists = cq.first()
    if exists:
        raise HTTPException(status_code=400, detail="WA sudah terdaftar di toko ini")
    c = models.Customer(nama=payload.nama, wa=payload.wa, store_id=store.id if store else None)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
