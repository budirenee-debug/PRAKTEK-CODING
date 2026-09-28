from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from .. import models, schemas
from ..store_ctx import resolve_store, store_role, default_store
from .auth import get_current_user, require_superadmin

router = APIRouter(prefix="/audit", tags=["Audit"])

# action -> (nama pola, IKON, keterangan).  PENTING: ikon = EMOJI SAJA,
# nama ditambahkan di sisi UI. Kalau ikon ikut berisi nama, teks jadi ganda
# (mis. "🛠 Service Service") di dropdown & chip filter.
POLA = {
    "service":     ("Service",     "🛠", "Masuk, ubah, status, hapus, klaim garansi"),
    "stok":        ("Stok",        "📦", "Tambah, ubah harga/stok, hapus sparepart"),
    "alat":        ("Stok",        "📦", "Alat kerja: tambah, ubah, hapus"),
    "engine":      ("Engine",      "⚙️", "Aturan komisi, check-in, nombok, oper garansi, harga part"),
    "finance":     ("Keuangan",    "💸", "Kecelakaan kerja & refund dana"),
    "wa":          ("WA Template", "💬", "Ubah template pesan WhatsApp"),
    "store":       ("Toko",        "🏪", "Profil toko, buat/nonaktifkan cabang"),
    "invite":      ("Tim",         "👥", "Undangan owner/member, revoke kode"),
    "user":        ("Akun",        "🔑", "Reset password, ganti peran, bekukan, hapus"),
    "auth":        ("Masuk",       "🔐", "Login, gagal login, ganti password/foto"),
    "seed":        ("Sistem",      "🧩", "Seed, maintenance"),
    "customer":    ("Pelanggan",   "👤", "Tambah data pelanggan"),
}
POLA_IKON = {v[0]: v[1] for v in POLA.values()}

# action yang dianggap janggal / perlu diawasi owner
SENSITIF = ("hapus", "delete", "update_harga", "refund", "nombok", "set_part",
            "settings", "diskon", "role", "toggle", "revoke", "password", "seed", "ganti_peran")

# action spesifik yang SENSITIF walau kata kuncinya tidak ada di atas
# (mis. "stok.update" = ubah harga/stok part, "store.update" = ubah profil toko)
SENSITIF_AKSI = {"stok.update", "store.update", "service.update", "invite.create",
                 "auth.login_gagal", "user.update", "alat.update"}

LABEL = {
    "service.create": "Service baru masuk",
    "service.update": "Ubah data service",
    "service.update_harga": "Ubah harga service",
    "service.status": "Ganti status service",
    "service.klaim_garansi": "Klaim garansi",
    "service.hapus": "Hapus service",
    "stok.create": "Tambah sparepart",
    "stok.update": "Ubah stok / harga part",
    "stok.hapus": "Hapus sparepart",
    "alat.create": "Tambah alat",
    "alat.update": "Ubah alat",
    "alat.hapus": "Hapus alat",
    "engine.settings": "Ubah aturan engine",
    "engine.checkin": "Absen teknisi",
    "engine.nombok": "Input nombok",
    "engine.nombok_pabrik": "Nombok cacat pabrik",
    "engine.set_part": "Set harga part (UP)",
    "engine.oper_garansi": "Oper garansi",
    "finance.kecelakaan": "Catat kecelakaan kerja",
    "finance.kecelakaan_selesai": "Tutup kecelakaan kerja",
    "finance.refund": "Catat refund dana",
    "store.update": "Ubah profil toko",
    "store.create": "Buat cabang / toko baru",
    "user.update": "Ubah akun",
    "user.role": "Ganti peran akun",
    "user.toggle": "Bekukan / aktifkan akun",
    "user.hapus": "Hapus akun",
    "invite.create": "Buat kode undangan",
    "invite.revoke": "Batalkan undangan",
    "auth.login": "Login berhasil",
    "auth.login_gagal": "Login gagal",
    "auth.password": "Ganti password",
    "auth.foto": "Ubah foto profil",
    "seed.run": "Seed database",
}


def _klasifikasi(action: str):
    prefix = (action or "").split(".")[0]
    pola = POLA.get(prefix)
    nama_pola = pola[0] if pola else "Lainnya"
    ikon = pola[1] if pola else "•"
    ket = pola[2] if pola else "Aksi lain"
    level = "tinggi" if (action in SENSITIF_AKSI
                         or any(k in (action or "") for k in SENSITIF)) else "normal"
    return {"pola": nama_pola, "ikon": ikon, "ket_pola": ket, "level": level,
            "label": LABEL.get(action, action)}


