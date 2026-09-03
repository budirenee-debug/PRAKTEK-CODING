"""
Auth helper - superadmin bismillah
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from . import models

# Config
SECRET_KEY = os.getenv("SECRET_KEY", "b_gadget_secret_key_2026_ganti_di_prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 jam

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    # jangan cek is_active di sini — biar login bisa kasih pesan spesifik
    return user

def ensure_superadmin(db: Session):
    """Buat default superadmin jika belum ada. Password: bismillah"""
    username = "superadmin"
    password = "bismillah"
    existing = db.query(models.User).filter(models.User.username == username).first()
    if existing:
        # update password jika ingin reset? optional
        return existing
    user = models.User(
        username=username,
        password_hash=hash_password(password),
        role="superadmin",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
