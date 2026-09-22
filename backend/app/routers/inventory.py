from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud
from ..store_ctx import resolve_store, ensure_in_store, default_store
from .auth import get_current_user, require_superadmin

router = APIRouter(prefix="/inventory", tags=["Inventory"])

def _sid(store) -> Optional[int]:
    return store.id if store is not None else None

def _need_store(db: Session, store):
    if store is None:
        store = default_store(db)
    return store

@router.get("/spareparts", response_model=List[schemas.SparepartOut])
def list_spareparts(
    search: Optional[str] = None,
    merk: Optional[str] = None,
    kategori: Optional[str] = None,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    return crud.get_spareparts(db, search=search, merk=merk, kategori=kategori, store_id=_sid(store))

@router.post("/spareparts", response_model=schemas.SparepartOut, status_code=201)
def create_sparepart(
    payload: schemas.SparepartCreate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = _need_store(db, resolve_store(db, current, store_id))
    # cek duplikat nama di toko yang sama
    sq = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.nama.ilike(payload.nama.strip()))
    if store is not None:
        sq = sq.filter(crud.models.Sparepart.store_id == store.id)
    existing = sq.first()
    if existing:
        raise HTTPException(status_code=400, detail="Nama part sudah ada di toko ini — pakai Edit")
    return crud.create_sparepart(db, payload, store_id=store.id if store else None)

@router.put("/spareparts/{sp_id}", response_model=schemas.SparepartOut)
def update_sparepart(
    sp_id: int,
    payload: schemas.SparepartUpdate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    # cek duplikat nama kecuali diri sendiri (di toko yang sama)
    if payload.nama:
        dq = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.nama.ilike(payload.nama.strip()), crud.models.Sparepart.id != sp_id)
        if store is not None:
            dq = dq.filter(crud.models.Sparepart.store_id == store.id)
        dup = dq.first()
        if dup:
            raise HTTPException(status_code=400, detail="Nama sudah dipakai item lain")
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    sp = crud.update_sparepart(db, sp_id, payload)
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    return sp

@router.delete("/spareparts/{sp_id}")
def delete_sparepart(
    sp_id: int,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(require_superadmin),
):
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    ok = crud.delete_sparepart(db, sp_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    return {"message": f"{sp_id} dihapus"}

@router.post("/spareparts/{sp_id}/pakai", response_model=schemas.SparepartOut)
def pakai_sparepart(
    sp_id: int,
    qty: int = Query(1, ge=1, description="Jumlah pakai"),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    sp, err = crud.pakai_sparepart(db, sp_id, qty)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return sp

# ----- Alat -----
@router.get("/alats", response_model=List[schemas.AlatOut])
def list_alats(
    search: Optional[str] = None,
    kondisi: Optional[str] = None,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    return crud.get_alats(db, search=search, kondisi=kondisi, store_id=_sid(store))

@router.post("/alats", response_model=schemas.AlatOut, status_code=201)
def create_alat(
    payload: schemas.AlatCreate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = _need_store(db, resolve_store(db, current, store_id))
    aq = db.query(crud.models.Alat).filter(crud.models.Alat.nama.ilike(payload.nama.strip()))
    if store is not None:
        aq = aq.filter(crud.models.Alat.store_id == store.id)
    dup = aq.first()
    if dup:
        raise HTTPException(status_code=400, detail="Nama alat sudah ada di toko ini")
    return crud.create_alat(db, payload, store_id=store.id if store else None)

@router.put("/alats/{alat_id}", response_model=schemas.AlatOut)
def update_alat(
    alat_id: int,
    payload: schemas.AlatUpdate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    alat = db.query(crud.models.Alat).filter(crud.models.Alat.id == alat_id).first()
    if not alat:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    ensure_in_store(alat, store, "Alat")
    if payload.nama:
        dq = db.query(crud.models.Alat).filter(crud.models.Alat.nama.ilike(payload.nama.strip()), crud.models.Alat.id != alat_id)
        if store is not None:
            dq = dq.filter(crud.models.Alat.store_id == store.id)
        dup = dq.first()
        if dup:
            raise HTTPException(status_code=400, detail="Nama sudah dipakai alat lain")
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    alat = crud.update_alat(db, alat_id, payload)
    if not alat:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    return alat

@router.delete("/alats/{alat_id}")
def delete_alat(
    alat_id: int,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(require_superadmin),
):
    store = resolve_store(db, current, store_id)
    alat = db.query(crud.models.Alat).filter(crud.models.Alat.id == alat_id).first()
    if not alat:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    ensure_in_store(alat, store, "Alat")
    ok = crud.delete_alat(db, alat_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    return {"message": f"{alat_id} dihapus"}
