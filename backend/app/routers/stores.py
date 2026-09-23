from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..database import get_db
from .. import models, schemas
from ..audit import log_action
from .auth import get_current_user, require_superadmin

router = APIRouter(prefix="/stores", tags=["Stores"])


# ---------- Template WA per status (default; {variabel} diisi frontend) ----------
DEFAULT_WA_TEMPLATES = {
    "umum": "Halo {nama} 👋\nDari {toko}\nInvoice: {invoice}\nDevice: {device}\nKeluhan: {keluhan}\n\nTerima kasih 🙏",
    "service_masuk": "Halo {nama} 👋\nHP {device} sudah kami terima di {toko} ✅\nInvoice: {invoice}\nKeluhan: {keluhan}\nKami kabari lagi kalau sudah selesai. Terima kasih 🙏",
    "bisa_diambil": "Halo {nama} 👋\nKabar baik! HP {device} sudah SELESAI diperbaiki ✅\nInvoice: {invoice}\nBiaya: {biaya}\nSilakan diambil di {toko}. Terima kasih 🙏",
    "gagal": "Halo {nama} 🙏\nMohon maaf, HP {device} belum bisa diperbaiki (gratis, tidak ada biaya).\nInvoice: {invoice}\nSilakan diambil kembali di {toko}.",
    "sudah_diambil": "Halo {nama} 👋\nTerima kasih sudah service di {toko} 🙏\nInvoice: {invoice} • Device: {device}\nAda garansi — hubungi kami jika ada keluhan.",
    "klaim_garansi": "Halo {nama} 👋\nHP {device} kami terima untuk KLAIM GARANSI 🔁\nInvoice baru: {invoice} (dari {garansi_dari})\nKeluhan: {keluhan}\n{toko} — terima kasih 🙏",
    "nota_digital": "🧾 *NOTA SERVICE — {toko}*\n--------------------------\nInvoice: {invoice}\nTanggal: {tanggal}\nPelanggan: {nama}\nDevice: {device} ({imei})\nKeluhan: {keluhan}\nKondisi awal: {keterangan}\nKelengkapan: {kelengkapan}\nEstimasi selesai: {estimasi}\nBiaya: {biaya}\n--------------------------\n{toko} — {alamat_toko}\nWA: {wa_toko}\nTerima kasih 🙏",
}
WA_TEMPLATE_KEYS = list(DEFAULT_WA_TEMPLATES.keys())


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
    log_action(db, "store.create", target=s.kode,
               detail=f"{s.nama} id={s.id}", actor=current, store_id=s.id)
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


@router.patch("/{store_id}", response_model=schemas.StoreOut)
def update_store(store_id: int, payload: schemas.StoreUpdate,
                 db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Edit profil toko (nama/alamat/WA pelayanan). Owner/admin toko atau superadmin."""
    s, my_role = _require_store_manager(db, current, store_id)
    changed = []
    if payload.nama is not None:
        nama = payload.nama.strip()
        if len(nama) < 2:
            raise HTTPException(status_code=400, detail="Nama toko minimal 2 karakter")
        if nama != s.nama:
            s.nama = nama
            changed.append("nama")
    if payload.alamat is not None:
        alamat = (payload.alamat or "").strip() or None
        if alamat != s.alamat:
            s.alamat = alamat
            changed.append("alamat")
    if payload.wa is not None:
        wa = (payload.wa or "").strip() or None
        if wa != s.wa:
            s.wa = wa
            changed.append("wa")
    if not changed:
        return _store_to_out(db, s, role_saya=my_role)
    db.commit()
    db.refresh(s)
    log_action(db, "store.update", target=s.kode,
               detail=f"ubah: {','.join(changed)}", actor=current, store_id=s.id)
    return _store_to_out(db, s, role_saya=my_role)


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


# ---------- BOS Fase 3: undang tim per toko ----------
def _require_store_manager(db: Session, current, store_id: int):
    """Store harus ada & aktif; requester harus owner/admin toko itu (atau superadmin)."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    s = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not s or not s.is_active:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan / nonaktif")
    if current.role == "superadmin":
        return s, "superadmin"
    m = db.query(models.Membership).filter(
        models.Membership.user_id == current.id,
        models.Membership.store_id == store_id,
        models.Membership.is_active == True,
    ).first()
    if not m or m.role not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin toko yang boleh kelola tim")
    return s, m.role


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


