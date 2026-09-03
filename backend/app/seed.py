"""
Seed data awal
"""
from sqlalchemy.orm import Session
from . import models
from datetime import date, timedelta
import json

def seed(db: Session):
    # ensure superadmin always
    from .auth import ensure_superadmin
    ensure_superadmin(db)
    # cek sudah ada?
    if db.query(models.Technician).count() > 0:
        return {"message": "already seeded (superadmin ensured)"}

    techs = [
        models.Technician(nama="Andi", foto="https://i.pravatar.cc/100?img=12"),
        models.Technician(nama="Sinta", foto="https://i.pravatar.cc/100?img=15"),
        models.Technician(nama="Budi", foto="https://i.pravatar.cc/100?img=8"),
    ]
    db.add_all(techs)
    db.flush()

    # customers + services (mimic defaultData JS)
    data = [
        {"invoice":"INV-2026-0118", "nama":"Renee Budiman", "wa":"081234567890", "device":"iPhone 11 64GB", "keluhan":"LCD pecah & baterai drop", "teknisi":"Andi", "biaya":850000, "status":"Dikerjakan", "date":date.today(), "kelengkapan":["HP Saja","+ Charger"]},
        {"invoice":"INV-2026-0119", "nama":"Dewi Lestari", "wa":"082112345678", "device":"Samsung A54", "keluhan":"Mati total habis jatuh", "teknisi":"Sinta", "biaya":450000, "status":"Antri", "date":date.today(), "kelengkapan":["HP Saja"]},
        {"invoice":"INV-2026-0120", "nama":"Budi Santoso", "wa":"081345678901", "device":"Xiaomi Redmi Note 12", "keluhan":"Kamera belakang blur", "teknisi":"Budi", "biaya":250000, "status":"Menunggu Sparepart", "date":date.today()-timedelta(days=1), "kelengkapan":["HP Saja","+ Dus"]},
        {"invoice":"INV-2026-0121", "nama":"Citra Amelia", "wa":"085678901234", "device":"Oppo Reno 8", "keluhan":"Speaker sember", "teknisi":"Andi", "biaya":180000, "status":"Selesai", "date":date.today()-timedelta(days=1), "kelengkapan":["HP Saja"]},
        {"invoice":"INV-2026-0122", "nama":"Fajar Pratama", "wa":"081987654321", "device":"iPhone XR", "keluhan":"Face ID tidak berfungsi", "teknisi":"Sinta", "biaya":650000, "status":"Antri", "date":date.today(), "kelengkapan":["HP Saja","+ Charger"]},
    ]

    for d in data:
        cust = db.query(models.Customer).filter(models.Customer.wa==d["wa"]).first()
        if not cust:
            cust = models.Customer(nama=d["nama"], wa=d["wa"])
            db.add(cust)
            db.flush()
        tech = db.query(models.Technician).filter(models.Technician.nama==d["teknisi"]).first()
        svc = models.Service(
            invoice=d["invoice"],
            customer_id=cust.id,
            technician_id=tech.id if tech else None,
            nama=d["nama"],
            wa=d["wa"],
            device=d["device"],
            keluhan=d["keluhan"],
            kelengkapan=json.dumps(d["kelengkapan"]),
            biaya=d["biaya"],
            teknisi=d["teknisi"],
            status=d["status"],
            date=d["date"]
        )
        db.add(svc)

    db.commit()
    return {"message": "seeded", "technicians": 3, "services": 5}
