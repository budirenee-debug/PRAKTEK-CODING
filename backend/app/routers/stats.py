from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from ..database import get_db
from .. import crud, schemas
from ..store_ctx import resolve_store
from .auth import get_current_user

router = APIRouter(prefix="/stats", tags=["Stats"])

def _sid(store) -> Optional[int]:
    return store.id if store is not None else None

@router.get("", response_model=schemas.StatsOut)
def get_stats(
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    return crud.get_stats(db, store_id=_sid(store))

@router.get("/dashboard")
def dashboard(
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    sid = _sid(store)
    stats = crud.get_stats(db, store_id=sid)
    recent = crud.get_services(db, limit=4, store_id=sid)
    # performa teknisi
    from .. import models
    tq = db.query(models.Technician)
    if sid is not None:
        tq = tq.filter(models.Technician.store_id == sid)
    techs = tq.all()
    perf = []
    for t in techs:
        sq = db.query(models.Service).filter(models.Service.technician_id==t.id)
        if sid is not None:
            sq = sq.filter(models.Service.store_id == sid)
        total = sq.count()
        selesai = sq.filter(models.Service.status.in_(["Selesai","Service Sukses"])).count()
        persen = round((selesai/total*100) if total else 0)
        perf.append({"id": t.id, "nama": t.nama, "foto": t.foto, "total": total, "selesai": selesai, "persen": persen})
    return {"stats": stats, "recent": recent, "technicians": perf}
