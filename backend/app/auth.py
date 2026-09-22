"""
Auth helper - superadmin bismillah
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from . import models

load_dotenv()

# Config — load dari .env, fail jika prod masih pakai default
SECRET_KEY = os.getenv("SECRET_KEY", "b_gadget_secret_key_2026_ganti_di_prod")
if os.getenv("ENV") == "production" and SECRET_KEY == "b_gadget_secret_key_2026_ganti_di_prod":
    raise RuntimeError("SECRET_KEY masih default di production — set di backend/.env")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))  # 2 jam default, dulu 1440

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


_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # tanpa I,O,0,1 biar tidak ambigu


def generate_invite_code(db: Session) -> str:
    """Buat kode invite unik format BOS-XXXX-XXXX."""
    import secrets
    for _ in range(50):
        part = lambda: "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(4))
        code = f"BOS-{part()}-{part()}"
        exists = db.query(models.Invite).filter(models.Invite.code == code).first()
        if not exists:
            return code
    raise RuntimeError("Gagal generate kode invite unik")
