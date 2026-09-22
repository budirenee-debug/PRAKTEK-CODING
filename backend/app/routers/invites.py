from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from ..database import get_db
from .. import models, schemas
from ..audit import log_action
from .auth import require_superadmin
from ..auth import generate_invite_code

router = APIRouter(prefix="/invites", tags=["Invites"])


def _invite_to_out(db: Session, inv: models.Invite) -> dict:
    store_nama = None
    if inv.store_id:
        s = db.query(models.Store).filter(models.Store.id == inv.store_id).first()
        store_nama = s.nama if s else None
    used_by_username = None
    if inv.used_by:
        u = db.query(models.User).filter(models.User.id == inv.used_by).first()
        used_by_username = u.username if u else None
    return {
        "id": inv.id, "code": inv.code, "kind": inv.kind,
        "store_id": inv.store_id, "store_nama": store_nama, "role": inv.role,
        "is_used": inv.is_used, "used_by_username": used_by_username,
        "expires_at": inv.expires_at, "created_at": inv.created_at,
    }


def check_invite(db: Session, code: str) -> tuple[Optional[models.Invite], Optional[str]]:
    """Validasi kode invite. Return (invite, reason). reason None = valid."""
    if not code:
        return None, "Kode undangan kosong"
    inv = db.query(models.Invite).filter(models.Invite.code == code.strip().upper()).first()
    if not inv:
        return None, "Kode undangan tidak ditemukan"
    if inv.is_used:
        return None, "Kode undangan sudah dipakai"
    if inv.expires_at and datetime.utcnow() > inv.expires_at:
        return None, "Kode undangan kedaluwarsa"
    if inv.kind == "member":
        if not inv.store_id:
            return None, "Undangan member rusak (tanpa toko)"
        s = db.query(models.Store).filter(models.Store.id == inv.store_id).first()
        if not s or not s.is_active:
            return None, "Toko undangan tidak aktif"
    return inv, None


@router.post("", response_model=schemas.InviteOut, status_code=201)
def create_invite(payload: schemas.InviteCreate, db: Session = Depends(get_db), current=Depends(require_superadmin)):
    if payload.kind == "member":
        if not payload.store_id:
            raise HTTPException(status_code=400, detail="Invite member wajib store_id")
        s = db.query(models.Store).filter(models.Store.id == payload.store_id).first()
        if not s:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        r = (payload.role or "").strip().lower()
        if r not in ["admin", "kasir", "teknisi"]:
            raise HTTPException(status_code=400, detail="Invite member role harus admin/kasir/teknisi")
    else:
        payload.store_id = None
        payload.role = None
    days = payload.expires_days or 0
    inv = models.Invite(
        code=generate_invite_code(db),
        kind=payload.kind,
        store_id=payload.store_id,
        role=(payload.role or "").strip().lower() if payload.role else None,
        created_by=current.id,
        is_used=False,
        expires_at=(datetime.utcnow() + timedelta(days=days)) if days > 0 else None,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    log_action(db, "invite.create_owner" if inv.kind == "owner" else "invite.create_member",
               target=inv.code, detail=f"kind={inv.kind} role={inv.role} store_id={inv.store_id}",
               actor=current, store_id=inv.store_id)
    return _invite_to_out(db, inv)


@router.get("", response_model=list[schemas.InviteOut])
def list_invites(db: Session = Depends(get_db), current=Depends(require_superadmin)):
    invs = db.query(models.Invite).order_by(models.Invite.id.desc()).all()
    return [_invite_to_out(db, i) for i in invs]


@router.get("/validate", response_model=schemas.InviteValidateOut)
def validate_invite(code: str, db: Session = Depends(get_db)):
    """Publik — dipakai halaman register untuk cek kode sebelum submit."""
    inv, reason = check_invite(db, code)
    if not inv:
        return {"valid": False, "reason": reason}
    store_nama = None
    if inv.store_id:
        s = db.query(models.Store).filter(models.Store.id == inv.store_id).first()
        store_nama = s.nama if s else None
    return {"valid": True, "reason": None, "kind": inv.kind, "role": inv.role,
            "store_id": inv.store_id, "store_nama": store_nama}


@router.post("/{invite_id}/revoke", response_model=schemas.InviteOut)
def revoke_invite(invite_id: int, db: Session = Depends(get_db), current=Depends(require_superadmin)):
    inv = db.query(models.Invite).filter(models.Invite.id == invite_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invite tidak ditemukan")
    inv.is_used = True
    db.commit()
    db.refresh(inv)
    log_action(db, "invite.revoke", target=inv.code,
               detail=f"kind={inv.kind} store_id={inv.store_id}", actor=current,
               store_id=inv.store_id)
    return _invite_to_out(db, inv)
