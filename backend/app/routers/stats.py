from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, schemas

router = APIRouter(prefix="/stats", tags=["Stats"])

@router.get("", response_model=schemas.StatsOut)
def get_stats(db: Session = Depends(get_db)):
    return crud.get_stats(db)

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    stats = crud.get_stats(db)
    recent = crud.get_services(db, limit=4)
    # performa teknisi
    from .. import models
    techs = db.query(models.Technician).all()
    perf = []
    for t in techs:
        total = db.query(models.Service).filter(models.Service.technician_id==t.id).count()
        selesai = db.query(models.Service).filter(models.Service.technician_id==t.id, models.Service.status=="Selesai").count()
        persen = round((selesai/total*100) if total else 0)
        perf.append({"id": t.id, "nama": t.nama, "foto": t.foto, "total": total, "selesai": selesai, "persen": persen})
    return {"stats": stats, "recent": recent, "technicians": perf}
