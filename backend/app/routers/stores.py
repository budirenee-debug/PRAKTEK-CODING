from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user, require_superadmin

router = APIRouter(prefix="/stores", tags=["Stores"])


def make_store_code(db: Session, nama: str) -> str:
    """Kode toko unik dari nama (3 huruf pertama alfanumerik, + digit jika tabrakan)."""
    base = "".join(c for c in nama.upper() if c.isalnum())[:3] or "TKO"
    code = base
    i = 2
    while db.query(models.Store).filter(models.Store.kode == code).first():
        code = f"{base}{i}"
        i += 1
        if i > 99:
            import secrets
            code = base + secrets.token_hex(1).upper()
            break
    return code[:10]


def _store_to_out(db: Session, s: models.Store, role_saya: str = None) -> dict:
    owner_username = None
    if s.owner_id:
        o = db.query(models.User).filter(models.User.id == s.owner_id).first()
        owner_username = o.username if o else None
    return {
        "id": s.id, "nama": s.nama, "kode": s.kode, "alamat": s.alamat, "wa": s.wa,
        "owner_id": s.owner_id, "owner_username": owner_username,
        "is_active": s.is_active, "role_saya": role_saya, "created_at": s.created_at,
    }


def _my_memberships(db: Session, user: models.User) -> list[models.Membership]:
    return db.query(models.Membership).filter(
        models.Membership.user_id == user.id,
        models.Membership.is_active == True,
    ).all()


def user_stores(db: Session, user: models.User) -> list[dict]:
    """Daftar toko user + perannya. Superadmin melihat semua toko."""
    if user.role == "superadmin":
        stores = db.query(models.Store).order_by(models.Store.id).all()
        return [_store_to_out(db, s, role_saya="superadmin") for s in stores]
    out = []
    for m in _my_memberships(db, user):
        s = db.query(models.Store).filter(models.Store.id == m.store_id).first()
        if s and s.is_active:
            out.append(_store_to_out(db, s, role_saya=m.role))
    return out


@router.get("", response_model=list[schemas.StoreOut])
def list_my_stores(db: Session = Depends(get_db), current=Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    return user_stores(db, current)


@router.post("", response_model=schemas.StoreOut, status_code=201)
def create_store(payload: schemas.StoreCreate, db: Session = Depends(get_db), current=Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    # boleh: superadmin, atau user yang sudah owner di minimal 1 toko
    allowed = current.role == "superadmin" or current.role == "owner" or any(
        m.role == "owner" for m in _my_memberships(db, current)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Hanya owner yang boleh menambah toko")
    kode = (payload.kode or "").strip().upper()
    if kode:
        if db.query(models.Store).filter(models.Store.kode == kode).first():
            raise HTTPException(status_code=400, detail=f"Kode toko {kode} sudah dipakai")
    else:
        kode = make_store_code(db, payload.nama)
    s = models.Store(
        nama=payload.nama.strip(), kode=kode,
        alamat=(payload.alamat or "").strip() or None,
        wa=(payload.wa or "").strip() or None,
        owner_id=current.id, is_active=True,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    db.add(models.Membership(user_id=current.id, store_id=s.id, role="owner", is_active=True))
    db.commit()
    return _store_to_out(db, s, role_saya="owner")


@router.get("/{store_id}", response_model=schemas.StoreOut)
def get_store(store_id: int, db: Session = Depends(get_db), current=Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    s = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    if current.role == "superadmin":
        return _store_to_out(db, s, role_saya="superadmin")
    m = db.query(models.Membership).filter(
        models.Membership.user_id == current.id,
        models.Membership.store_id == store_id,
        models.Membership.is_active == True,
    ).first()
    if not m:
        raise HTTPException(status_code=403, detail="Bukan anggota toko ini")
    return _store_to_out(db, s, role_saya=m.role)


@router.get("/{store_id}/members", response_model=list[schemas.MembershipOut])
def list_members(store_id: int, db: Session = Depends(get_db), current=Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    s = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    if current.role != "superadmin":
        m = db.query(models.Membership).filter(
            models.Membership.user_id == current.id,
            models.Membership.store_id == store_id,
            models.Membership.is_active == True,
        ).first()
        if not m or m.role not in ["owner", "admin"]:
            raise HTTPException(status_code=403, detail="Hanya owner/admin toko yang boleh lihat anggota")
    out = []
    for m in db.query(models.Membership).filter(models.Membership.store_id == store_id).all():
        u = db.query(models.User).filter(models.User.id == m.user_id).first()
        out.append({
            "id": m.id, "user_id": m.user_id, "username": u.username if u else None,
            "store_id": m.store_id, "store_nama": s.nama, "role": m.role,
            "is_active": m.is_active, "created_at": m.created_at,
        })
    return out