@router.get("/{store_id}/invites", response_model=list[schemas.InviteOut])
def list_store_invites(store_id: int, db: Session = Depends(get_db), current=Depends(get_current_user)):
    _require_store_manager(db, current, store_id)
    invs = db.query(models.Invite).filter(
        models.Invite.store_id == store_id,
        models.Invite.kind == "member",
    ).order_by(models.Invite.id.desc()).all()
    return [_invite_to_out(db, i) for i in invs]


@router.post("/{store_id}/invites", response_model=schemas.InviteOut, status_code=201)
def create_store_invite(store_id: int, payload: schemas.StoreInviteCreate,
                        db: Session = Depends(get_db), current=Depends(get_current_user)):
    _require_store_manager(db, current, store_id)
    from ..auth import generate_invite_code
    days = payload.expires_days or 0
    inv = models.Invite(
        code=generate_invite_code(db),
        kind="member",
        store_id=store_id,
        role=(payload.role or "").strip().lower(),
        created_by=current.id,
        is_used=False,
        expires_at=(datetime.utcnow() + timedelta(days=days)) if days > 0 else None,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    log_action(db, "invite.create_member", target=inv.code,
               detail=f"role={inv.role}", actor=current, store_id=store_id)
    return _invite_to_out(db, inv)


@router.post("/{store_id}/invites/{invite_id}/revoke", response_model=schemas.InviteOut)
def revoke_store_invite(store_id: int, invite_id: int,
                        db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Batalkan kode invite toko (manager only). Kode jadi tidak bisa dipakai daftar."""
    _require_store_manager(db, current, store_id)
    inv = db.query(models.Invite).filter(
        models.Invite.id == invite_id,
        models.Invite.store_id == store_id,
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invite tidak ditemukan di toko ini")
    inv.is_used = True
    db.commit()
    db.refresh(inv)
    log_action(db, "invite.revoke", target=inv.code,
               detail=f"role={inv.role}", actor=current, store_id=store_id)
    return _invite_to_out(db, inv)


@router.patch("/{store_id}/members/{membership_id}", response_model=schemas.MembershipOut)
def update_member(store_id: int, membership_id: int, payload: schemas.MembershipUpdate,
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    s, my_role = _require_store_manager(db, current, store_id)
    m = db.query(models.Membership).filter(
        models.Membership.id == membership_id,
        models.Membership.store_id == store_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan di toko ini")
    # Guard anti-lockout: tidak boleh ubah status/role diri sendiri
    if m.user_id == current.id and current.role != "superadmin":
        if payload.is_active is False:
            raise HTTPException(status_code=400, detail="Tidak bisa nonaktifkan diri sendiri")
        if payload.role and payload.role != m.role:
            raise HTTPException(status_code=400, detail="Tidak bisa ubah role diri sendiri — minta owner lain")
    # Hanya owner/superadmin yang boleh kelola role owner
    if m.role == "owner" or (payload.role == "owner"):
        if not (my_role in ["owner", "superadmin"]):
            raise HTTPException(status_code=403, detail="Hanya owner yang boleh kelola role owner")
    if payload.role:
        m.role = payload.role
        # sinkronkan role global user jika membership ini satu-satunya yang aktif
        # (agar tab penerima/teknisi konsisten) — best effort, jangan gagalkan request
        try:
            u = db.query(models.User).filter(models.User.id == m.user_id).first()
            if u and u.role != "superadmin":
                others = db.query(models.Membership).filter(
                    models.Membership.user_id == m.user_id,
                    models.Membership.is_active == True,
                    models.Membership.id != m.id,
                ).count()
                if others == 0:
                    u.role = payload.role if payload.role in ["admin", "kasir", "teknisi"] else u.role
        except Exception:
            pass
    if payload.is_active is not None:
        # jangan nonaktifkan owner terakhir toko
        if payload.is_active is False and m.role == "owner":
            n_owner = db.query(models.Membership).filter(
                models.Membership.store_id == store_id,
                models.Membership.role == "owner",
                models.Membership.is_active == True,
            ).count()
            if n_owner <= 1:
                raise HTTPException(status_code=400, detail="Tidak bisa nonaktifkan owner terakhir toko")
        m.is_active = payload.is_active
    db.commit()
    db.refresh(m)
    u = db.query(models.User).filter(models.User.id == m.user_id).first()
    log_action(db, "member.update", target=u.username if u else f"uid={m.user_id}",
               detail=f"role={m.role} is_active={m.is_active}", actor=current,
               store_id=store_id)
    return {
        "id": m.id, "user_id": m.user_id, "username": u.username if u else None,
        "store_id": m.store_id, "store_nama": s.nama, "role": m.role,
        "is_active": m.is_active, "created_at": m.created_at,
    }


@router.delete("/{store_id}/members/{membership_id}")
def remove_member(store_id: int, membership_id: int,
                  db: Session = Depends(get_db), current=Depends(get_current_user)):
    s, my_role = _require_store_manager(db, current, store_id)
    m = db.query(models.Membership).filter(
        models.Membership.id == membership_id,
        models.Membership.store_id == store_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan di toko ini")
    if m.user_id == current.id and current.role != "superadmin":
        raise HTTPException(status_code=400, detail="Tidak bisa keluarkan diri sendiri — minta owner lain")
    if m.role == "owner" and my_role not in ["owner", "superadmin"]:
        raise HTTPException(status_code=403, detail="Hanya owner yang boleh keluarkan owner")
    if m.role == "owner":
        n_owner = db.query(models.Membership).filter(
            models.Membership.store_id == store_id,
            models.Membership.role == "owner",
            models.Membership.is_active == True,
        ).count()
        if n_owner <= 1:
            raise HTTPException(status_code=400, detail="Tidak bisa keluarkan owner terakhir toko")
    # soft-delete: nonaktifkan (riwayat service tetap utuh)
    m.is_active = False
    db.commit()
    u_rm = db.query(models.User).filter(models.User.id == m.user_id).first()
    log_action(db, "member.remove", target=u_rm.username if u_rm else f"uid={m.user_id}",
               detail=f"role={m.role}", actor=current, store_id=store_id)
    return {"message": "Anggota dikeluarkan dari toko (nonaktif)", "membership_id": m.id}


@router.get("/{store_id}/wa-templates", response_model=list[schemas.WaTemplateOut])
def list_wa_templates(store_id: int, db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Template WA efektif per status (custom toko, fallback default). Butuh login anggota."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    s = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not s or not s.is_active:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan / nonaktif")
    customs = {t.key: t for t in db.query(models.WaTemplate).filter(models.WaTemplate.store_id == store_id).all()}
    return [
        {"key": k,
         "template": customs[k].template if k in customs else v,
         "is_custom": k in customs,
         "updated_at": customs[k].updated_at if k in customs else None}
        for k, v in DEFAULT_WA_TEMPLATES.items()
    ]


@router.put("/{store_id}/wa-templates", response_model=schemas.WaTemplateOut)
def upsert_wa_template(store_id: int, payload: schemas.WaTemplateIn,
                       db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Ubah 1 template WA toko (owner/admin). Template kosong = reset ke default."""
    _require_store_manager(db, current, store_id)
    key = (payload.key or "").strip()
    if key not in DEFAULT_WA_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"key harus salah satu: {WA_TEMPLATE_KEYS}")
    tpl = (payload.template or "").strip()
    if not tpl:
        db.query(models.WaTemplate).filter(
            models.WaTemplate.store_id == store_id, models.WaTemplate.key == key).delete()
        db.commit()
        log_action(db, "wa.template_reset", target=key, actor=current, store_id=store_id)
        return {"key": key, "template": DEFAULT_WA_TEMPLATES[key], "is_custom": False, "updated_at": None}
    row = db.query(models.WaTemplate).filter(
        models.WaTemplate.store_id == store_id, models.WaTemplate.key == key).first()
    if row:
        row.template = tpl
    else:
        row = models.WaTemplate(store_id=store_id, key=key, template=tpl)
        db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, "wa.template", target=key, detail=f"{len(tpl)} karakter", actor=current, store_id=store_id)
    return {"key": key, "template": row.template, "is_custom": True, "updated_at": row.updated_at}
