"""
Main FastAPI - B_gadget POS Service HP
Root + Models + SQLite
"""
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import os

from .database import Base, engine, get_db
from .routers import services, customers, technicians, stats, auth
from . import models
from .seed import seed
from .auth import ensure_superadmin
from sqlalchemy.orm import Session

# Create tables
Base.metadata.create_all(bind=engine)
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

# CORS - izinkan frontend akses (Vite, file://, live-server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers / Root API
app.include_router(auth.router, prefix="/api")
app.include_router(services.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(technicians.router, prefix="/api")
app.include_router(stats.router, prefix="/api")

# Serve frontend static (rapi: frontend/assets/*)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    # juga serve assets langsung
    ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
    if os.path.exists(ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

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
def seed_db(db: Session = Depends(get_db)):
    """Seed data awal dummy (idempotent)"""
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
            models.Service.keluhan.ilike(like)
        )
    ).limit(20).all()
    return data
