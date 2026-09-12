"""
CRUD helper
"""
import json
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import datetime
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

def compute_deadline(base_date: date, dtype: str, explicit: date = None):
    """Harian=3 hari, Mingguan=7 hari dari base_date. Jika explicit deadline dikirim pakai itu."""
    if explicit:
        return explicit
    dtype = (dtype or "harian").lower()
    days = 3 if dtype == "harian" else 7
    if not base_date:
        base_date = date.today()
    return base_date + datetime.timedelta(days=days)

def compute_deadline_from_estimasi(estimasi: date = None, base_date: date = None, dtype: str = None, explicit: date = None):
    """Deadline berbasis estimasi_selesai: jika estimasi ada, deadline=estimasi (jatuh tempo = estimasi). Jika tidak, fallback ke today+3/7."""
    if explicit:
        return explicit, (dtype or "harian").lower()
    if estimasi:
        # infer dtype jika tidak dikirim: gap <=3 hari => harian, else mingguan
        if not dtype:
            try:
                gap = (estimasi - (base_date or date.today())).days
            except:
                gap = 3
            dtype = "harian" if gap <= 3 else "mingguan"
        else:
            dtype = dtype.lower()
        return estimasi, dtype
    # tidak ada estimasi -> pakai today + dtype
    dtype = (dtype or "harian").lower()
    base = base_date or date.today()
    return compute_deadline(base, dtype, None), dtype

def enrich_service(svc):
    """Tambah sisa_hari dan is_overdue dinamis untuk response. Deadline sekarang berbasis estimasi_selesai jika ada."""
    if not svc:
        return svc
    try:
        dl = svc.deadline
        # jika deadline kosong tapi estimasi ada -> pakai estimasi sebagai deadline
        if not dl and getattr(svc, 'estimasi_selesai', None):
            dl, dtype = compute_deadline_from_estimasi(svc.estimasi_selesai, getattr(svc, 'date', None), getattr(svc, 'deadline_type', None))
            svc.deadline = dl
            svc.deadline_type = dtype
        elif not dl and hasattr(svc, 'date') and svc.date:
            dl, dtype = compute_deadline_from_estimasi(None, svc.date, getattr(svc, 'deadline_type', 'harian'))
            svc.deadline = dl
            svc.deadline_type = dtype
        # sinkronkan deadline jika estimasi berubah tapi deadline masih mengikuti estimasi lama
        # (jika estimasi ada dan deadline != estimasi, anggap deadline mengikuti estimasi terbaru)
        if getattr(svc, 'estimasi_selesai', None) and dl != svc.estimasi_selesai and svc.deadline_type in (None, "harian", "mingguan"):
            # jika estimasi lebih baru, update deadline agar jatuh tempo = estimasi
            # hanya jika deadline sebelumnya berasal dari estimasi (bukan manual)
            try:
                if svc.estimasi_selesai != dl:
                    # update ke estimasi agar proses service deadline = estimasi
                    svc.deadline = svc.estimasi_selesai
                    dl = svc.deadline
                    # infer ulang dtype
                    gap = (dl - (svc.date or date.today())).days
                    svc.deadline_type = "harian" if gap <= 3 else "mingguan"
            except:
                pass
        if dl:
            delta = (dl - date.today()).days
            svc.sisa_hari = delta
            # overdue hanya jika belum selesai dan deadline lewat
            svc.is_overdue = delta < 0 and svc.status not in ["Selesai", "Sudah Diambil", "Dibatalkan", "Service Failed"]
        else:
            svc.sisa_hari = None
            svc.is_overdue = False
    except Exception:
        svc.sisa_hari = None
        svc.is_overdue = False
    return svc

# ----- Service -----
def get_service(db: Session, invoice: str):
    svc = db.query(models.Service).filter(models.Service.invoice == invoice).first()
    return enrich_service(svc)

def get_services(db: Session, skip: int = 0, limit: int = 100, status: str = None, search: str = None, device: str = None, deadline_type: str = None, overdue: bool = None):
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
    if deadline_type:
        q = q.filter(models.Service.deadline_type == deadline_type)
    q = q.order_by(desc(models.Service.created_at))
    rows = q.offset(skip).limit(limit).all()
    # enrich
    rows = [enrich_service(r) for r in rows]
    if overdue is True:
        rows = [r for r in rows if r.is_overdue]
    elif overdue is False:
        rows = [r for r in rows if not r.is_overdue]
    return rows

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

    # deadline berbasis estimasi_selesai: jika estimasi ada, deadline = estimasi
    dl, dtype = compute_deadline_from_estimasi(payload.estimasi_selesai, date.today(), payload.deadline_type, payload.deadline)

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
        penerima=payload.penerima,
        status=payload.status or "Antri",
        date=date.today(),
        estimasi_selesai=payload.estimasi_selesai,
        deadline_type=dtype,
        deadline=dl
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return enrich_service(svc)

