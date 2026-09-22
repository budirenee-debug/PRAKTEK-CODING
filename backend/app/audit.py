"""
Audit helper - BOS dev dashboard.

log_action() dipanggil SETELAH aksi sukses commit, agar log = kejadian nyata.
Ditulis dengan commit sendiri + rollback aman, jadi tidak pernah menggagalkan request.
"""
from sqlalchemy.orm import Session
from . import models


def log_action(db: Session, action: str, target=None, detail=None, actor=None, store_id=None):
    """Catat 1 baris audit. actor = User atau None (aksi publik spt register)."""
    try:
        db.add(models.AuditLog(
            actor_id=getattr(actor, "id", None),
            actor_username=getattr(actor, "username", None),
            action=action,
            target=str(target) if target is not None else None,
            detail=str(detail) if detail is not None else None,
            store_id=store_id,
        ))
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print("audit log skip:", e)
