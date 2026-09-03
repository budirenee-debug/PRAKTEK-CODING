"""
CRUD helper
"""
import json
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import date
from . import models, schemas

def generate_invoice(db: Session) -> str:
    """Generate INV-YYYY-XXXX increment. Tahun ambil dari date.today().year"""
    year = date.today().year
    prefix = f"INV-{year}-"
    # cari max invoice tahun ini
    last = db.query(models.Service).filter(models.Service.invoice.like(f"{prefix}%")).order_by(desc(models.Service.invoice)).first()
    if last:
        try:
            num = int(last.invoice.split("-")[-1])
        except:
            num = 100
        new_num = num + 1
    else:
        new_num = 101  # mulai 0101 biar konsisten dengan dummy lama 0118
        # cek kalau sudah ada 0118 dummy, lanjutkan
        # fallback: hitung count+100
        cnt = db.query(models.Service).count()
        if cnt > 0:
            new_num = 100 + cnt + 1
    return f"{prefix}{str(new_num).zfill(4)}"

def kelengkapan_to_str(arr):
    if arr is None:
        return json.dumps([])
    return json.dumps(arr, ensure_ascii=False)

def kelengkapan_from_str(s):
    if not s:
        return []
    try:
        return json.loads(s)
    except:
        return []

# ----- Service -----
def get_service(db: Session, invoice: str):
    return db.query(models.Service).filter(models.Service.invoice == invoice).first()

def get_services(db: Session, skip: int = 0, limit: int = 100, status: str = None, search: str = None, device: str = None):
    q = db.query(models.Service)
    if status and status != "all":
        q = q.filter(models.Service.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (models.Service.nama.ilike(like)) |
            (models.Service.wa.ilike(like)) |
            (models.Service.device.ilike(like)) |
            (models.Service.invoice.ilike(like)) |
            (models.Service.keluhan.ilike(like))
        )
    if device:
        q = q.filter(models.Service.device.ilike(f"%{device}%"))
    q = q.order_by(desc(models.Service.created_at))
    return q.offset(skip).limit(limit).all()

def count_services(db: Session, status: str = None):
    q = db.query(models.Service)
    if status and status != "all":
        q = q.filter(models.Service.status == status)
    return q.count()

def create_service(db: Session, payload: schemas.ServiceCreate):
    invoice = generate_invoice(db)
    # upsert customer berdasarkan WA
    customer = db.query(models.Customer).filter(models.Customer.wa == payload.wa).first()
    if not customer:
        customer = models.Customer(nama=payload.nama, wa=payload.wa)
        db.add(customer)
        db.flush()  # dapat id
    else:
        # update nama jika berubah
        if customer.nama != payload.nama:
            customer.nama = payload.nama

    # cari technician_id jika nama teknisi diberikan
    tech_id = None
    if payload.teknisi:
        tech = db.query(models.Technician).filter(models.Technician.nama == payload.teknisi).first()
        if tech:
            tech_id = tech.id

    svc = models.Service(
        invoice=invoice,
        customer_id=customer.id,
        technician_id=tech_id,
        nama=payload.nama,
        wa=payload.wa,
        device=payload.device,
        imei=payload.imei,
        keluhan=payload.keluhan,
        kelengkapan=kelengkapan_to_str(payload.kelengkapan),
        biaya=payload.biaya,
        teknisi=payload.teknisi,
        status=payload.status or "Antri",
        date=date.today(),
        estimasi_selesai=payload.estimasi_selesai
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return svc

def update_service(db: Session, invoice: str, payload: schemas.ServiceUpdate):
    svc = get_service(db, invoice)
    if not svc:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "kelengkapan" in data and data["kelengkapan"] is not None:
        data["kelengkapan"] = kelengkapan_to_str(data["kelengkapan"])
    if "teknisi" in data and data["teknisi"]:
        tech = db.query(models.Technician).filter(models.Technician.nama == data["teknisi"]).first()
        if tech:
            data["technician_id"] = tech.id
    for k, v in data.items():
        setattr(svc, k, v)
    db.commit()
    db.refresh(svc)
    return svc

def delete_service(db: Session, invoice: str):
    svc = get_service(db, invoice)
    if not svc:
        return False
    db.delete(svc)
    db.commit()
    return True

def get_stats(db: Session):
    total = db.query(models.Service).count()
    dalam_proses = db.query(models.Service).filter(models.Service.status.in_(["Antri","Dikerjakan","Menunggu Sparepart"])).count()
    selesai_hari = db.query(models.Service).filter(models.Service.status=="Selesai", models.Service.date==date.today()).count()
    pendapatan = db.query(func.coalesce(func.sum(models.Service.biaya),0)).filter(models.Service.date==date.today()).scalar() or 0
    antri = db.query(models.Service).filter(models.Service.status=="Antri").count()
    dikerjakan = db.query(models.Service).filter(models.Service.status=="Dikerjakan").count()
    sparepart = db.query(models.Service).filter(models.Service.status=="Menunggu Sparepart").count()
    selesai = db.query(models.Service).filter(models.Service.status=="Selesai").count()
    return {
        "total_masuk": total,
        "dalam_proses": dalam_proses,
        "selesai_hari_ini": selesai_hari,
        "estimasi_pendapatan": int(pendapatan),
        "antri": antri,
        "dikerjakan": dikerjakan,
        "menunggu_sparepart": sparepart,
        "selesai": selesai
    }

# ----- Technician -----
def get_technicians(db: Session):
    return db.query(models.Technician).filter(models.Technician.is_active==1).all()

def create_technician(db: Session, payload: schemas.TechnicianCreate):
    t = models.Technician(nama=payload.nama, foto=payload.foto)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t

# ----- Customer -----
def get_customers(db: Session, search: str = None, device: str = None, skip: int=0, limit: int=50):
    # customer unik by WA, agregasi dari service
    # kita query service dulu lalu group, tapi simpel: query customer + join
    q = db.query(models.Customer)
    if search:
        like = f"%{search}%"
        q = q.filter((models.Customer.nama.ilike(like)) | (models.Customer.wa.ilike(like)))
    # device filter via join service
    if device:
        q = q.join(models.Service, models.Service.customer_id==models.Customer.id).filter(models.Service.device.ilike(f"%{device}%")).distinct()
    return q.offset(skip).limit(limit).all()

def get_customer_detail(db: Session, customer_id: int):
    c = db.query(models.Customer).filter(models.Customer.id==customer_id).first()
    if not c:
        return None
    total = db.query(models.Service).filter(models.Service.customer_id==c.id).count()
    last = db.query(models.Service).filter(models.Service.customer_id==c.id).order_by(desc(models.Service.date)).first()
    return c, total, last
