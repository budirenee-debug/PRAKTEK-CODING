from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..database import get_db
from .. import models
from ..auth import authenticate_user, create_access_token, decode_token, get_user_by_username, ensure_superadmin

router = APIRouter(prefix="/auth", tags=["Auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

class LoginIn(BaseModel):
    username: str
    password: str

class RegisterIn(BaseModel):
    username: str
    password: str
    role: str  # admin, kasir, teknisi

class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str

class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    class Config:
        from_attributes = True

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = get_user_by_username(db, username)
    return user

def require_superadmin(current = Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Token tidak valid / belum login")
    if current.role not in ["superadmin", "admin"]:
        raise HTTPException(status_code=403, detail="Butuh role superadmin")
    return current

@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    ensure_superadmin(db)
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Username atau password salah")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun menunggu persetujuan superadmin — hubungi superadmin untuk aktivasi")
    user.last_login = datetime.utcnow()
    db.commit()
    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "username": user.username, "role": user.role}

@router.post("/login-form", response_model=LoginOut)
def login_form(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ensure_superadmin(db)
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Username atau password salah")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun menunggu persetujuan superadmin — hubungi superadmin untuk aktivasi")
    user.last_login = datetime.utcnow()
    db.commit()
    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "username": user.username, "role": user.role}

@router.get("/me", response_model=UserOut)
def me(current = Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    return current

@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current = Depends(require_superadmin)):
    return db.query(models.User).all()

@router.get("/pending", response_model=list[UserOut])
def pending_users(db: Session = Depends(get_db), current = Depends(require_superadmin)):
    return db.query(models.User).filter(models.User.is_active == False).all()

@router.post("/approve/{user_id}", response_model=UserOut)
def approve_user(user_id: int, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if user.is_active:
        raise HTTPException(status_code=400, detail="User sudah aktif")
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user

@router.post("/reject/{user_id}")
def reject_user(user_id: int, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="Tidak bisa hapus superadmin")
    db.delete(user)
    db.commit()
    return {"message": f"User {user.username} ditolak & dihapus"}

@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    from ..auth import hash_password
    allowed = ["admin", "kasir", "teknisi"]
    # normalize
    username = payload.username.strip()
    role = payload.role.strip().lower()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username minimal 3 karakter")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
    if role not in allowed:
        raise HTTPException(status_code=400, detail=f"Role harus salah satu: {allowed}")
    # superadmin tidak boleh daftar via register umum
    if username.lower() == "superadmin":
        raise HTTPException(status_code=400, detail="Username superadmin tidak boleh didaftar")
    exists = db.query(models.User).filter(models.User.username == username).first()
    if exists:
        raise HTTPException(status_code=400, detail="Username sudah terdaftar")
    # ensure superadmin tetap ada
    ensure_superadmin(db)
    user = models.User(
        username=username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=False  # butuh persetujuan superadmin
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

class UpdateMeIn(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None

@router.patch("/me", response_model=UserOut)
def update_me(payload: UpdateMeIn, db: Session = Depends(get_db), current = Depends(get_current_user)):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    if payload.username:
        new_u = payload.username.strip()
        if len(new_u) < 3:
            raise HTTPException(status_code=400, detail="Username minimal 3 karakter")
        if new_u.lower() == "superadmin" and current.username.lower() != "superadmin":
            raise HTTPException(status_code=400, detail="Tidak boleh pakai username superadmin")
        exists = db.query(models.User).filter(models.User.username == new_u, models.User.id != current.id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Username sudah dipakai")
        current.username = new_u
    if payload.password:
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
        from ..auth import hash_password
        current.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(current)
    return current

@router.post("/seed-superadmin")
def seed_superadmin(db: Session = Depends(get_db)):
    user = ensure_superadmin(db)
    return {"message": "superadmin ready", "username": user.username, "role": user.role}