def update_service(db: Session, invoice: str, payload: schemas.ServiceUpdate):
    svc = db.query(models.Service).filter(models.Service.invoice == invoice).first()
    if not svc:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "kelengkapan" in data and data["kelengkapan"] is not None:
        data["kelengkapan"] = kelengkapan_to_str(data["kelengkapan"])
    if "teknisi" in data and data["teknisi"]:
        tech = db.query(models.Technician).filter(models.Technician.nama == data["teknisi"]).first()
        if tech:
            data["technician_id"] = tech.id
    # handle perubahan estimasi_selesai / deadline berbasis estimasi
    if "estimasi_selesai" in data or "deadline_type" in data or "deadline" in data:
        # jika estimasi diubah, deadline mengikuti estimasi (jatuh tempo = estimasi)
        new_estimasi = data.get("estimasi_selesai", svc.estimasi_selesai)
        new_dtype = data.get("deadline_type", svc.deadline_type)
        new_dl_explicit = data.get("deadline", None)
        # jika ada explicit deadline dikirim, pakai itu
        if new_dl_explicit is not None:
            data["deadline"] = new_dl_explicit
            if new_dtype:
                data["deadline_type"] = new_dtype.lower()
        else:
            # hitung dari estimasi
            computed_dl, computed_dtype = compute_deadline_from_estimasi(new_estimasi, svc.date or date.today(), new_dtype, None)
            data["deadline"] = computed_dl
            data["deadline_type"] = computed_dtype
            # jika estimasi tidak dikirim tapi ada di payload, pastikan terset
            if "estimasi_selesai" in data:
                pass  # sudah ada
        # normalisasi dtype
        if "deadline_type" in data and data["deadline_type"]:
            data["deadline_type"] = data["deadline_type"].lower()
    for k, v in data.items():
        setattr(svc, k, v)
    db.commit()
    db.refresh(svc)
    return enrich_service(svc)

def delete_service(db: Session, invoice: str):
    svc = get_service(db, invoice)
    if not svc:
        return False
    db.delete(svc)
    db.commit()
    return True

def get_stats(db: Session):
    total = db.query(models.Service).count()
    dalam_proses = db.query(models.Service).filter(models.Service.status.in_(["Antri","Menunggu Konfirmasi","Dikerjakan","Menunggu Sparepart"])).count()
    selesai_hari = db.query(models.Service).filter(models.Service.status=="Selesai", models.Service.date==date.today()).count()
    pendapatan = db.query(func.coalesce(func.sum(models.Service.biaya),0)).filter(models.Service.date==date.today()).scalar() or 0
    antri = db.query(models.Service).filter(models.Service.status=="Antri").count()
    dikerjakan = db.query(models.Service).filter(models.Service.status=="Dikerjakan").count()
    sparepart = db.query(models.Service).filter(models.Service.status=="Menunggu Sparepart").count()
    selesai = db.query(models.Service).filter(models.Service.status=="Selesai").count()
    # deadline stats
    all_svc = db.query(models.Service).all()
    overdue = 0
    deadline_hari_ini = 0
    harian = 0
    mingguan = 0
    for s in all_svc:
        enrich_service(s)
        if getattr(s, 'is_overdue', False):
            overdue += 1
        if s.deadline == date.today():
            deadline_hari_ini += 1
        if (s.deadline_type or "harian") == "harian":
            harian += 1
        else:
            mingguan += 1
    return {
        "total_masuk": total,
        "dalam_proses": dalam_proses,
        "selesai_hari_ini": selesai_hari,
        "estimasi_pendapatan": int(pendapatan),
        "antri": antri,
        "dikerjakan": dikerjakan,
        "menunggu_sparepart": sparepart,
        "selesai": selesai,
        "overdue": overdue,
        "deadline_hari_ini": deadline_hari_ini,
        "harian": harian,
        "mingguan": mingguan
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
