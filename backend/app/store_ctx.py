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
    """Toko default: BGJ jika AKTIF dipakai (ada data). Jika BGJ kosong tapi ada
    toko aktif lain yang berisi data (mis. kode diganti / cabang baru), pakai
    yang paling banyak aktivitasnya — agar superadmin & anonim tidak nyasar ke
    toko kosong dan mengira data hilang."""
    bgj = db.query(models.Store).filter(
        models.Store.kode == "BGJ",
        models.Store.is_active == True,
    ).first()
    if bgj and _store_isi(db, bgj.id) > 0:
        return bgj
    actives = db.query(models.Store).filter(
        models.Store.is_active == True).order_by(models.Store.id).all()
    if not actives:
        return None
    if len(actives) == 1:
        return actives[0]
    best, best_n = None, -1
    for s in actives:
        n = _store_isi(db, s.id)
        if n > best_n:
            best, best_n = s, n
    if best is not None and best_n > 0:
        return best
    return bgj or actives[0]


def _store_isi(db: Session, store_id: int) -> int:
    """Jumlah baris data milik toko (skor aktivitas, murah di SQLite kecil)."""
    try:
        return (
            db.query(models.Service).filter(models.Service.store_id == store_id).count()
            + db.query(models.Sparepart).filter(models.Sparepart.store_id == store_id).count()
            + db.query(models.LedgerEntry).filter(models.LedgerEntry.store_id == store_id).count()
            + db.query(models.Sale).filter(models.Sale.store_id == store_id).count()
        )
    except Exception:
        return 0


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


# ---------- Batas visibilitas teknisi (hanya kerjaan sendiri + tak bertuan) ----------
UNASSIGNED_TEKNISI = {"Menunggu Teknisi", "-", ""}


def store_role(db: Session, current, store) -> Optional[str]:
    """Peran requester di toko aktif: superadmin/owner/admin/kasir/teknisi, None jika bukan anggota."""
    if not current:
        return None
    if getattr(current, "role", None) == "superadmin":
        return "superadmin"
    if store is None:
        return getattr(current, "role", None)
    m = db.query(models.Membership).filter(
        models.Membership.user_id == current.id,
        models.Membership.store_id == store.id,
        models.Membership.is_active == True,
    ).first()
    return m.role if m else None


def teknisi_scope_names(current) -> set:
    """Nama-nama yang dianggap milik teknisi: username + nama lengkap akun."""
    names = set()
    if getattr(current, "username", None):
        names.add(current.username)
    if getattr(current, "nama", None):
        names.add(current.nama)
    return names


def is_own_or_free(svc_teknisi, names: set) -> bool:
    """True jika service milik teknisi (nama cocok) atau belum di-assign siapa pun."""
    if svc_teknisi in names:
        return True
    if svc_teknisi is None or svc_teknisi in UNASSIGNED_TEKNISI:
        return True
    return False
