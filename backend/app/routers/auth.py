from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

from ..database import get_db
from .. import models, schemas
from ..audit import log_action
from ..auth import authenticate_user, create_access_token, decode_token, get_user_by_username, ensure_superadmin

router = APIRouter(prefix="/auth", tags=["Auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

class LoginIn(BaseModel):
    username: str
    password: str

class RegisterIn(BaseModel):
    username: str
    password: str
    role: Optional[str] = None  # legacy (tanpa invite): admin/kasir/teknisi
    # kontrak baru BOS (invite-only):
    invite_code: Optional[str] = None
    nama: Optional[str] = None
    wa: Optional[str] = None
    nama_toko: Optional[str] = None  # wajib jika invite kind=owner

class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    stores: list[schemas.StoreMini] = []  # toko yang bisa diakses + peran
    primary_store_id: Optional[int] = None

class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    nama: Optional[str] = None
    foto: Optional[str] = None
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
    if current.role != "superadmin":
        raise HTTPException(status_code=403, detail="Hanya superadmin yang boleh mengakses persetujuan akun")
    return current

def _stores_for_login(db: Session, user) -> tuple[list, Optional[int]]:
    """Daftar toko user untuk response login. Self-contained (tanpa import stores)."""
    items = []
    if user.role == "superadmin":
        for s in db.query(models.Store).order_by(models.Store.id).all():
            items.append({"id": s.id, "nama": s.nama, "kode": s.kode, "role": "superadmin"})
    else:
        mems = db.query(models.Membership).filter(
            models.Membership.user_id == user.id,
            models.Membership.is_active == True,
        ).all()
        for m in mems:
            s = db.query(models.Store).filter(models.Store.id == m.store_id).first()
            if s and s.is_active:
                items.append({"id": s.id, "nama": s.nama, "kode": s.kode, "role": m.role})
    primary = items[0]["id"] if items else None
    return items, primary

def _login_response(db: Session, user):
    user.last_login = datetime.utcnow()
    db.commit()
    token = create_access_token({"sub": user.username, "role": user.role})
    stores, primary = _stores_for_login(db, user)
    return {"access_token": token, "token_type": "bearer",
            "username": user.username, "role": user.role,
            "stores": stores, "primary_store_id": primary}

@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    ensure_superadmin(db)
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Username atau password salah")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun menunggu persetujuan superadmin — hubungi superadmin untuk aktivasi")
    return _login_response(db, user)

@router.post("/login-form", response_model=LoginOut)
def login_form(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ensure_superadmin(db)
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Username atau password salah")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun menunggu persetujuan superadmin — hubungi superadmin untuk aktivasi")
    return _login_response(db, user)

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

@router.get("/available-technicians")
def available_technicians(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """
    Daftar akun yang bisa di-assign sebagai teknisi/penerima di tab Semua Service & Service Masuk.
    Di-scope per toko aktif (multi-toko BOS): anggota toko + Technician legacy toko itu.
    Butuh login (token), tidak harus superadmin.
    """
    from ..store_ctx import resolve_store
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    sid = store.id if store is not None else None
    # User aktif: anggota toko (atau semua jika superadmin tanpa scope)
    if sid is None:
        users = db.query(models.User).filter(
            models.User.is_active == True,
            models.User.role.in_(["teknisi", "admin", "kasir", "superadmin", "owner"])
        ).all()
    else:
        mems = db.query(models.Membership).filter(
            models.Membership.store_id == sid,
            models.Membership.is_active == True,
        ).all()
        uids = [m.user_id for m in mems]
        users = db.query(models.User).filter(
            models.User.id.in_(uids),
            models.User.is_active == True,
        ).all() if uids else []
    tq = db.query(models.Technician).filter(models.Technician.is_active == 1)
    if sid is not None:
        tq = tq.filter(models.Technician.store_id == sid)
    techs = tq.all()
    names = set()
    result = []
    for u in users:
        if u.username not in names:
            names.add(u.username)
            result.append({"username": u.username, "role": u.role, "source": "user", "is_active": u.is_active, "foto": None})
    for t in techs:
        if t.nama not in names:
            names.add(t.nama)
            result.append({"username": t.nama, "role": "teknisi", "source": "technician", "is_active": True, "foto": t.foto})
    # fallback jika kosong (DB baru) -> kembalikan legacy default
    if not result:
        for fallback in ["Andi", "Sinta", "Budi"]:
            result.append({"username": fallback, "role": "teknisi", "source": "fallback", "is_active": True, "foto": None})
    return result

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
    log_action(db, "user.approve", target=user.username, detail=f"role={user.role}", actor=current)
    return user

@router.post("/reject/{user_id}")
def reject_user(user_id: int, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="Tidak bisa hapus superadmin")
    uname = user.username
    db.delete(user)
    db.commit()
    log_action(db, "user.reject", target=uname, actor=current)
    return {"message": f"User {uname} ditolak & dihapus"}

@router.post("/register", response_model=schemas.RegisterOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    from ..auth import hash_password
    from .invites import check_invite
    allowed_legacy = ["admin", "kasir", "teknisi"]
    # normalize umum
    username = (payload.username or "").strip()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username minimal 3 karakter")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
    # superadmin tidak boleh daftar via register umum
    if username.lower() == "superadmin":
        raise HTTPException(status_code=400, detail="Username superadmin tidak boleh didaftar")
    exists = db.query(models.User).filter(models.User.username == username).first()
    if exists:
        raise HTTPException(status_code=400, detail="Username sudah terdaftar")
    # ensure superadmin tetap ada
    ensure_superadmin(db)

    def _wa_ok(wa: str) -> bool:
        cleaned = (wa or "").replace(" ", "").replace("-", "").replace("+", "")
        return cleaned.isdigit() and 9 <= len(cleaned) <= 16

    # ---------- Alur BARU: invite-only BOS ----------
    if payload.invite_code:
        inv, reason = check_invite(db, payload.invite_code)
        if not inv:
            raise HTTPException(status_code=400, detail=reason or "Kode undangan tidak valid")
        nama = (payload.nama or "").strip()
        wa = (payload.wa or "").strip()
        if len(nama) < 2:
            raise HTTPException(status_code=400, detail="Nama lengkap minimal 2 karakter")
        if not _wa_ok(wa):
            raise HTTPException(status_code=400, detail="No. WA tidak valid (9–16 digit angka)")
        if inv.kind == "owner":
            nama_toko = (payload.nama_toko or "").strip()
            if len(nama_toko) < 2:
                raise HTTPException(status_code=400, detail="Nama toko pertama wajib diisi")
            from .stores import make_store_code  # lazy: hindari circular import
            user = models.User(username=username, password_hash=hash_password(payload.password),
                               role="owner", nama=nama, wa=wa, is_active=True)
            db.add(user)
            db.flush()
            store = models.Store(nama=nama_toko, kode=make_store_code(db, nama_toko),
                                 owner_id=user.id, is_active=True)
            db.add(store)
            db.flush()
            db.add(models.Membership(user_id=user.id, store_id=store.id, role="owner", is_active=True))
            inv.is_used = True
            inv.used_by = user.id
            db.commit()
            db.refresh(user)
            log_action(db, "auth.register_owner", target=username,
                       detail=f"toko={store.nama} kode={store.kode} invite={inv.code}",
                       store_id=store.id)
            return {"id": user.id, "username": user.username, "role": user.role,
                    "is_active": user.is_active, "nama": user.nama,
                    "store_id": store.id, "store_nama": store.nama, "store_kode": store.kode,
                    "created_at": user.created_at}
        else:  # member: gabung ke toko undangan
            user = models.User(username=username, password_hash=hash_password(payload.password),
                               role=inv.role, nama=nama, wa=wa, is_active=True)
            db.add(user)
            db.flush()
            db.add(models.Membership(user_id=user.id, store_id=inv.store_id, role=inv.role, is_active=True))
            inv.is_used = True
            inv.used_by = user.id
            db.commit()
            db.refresh(user)
            s = db.query(models.Store).filter(models.Store.id == inv.store_id).first()
            log_action(db, "auth.register_member", target=username,
                       detail=f"toko={s.nama if s else '?'} role={inv.role} invite={inv.code}",
                       store_id=inv.store_id)
            return {"id": user.id, "username": user.username, "role": user.role,
                    "is_active": user.is_active, "nama": user.nama,
                    "store_id": s.id if s else None, "store_nama": s.nama if s else None,
                    "store_kode": s.kode if s else None, "created_at": user.created_at}

    # ---------- Alur LEGACY: tanpa invite (butuh persetujuan superadmin) ----------
    role = (payload.role or "").strip().lower()
    if role not in allowed_legacy:
        raise HTTPException(status_code=400, detail=f"Tanpa kode undangan, role harus salah satu: {allowed_legacy}. Untuk akun Owner, daftar dengan kode undangan.")
    user = models.User(
        username=username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=False  # butuh persetujuan superadmin
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, "auth.register_legacy", target=username, detail=f"role={role} (pending)")
    return {"id": user.id, "username": user.username, "role": user.role,
            "is_active": user.is_active, "nama": user.nama,
            "store_id": None, "store_nama": None, "store_kode": None,
            "created_at": user.created_at}

class UpdateMeIn(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    foto: Optional[str] = None  # null = hapus foto

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
    if "foto" in payload.model_dump(exclude_unset=True):
        current.foto = payload.foto
    db.commit()
    db.refresh(current)
    return current

class UpdateUserIn(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None

@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UpdateUserIn, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if payload.username is not None:
        new_u = payload.username.strip()
        if len(new_u) < 3:
            raise HTTPException(status_code=400, detail="Username minimal 3 karakter")
        if new_u.lower() == "superadmin" and user.username.lower() != "superadmin":
            raise HTTPException(status_code=400, detail="Username superadmin tidak boleh dipakai")
        exists = db.query(models.User).filter(models.User.username == new_u, models.User.id != user_id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Username sudah dipakai")
        user.username = new_u
    if payload.role is not None:
        r = payload.role.strip().lower()
        allowed = ["admin", "kasir", "teknisi", "superadmin"]
        if r not in allowed:
            raise HTTPException(status_code=400, detail=f"Role harus salah satu: {allowed}")
        if user.role == "superadmin" and r != "superadmin":
            raise HTTPException(status_code=400, detail="Tidak bisa downgrade superadmin")
        # cegah buat superadmin baru sembarangan — hanya boleh jika current superadmin (sudah)
        user.role = r
    if payload.password is not None and payload.password != "":
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
        from ..auth import hash_password
        user.password_hash = hash_password(payload.password)
    is_reset = payload.password is not None and payload.password != ""
    db.commit()
    db.refresh(user)
    log_action(db, "user.reset_password" if is_reset else "user.update", target=user.username,
               detail=f"role={user.role} is_active={user.is_active}", actor=current)
    return user

@router.post("/toggle/{user_id}", response_model=UserOut)
def toggle_user(user_id: int, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="Tidak bisa bekukan akun sendiri")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="Tidak bisa bekukan superadmin")
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    log_action(db, "user.toggle", target=user.username,
               detail=f"is_active={user.is_active}", actor=current)
    return user

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current = Depends(require_superadmin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="Tidak bisa hapus superadmin")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="Tidak bisa hapus akun sendiri")
    uname = user.username
    db.delete(user)
    db.commit()
    log_action(db, "user.delete", target=uname, actor=current)
    return {"message": f"User {uname} dihapus"}

@router.post("/me/foto")
def upload_my_foto(file: UploadFile = File(...), db: Session = Depends(get_db), current = Depends(get_current_user)):
    """Upload foto profil sendiri — otomatis dikompres (max 256px, JPEG q70). Maks 5MB."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File harus gambar (JPG/PNG/WebP)")
    raw = file.file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran maksimal 5MB")
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((256, 256), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=70, optimize=True)
        blob = out.getvalue()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Gambar tidak valid / rusak")
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    av_dir = os.path.join(root, "frontend", "assets", "images", "avatars")
    os.makedirs(av_dir, exist_ok=True)
    for ext in ("jpg", "png", "webp", "jpeg"):
        p = os.path.join(av_dir, f"u{current.id}.{ext}")
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    with open(os.path.join(av_dir, f"u{current.id}.jpg"), "wb") as f:
        f.write(blob)
    current.foto = f"/assets/images/avatars/u{current.id}.jpg"
    db.commit()
    log_action(db, "user.foto", target=current.username, actor=current)
    return {"foto": current.foto, "size": len(blob)}

@router.post("/seed-superadmin")
def seed_superadmin(db: Session = Depends(get_db)):
    user = ensure_superadmin(db)
    return {"message": "superadmin ready", "username": user.username, "role": user.role}
