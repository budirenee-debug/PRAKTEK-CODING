from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import schemas, crud

router = APIRouter(prefix="/technicians", tags=["Technicians"])

@router.get("", response_model=List[schemas.TechnicianOut])
def list_technicians(db: Session = Depends(get_db)):
    return crud.get_technicians(db)

@router.post("", response_model=schemas.TechnicianOut, status_code=201)
def create_technician(payload: schemas.TechnicianCreate, db: Session = Depends(get_db)):
    exists = db.query(crud.models.Technician).filter(crud.models.Technician.nama==payload.nama).first() if hasattr(crud, 'models') else None
    # simpel: cek manual
    from .. import models
    exists = db.query(models.Technician).filter(models.Technician.nama==payload.nama).first()
    if exists:
        raise HTTPException(status_code=400, detail="Teknisi sudah ada")
    return crud.create_technician(db, payload)

@router.get("/{tech_id}/stats")
def technician_stats(tech_id: int, db: Session = Depends(get_db)):
    from .. import models
    tech = db.query(models.Technician).filter(models.Technician.id==tech_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Teknisi tidak ditemukan")
    total = db.query(models.Service).filter(models.Service.technician_id==tech_id).count()
    selesai = db.query(models.Service).filter(models.Service.technician_id==tech_id, models.Service.status=="Selesai").count()
    proses = db.query(models.Service).filter(models.Service.technician_id==tech_id, models.Service.status.in_(["Antri","Dikerjakan","Menunggu Sparepart"])).count()
    persen = round((selesai/total*100) if total else 0)
    return {"id": tech.id, "nama": tech.nama, "total": total, "selesai": selesai, "proses": proses, "persen": persen}