@router.get("", response_model=list[schemas.AuditLogOut])
def list_audit(
    limit: int = 100,
    action: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current = Depends(require_superadmin),
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


@router.get("/antifraud")
def antifraud(store_id: Optional[int] = Query(None),
              level: Optional[str] = Query(None, description="tinggi | normal"),
              pola: Optional[str] = Query(None, description="Service/Stok/Engine/Keuangan/WA Template/Toko/Tim/Akun/Masuk/Sistem/Pelanggan"),
              actor: Optional[str] = Query(None, description="username pelaku (partial)"),
              q: Optional[str] = Query(None, description="cari di actor/target/detail/action"),
              since: Optional[str] = Query(None, description="YYYY-MM-DD"),
              limit: int = Query(200, ge=1, le=500),
              offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Log aktivitas KESELURUHAN toko untuk owner/admin (scoped per toko).
    Level 'tinggi' = aksi yang perlu diawasi (hapus, ubah harga, refund, nombok, peran, password).
    Filter: level, pola, actor (username), q (teks), since (tanggal), limit/offset."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh lihat log anti-fraud")
    query = db.query(models.AuditLog)
    if store is not None:
        query = query.filter(models.AuditLog.store_id == store.id)
    if actor:
        query = query.filter(models.AuditLog.actor_username.ilike(actor.strip()))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (models.AuditLog.actor_username.ilike(like))
            | (models.AuditLog.target.ilike(like))
            | (models.AuditLog.detail.ilike(like))
            | (models.AuditLog.action.ilike(like))
        )
    if since:
        query = query.filter(models.AuditLog.created_at >= since.strip() + " 00:00:00")
    rows = query.order_by(models.AuditLog.id.desc()).all()
    users = {u.id: u for u in db.query(models.User).all()}
    techs = {t.nama: t for t in db.query(models.Technician).all()}
    out, hit_pola, hit_level = [], {}, {"tinggi": 0, "normal": 0}
    aktor = {}
    for r in rows:
        k = _klasifikasi(r.action)
        if level and k["level"] != level:
            continue
        if pola and k["pola"] != pola:
            continue
        u = users.get(r.actor_id)
        peran = (u.role if u else None) or ("teknisi" if (r.actor_username in techs) else "publik")
        hit_pola[k["pola"]] = hit_pola.get(k["pola"], 0) + 1
        hit_level[k["level"]] = hit_level.get(k["level"], 0) + 1
        nm = r.actor_username or "(publik)"
        a = aktor.setdefault(nm, {"nama": nm, "jumlah": 0, "tinggi": 0, "peran": peran})
        a["jumlah"] += 1
        if k["level"] == "tinggi":
            a["tinggi"] += 1
        out.append({"id": r.id, "created_at": r.created_at, "actor": nm,
                    "peran": peran, "action": r.action, "label": k["label"],
                    "target": r.target, "detail": r.detail,
                    "pola": k["pola"], "ikon": k["ikon"], "ket_pola": k["ket_pola"],
                    "level": k["level"]})
    total = len(out)
    start = max(0, int(offset or 0))
    return {"rows": out[start:start + max(1, min(limit or 200, 500))],
            "total": total,
            "aktor": sorted(aktor.values(), key=lambda x: -x["jumlah"]),
            "pola": [{"nama": p, "jumlah": hit_pola[p], "ikon": POLA_IKON.get(p, "•")}
                     for p in sorted(hit_pola, key=lambda x: -hit_pola[x])],
            "jumlah_tinggi": hit_level.get("tinggi", 0),
            "jumlah_normal": hit_level.get("normal", 0),
            "store": {"id": store.id, "nama": store.nama} if store else None}


@router.get("/antifraud/aksi")
def daftar_aksi(db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Daftar semua action yang pernah tercatat + pola/label-nya (untuk filter UI)."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    rows = db.query(models.AuditLog.action).distinct().all()
    seen = {}
    for (a,) in rows:
        k = _klasifikasi(a)
        seen[a] = {"action": a, "label": k["label"], "pola": k["pola"], "level": k["level"]}
    return sorted(seen.values(), key=lambda x: (x["pola"], x["action"]))
