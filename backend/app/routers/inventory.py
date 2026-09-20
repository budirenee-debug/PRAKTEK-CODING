from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud
from .auth import get_current_user, require_superadmin

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("/spareparts", response_model=List[schemas.SparepartOut])
def list_spareparts(search: Optional[str] = None, merk: Optional[str] = None, kategori: Optional[str] = None, db: Session = Depends(get_db)):
    return crud.get_spareparts(db, search=search, merk=merk, kategori=kategori)

@router.post("/spareparts", response_model=schemas.SparepartOut, status_code=201)
def create_sparepart(payload: schemas.SparepartCreate, db: Session = Depends(get_db), current = Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    # cek duplikat nama
    existing = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.nama.ilike(payload.nama.strip())).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nama part sudah ada — pakai Edit")
    return crud.create_sparepart(db, payload)

@router.put("/spareparts/{sp_id}", response_model=schemas.SparepartOut)
def update_sparepart(sp_id: int, payload: schemas.SparepartUpdate, db: Session = Depends(get_db), current = Depends(get_current_user)):
    # cek duplikat nama kecuali diri sendiri
    if payload.nama:
        dup = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.nama.ilike(payload.nama.strip()), crud.models.Sparepart.id != sp_id).first()
        if dup:
            raise HTTPException(status_code=400, detail="Nama sudah dipakai item lain")
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    sp = crud.update_sparepart(db, sp_id, payload)
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    return sp

@router.delete("/spareparts/{sp_id}")
def delete_sparepart(sp_id: int, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    ok = crud.delete_sparepart(db, sp_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    return {"message": f"{sp_id} dihapus"}

@router.post("/spareparts/{sp_id}/pakai", response_model=schemas.SparepartOut)
def pakai_sparepart(sp_id: int, qty: int = Query(1, ge=1, description="Jumlah pakai"), db: Session = Depends(get_db), current = Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    sp, err = crud.pakai_sparepart(db, sp_id, qty)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return sp

# ----- Alat -----
@router.get("/alats", response_model=List[schemas.AlatOut])
def list_alats(search: Optional[str] = None, kondisi: Optional[str] = None, db: Session = Depends(get_db)):
    return crud.get_alats(db, search=search, kondisi=kondisi)

@router.post("/alats", response_model=schemas.AlatOut, status_code=201)
def create_alat(payload: schemas.AlatCreate, db: Session = Depends(get_db), current = Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    dup = db.query(crud.models.Alat).filter(crud.models.Alat.nama.ilike(payload.nama.strip())).first()
    if dup:
        raise HTTPException(status_code=400, detail="Nama alat sudah ada")
    return crud.create_alat(db, payload)

@router.put("/alats/{alat_id}", response_model=schemas.AlatOut)
def update_alat(alat_id: int, payload: schemas.AlatUpdate, db: Session = Depends(get_db), current = Depends(get_current_user)):
    if payload.nama:
        dup = db.query(crud.models.Alat).filter(crud.models.Alat.nama.ilike(payload.nama.strip()), crud.models.Alat.id != alat_id).first()
        if dup:
            raise HTTPException(status_code=400, detail="Nama sudah dipakai alat lain")
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    alat = crud.update_alat(db, alat_id, payload)
    if not alat:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    return alat

@router.delete("/alats/{alat_id}")
def delete_alat(alat_id: int, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    ok = crud.delete_alat(db, alat_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    return {"message": f"{alat_id} dihapus"}
