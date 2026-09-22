"""
Store context helper - BOS Fase 2 (scoping multi-toko).

Aturan resolve_store(db, current, store_id):
- store_id eksplisit -> toko harus ada & aktif; anonimus 401; non-member 403.
  (superadmin bebas semua toko)
- tanpa store_id + superadmin -> None (semua toko, perilaku legacy)
- tanpa store_id + member -> toko primer (membership aktif pertama)
- tanpa store_id + anonimus -> toko default (BGJ / toko aktif pertama,
  agar dashboard publik tetap tampil seperti dulu)
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from . import models


def default_store(db: Session) -> Optional[models.Store]:
    s = db.query(models.Store).filter(
        models.Store.kode == "BGJ",
        models.Store.is_active == True,
    ).first()
    if not s:
        s = db.query(models.Store).filter(
            models.Store.is_active == True,
        ).order_by(models.Store.id).first()
    return s


def resolve_store(db: Session, current, store_id: Optional[int]) -> Optional[models.Store]:
    if store_id is not None:
        s = db.query(models.Store).filter(models.Store.id == store_id).first()
        if not s or not s.is_active:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan / nonaktif")
        if not current:
            raise HTTPException(status_code=401, detail="Login dulu untuk akses toko ini")
        if current.role != "superadmin":
            m = db.query(models.Membership).filter(
                models.Membership.user_id == current.id,
                models.Membership.store_id == s.id,
                models.Membership.is_active == True,
            ).first()
            if not m:
                raise HTTPException(status_code=403, detail="Bukan anggota toko ini")
        return s
    if current and current.role == "superadmin":
        return None
    if current:
        m = db.query(models.Membership).filter(
            models.Membership.user_id == current.id,
            models.Membership.is_active == True,
        ).order_by(models.Membership.id).first()
        if not m:
            raise HTTPException(status_code=403, detail="Akun belum jadi anggota toko manapun — hubungi owner")
        s = db.query(models.Store).filter(models.Store.id == m.store_id).first()
        if not s or not s.is_active:
            raise HTTPException(status_code=403, detail="Toko tidak aktif")
        return s
    s = default_store(db)
    if not s:
        raise HTTPException(status_code=404, detail="Belum ada toko aktif")
    return s


def ensure_in_store(row, store: Optional[models.Store], label: str = "Data"):
    """404 jika baris bukan milik toko aktif (jangan bocorkan eksistensi)."""
    if store is None or row is None:
        return row
    if getattr(row, "store_id", None) != store.id:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=404, detail=f"{label} tidak ditemukan di toko ini")
    return row
