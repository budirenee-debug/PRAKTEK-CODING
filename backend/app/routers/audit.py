from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from .. import models, schemas
from .auth import require_superadmin

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=list[schemas.AuditLogOut])
def list_audit(
    limit: int = 100,
    action: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current=Depends(require_superadmin),
):
    """Log aktivitas platform — superadmin only. Filter opsional: action & cari teks."""
    limit = max(1, min(limit or 100, 500))
    query = db.query(models.AuditLog).order_by(models.AuditLog.id.desc())
    if action:
        query = query.filter(models.AuditLog.action == action.strip())
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (models.AuditLog.actor_username.ilike(like))
            | (models.AuditLog.target.ilike(like))
            | (models.AuditLog.detail.ilike(like))
        )
    return query.limit(limit).all()
