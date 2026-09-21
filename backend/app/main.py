"""
Main FastAPI - B_gadget POS Service HP
Root + Models + SQLite
"""
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv

load_dotenv()

from .database import Base, engine, get_db
from .routers import services, customers, technicians, stats, auth, inventory
from . import models
from .seed import seed
from .auth import ensure_superadmin

# Create tables
Base.metadata.create_all(bind=engine)
# Migration: tambah kolom deadline & penerima & hasil jika DB lama belum ada
def _migrate_deadline():
    try:
        from sqlalchemy import text
        import datetime
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(services)")).fetchall()]
            if "deadline_type" not in cols:
                conn.execute(text("ALTER TABLE services ADD COLUMN deadline_type VARCHAR(20) DEFAULT 'harian'"))
                print("migrated: deadline_type")
            if "deadline" not in cols:
                conn.execute(text("ALTER TABLE services ADD COLUMN deadline DATE"))
                print("migrated: deadline")
            if "penerima" not in cols:
                conn.execute(text("ALTER TABLE services ADD COLUMN penerima VARCHAR(100)"))
                print("migrated: penerima")
            if "hasil" not in cols:
                conn.execute(text("ALTER TABLE services ADD COLUMN hasil VARCHAR(10)"))
                print("migrated: hasil JADI/TIDAK")
            if "keterangan" not in cols:
                conn.execute(text("ALTER TABLE services ADD COLUMN keterangan TEXT"))
                print("migrated: keterangan")
            conn.commit()
            # isi deadline kosong untuk data lama: prioritaskan estimasi_selesai jika ada, else today+3/7
            rows = conn.execute(text("SELECT invoice, date, estimasi_selesai, deadline_type, deadline FROM services WHERE deadline IS NULL")).fetchall()
            for inv, d, estimasi, dtype, dl in rows:
                if estimasi:
                    try:
                        est = datetime.date.fromisoformat(estimasi) if isinstance(estimasi, str) else estimasi
                        # infer dtype dari gap jika belum ada
                        base = datetime.date.fromisoformat(d) if isinstance(d, str) else (d or datetime.date.today())
                        gap = (est - base).days if est and base else 3
                        new_dtype = dtype or ("harian" if gap <=3 else "mingguan")
                        dl_date = est
                        conn.execute(text("UPDATE services SET deadline=:dl, deadline_type=:dt WHERE invoice=:inv"), {"dl": dl_date.isoformat() if hasattr(dl_date,'isoformat') else str(dl_date), "dt": new_dtype, "inv": inv})
                        continue
                    except Exception:
                        pass
                try:
                    base = datetime.date.fromisoformat(d) if isinstance(d, str) else d
                except:
                    base = datetime.date.today()
                dtype = dtype or "harian"
                days = 3 if dtype=="harian" else 7
                dl_date = base + datetime.timedelta(days=days) if base else datetime.date.today() + datetime.timedelta(days=days)
                conn.execute(text("UPDATE services SET deadline=:dl, deadline_type=:dt WHERE invoice=:inv"), {"dl": dl_date.isoformat(), "dt": dtype, "inv": inv})
            conn.commit()
            # sinkronkan deadline yang sudah ada tapi estimasi lebih baru: deadline = estimasi_selesai (jatuh tempo = estimasi)
            try:
                rows2 = conn.execute(text("SELECT invoice, estimasi_selesai, deadline FROM services WHERE estimasi_selesai IS NOT NULL AND estimasi_selesai != '' AND deadline != estimasi_selesai")).fetchall()
                for inv, est, dl in rows2:
                    conn.execute(text("UPDATE services SET deadline=:est WHERE invoice=:inv"), {"est": est, "inv": inv})
                conn.commit()
            except Exception as e2:
                print("sync deadline->estimasi skip:", e2)
    except Exception as e:
        print("migrate deadline fail:", e)
_migrate_deadline()
# ensure superadmin on startup
try:
    from sqlalchemy.orm import sessionmaker
    _Session = sessionmaker(bind=engine)
    _db = _Session()
    ensure_superadmin(_db)
    _db.close()
except Exception as e:
    print("ensure_superadmin startup fail:", e)

app = FastAPI(
    title="B_gadget POS Service HP API",
    description="Backend POS Service HP - FastAPI + SQLite. Kelola service masuk, pelanggan, teknisi, dan dashboard stats.",
    version="1.0.0",
    contact={"name": "B_gadget Team"},
)

# CORS - lock ke domain prod + localhost (fix P0-1 K2)
# P0: jangan "*" jika nanti butuh auth cookie; batasi origin
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://service.reneepsl.my.id,https://reneepsl.my.id,https://www.reneepsl.my.id,http://localhost:8000,http://localhost:5500,http://127.0.0.1:5500,http://127.0.0.1:8000").split(",")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_cache_html(request: Request, call_next):
    # HTML jangan di-cache browser/CDN (menu/tampilan selalu fresh tiap deploy).
    # Aset .js/.css sudah cache-busting via ?v= di index.html.
    resp = await call_next(request)
    try:
        if "text/html" in resp.headers.get("content-type", ""):
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            resp.headers["Pragma"] = "no-cache"
    except Exception:
        pass
    return resp

# Routers / Root API
app.include_router(auth.router, prefix="/api")
app.include_router(services.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(technicians.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")

# Serve frontend static (rapi: frontend/assets/*) — single source, hapus mount /root ambigu (fix P0-2)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
    if os.path.exists(ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
    # /root mount dihapus — duplikat root (index.html/style.css/script.js) adalah legacy,
    # akses canonical sekarang hanya via /frontend/* dan /assets/* (hindari drift)
    # legacy /index.html tetap di-serve via redirect di root() jika dibutuhkan

@app.get("/", tags=["Root"])
def root(request: Request):
    # Jika akses via browser (ketik reneepsl.my.id) -> redirect ke halaman login
    # API client tetap dapat JSON via Accept: application/json
    try:
        accept = request.headers.get("accept", "")
        # browser minta html -> redirect ke login
        if "text/html" in accept:
            return RedirectResponse(url="/frontend/login.html", status_code=302)
    except Exception:
        pass
    return {
        "message": "B_gadget POS Service HP API - Online",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "login": "/frontend/login.html",
        "endpoints": {
            "auth": "/api/auth/login (superadmin/bismillah)",
            "services": "/api/services",
            "customers": "/api/customers",
            "technicians": "/api/technicians",
            "stats": "/api/stats",
            "dashboard": "/api/stats/dashboard"
        }
    }

@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok", "db": "sqlite", "engine": str(engine.url)}

@app.post("/api/seed", tags=["Root"])
def seed_db(db: Session = Depends(get_db), current = Depends(auth.require_superadmin)):
    """Seed data awal dummy (idempotent) — butuh superadmin (fix P0-1)"""
    result = seed(db)
    return result

@app.get("/api/search", tags=["Root"])
def global_search(q: str, db: Session = Depends(get_db)):
    """Global search pelanggan, HP, invoice"""
    from sqlalchemy import or_
    like = f"%{q}%"
    data = db.query(models.Service).filter(
        or_(
            models.Service.nama.ilike(like),
            models.Service.wa.ilike(like),
            models.Service.device.ilike(like),
            models.Service.invoice.ilike(like),
            models.Service.keluhan.ilike(like),
            models.Service.imei.ilike(like)
        )
    ).limit(20).all()
    return data
