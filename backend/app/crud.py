"""
CRUD helper
"""
import json
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import datetime
from datetime import date
from . import models, schemas

def generate_invoice(db: Session, store=None) -> str:
    """Generate invoice increment. Per toko: {KODE}-{YYYY}-XXXX (mis. REN-2026-0001).
    Tanpa store: legacy INV-YYYY-XXXX (tidak berubah)."""
    year = date.today().year
    if store is not None and getattr(store, "kode", None):
        prefix = f"{store.kode}-{year}-"
        last = db.query(models.Service).filter(models.Service.invoice.like(f"{prefix}%")).order_by(desc(models.Service.invoice)).first()
        if last:
            try:
                num = int(last.invoice.split("-")[-1])
            except:
                num = 0
            new_num = num + 1
        else:
            new_num = 1
        return f"{prefix}{str(new_num).zfill(4)}"
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

TERMINAL_STATUSES = {"Service Sukses", "Selesai", "Sudah Diambil", "Dibatalkan", "Service Failed", "Garansi", "Bisa Diambil"}

def attach_engine(db: Session, svc):
    """Tempel data service_engine ke objek service (agar ServiceOut ada part/jasa/komisi)."""
    if not svc:
        return svc
    try:
        inv = getattr(svc, "invoice", None)
        if not inv:
            return svc
        row = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == inv).first()
        if row:
            svc.kategori = row.kategori
            svc.harga_part_up = row.harga_part_up
            svc.jasa_bersih = row.jasa_bersih
            svc.komisi_teknisi = row.komisi_teknisi
            svc.komisi_status = row.komisi_status
        else:
            svc.kategori = None
            svc.harga_part_up = 0
            svc.jasa_bersih = None
            svc.komisi_teknisi = None
            svc.komisi_status = None
    except Exception:
        pass
    return svc


def attach_engine_many(db: Session, rows):
    try:
        invs = [getattr(r, "invoice", None) for r in rows if getattr(r, "invoice", None)]
        if not invs:
            return rows
        emap = {e.invoice: e for e in db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice.in_(invs)).all()}
        for r in rows:
            e = emap.get(getattr(r, "invoice", None))
            if e:
                r.kategori = e.kategori
                r.harga_part_up = e.harga_part_up
                r.jasa_bersih = e.jasa_bersih
                r.komisi_teknisi = e.komisi_teknisi
                r.komisi_status = e.komisi_status
            else:
                r.kategori = None
                r.harga_part_up = 0
                r.jasa_bersih = None
                r.komisi_teknisi = None
                r.komisi_status = None
    except Exception:
        pass
    return rows


def enrich_service(svc):
    """Tambah sisa_hari dan is_overdue dinamis (virtual, tidak mutasi DB) — fix P0-5/6."""
    if not svc:
        return svc
    try:
        # hitung deadline efektif tanpa mutasi svc.deadline (hindari side-effect flush)
        dl = svc.deadline
        dtype = getattr(svc, 'deadline_type', None) or "harian"
        # jika deadline kosong tapi estimasi ada -> pakai estimasi sebagai deadline efektif
        if not dl and getattr(svc, 'estimasi_selesai', None):
            dl, dtype = compute_deadline_from_estimasi(svc.estimasi_selesai, getattr(svc, 'date', None), dtype)
        elif not dl and hasattr(svc, 'date') and svc.date:
            dl, dtype = compute_deadline_from_estimasi(None, svc.date, dtype)
        # jika estimasi ada dan deadline efektif != estimasi, anggap jatuh tempo = estimasi (virtual, tidak tulis DB)
        elif getattr(svc, 'estimasi_selesai', None) and dl and dl != svc.estimasi_selesai and dtype in ("harian", "mingguan", None):
            dl = svc.estimasi_selesai
            try:
                gap = (dl - (svc.date or date.today())).days
                dtype = "harian" if gap <= 3 else "mingguan"
            except:
                pass
        # sisa & overdue pakai deadline efektif (virtual, tidak commit ke DB di GET)
        effective_dl = dl
        effective_dtype = dtype
        if effective_dl:
            delta = (effective_dl - date.today()).days
            svc.sisa_hari = delta
            svc.is_overdue = delta < 0 and svc.status not in TERMINAL_STATUSES
            # untuk response, tampilkan deadline efektif jika berbeda (virtual — tidak di-commit di read path)
            if svc.deadline != effective_dl or svc.deadline_type != effective_dtype:
                svc.deadline = effective_dl
                svc.deadline_type = effective_dtype
        else:
            svc.sisa_hari = None
            svc.is_overdue = False
    except Exception:
        svc.sisa_hari = None
        svc.is_overdue = False
    return svc

# ----- Service -----
def get_service(db: Session, invoice: str, store_id=None):
    svc = db.query(models.Service).filter(models.Service.invoice == invoice).first()
    if svc and store_id is not None and svc.store_id != store_id:
        return None
    if svc:
        attach_engine(db, svc)
    return enrich_service(svc)

def get_services(db: Session, skip: int = 0, limit: int = 100, status: str = None, search: str = None, device: str = None, deadline_type: str = None, overdue: bool = None, store_id=None, teknisi_scope: set = None):
    q = db.query(models.Service)
    if store_id is not None:
        q = q.filter(models.Service.store_id == store_id)
    if teknisi_scope is not None:
        # teknisi: hanya miliknya + yang belum di-assign
        from sqlalchemy import or_ as _or
        from .store_ctx import UNASSIGNED_TEKNISI
        q = q.filter(_or(
            models.Service.teknisi.in_(list(teknisi_scope)),
            models.Service.teknisi.is_(None),
            models.Service.teknisi.in_(list(UNASSIGNED_TEKNISI)),
        ))
    if status and status != "all":
        q = q.filter(models.Service.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (models.Service.nama.ilike(like)) |
            (models.Service.wa.ilike(like)) |
            (models.Service.device.ilike(like)) |
            (models.Service.invoice.ilike(like)) |
            (models.Service.keluhan.ilike(like)) |
            (models.Service.imei.ilike(like))
        )
    if device:
        q = q.filter(models.Service.device.ilike(f"%{device}%"))
    if deadline_type:
        q = q.filter(models.Service.deadline_type == deadline_type)
    # overdue filter di SQL agar pagination benar (fix P1-7)
    if overdue is not None:
        # overdue = deadline < today AND status not in terminal
        today = date.today()
        if overdue is True:
            q = q.filter(models.Service.deadline != None).filter(models.Service.deadline < today).filter(models.Service.status.notin_(list(TERMINAL_STATUSES)))
        else:
            # not overdue = deadline >= today OR deadline is null OR status in terminal
            q = q.filter(
                (models.Service.deadline == None) |
                (models.Service.deadline >= today) |
                (models.Service.status.in_(list(TERMINAL_STATUSES)))
            )
    q = q.order_by(desc(models.Service.created_at))
    rows = q.offset(skip).limit(limit).all()
    attach_engine_many(db, rows)
    rows = [enrich_service(r) for r in rows]
    return rows

def count_services(db: Session, status: str = None, search: str = None, device: str = None, deadline_type: str = None, overdue: bool = None, store_id=None):
    q = db.query(models.Service)
    if store_id is not None:
        q = q.filter(models.Service.store_id == store_id)
    if status and status != "all":
        q = q.filter(models.Service.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (models.Service.nama.ilike(like)) |
            (models.Service.wa.ilike(like)) |
            (models.Service.device.ilike(like)) |
            (models.Service.invoice.ilike(like)) |
            (models.Service.keluhan.ilike(like)) |
            (models.Service.imei.ilike(like))
        )
    if device:
        q = q.filter(models.Service.device.ilike(f"%{device}%"))
    if deadline_type:
        q = q.filter(models.Service.deadline_type == deadline_type)
    if overdue is not None:
        today = date.today()
        if overdue is True:
            q = q.filter(models.Service.deadline != None).filter(models.Service.deadline < today).filter(models.Service.status.notin_(list(TERMINAL_STATUSES)))
        else:
            q = q.filter(
                (models.Service.deadline == None) |
                (models.Service.deadline >= today) |
                (models.Service.status.in_(list(TERMINAL_STATUSES)))
            )
    return q.count()

def create_service(db: Session, payload: schemas.ServiceCreate, store_id=None, store=None):
    invoice = generate_invoice(db, store)
    # upsert customer berdasarkan WA di toko yang sama
    cq = db.query(models.Customer).filter(models.Customer.wa == payload.wa)
    if store_id is not None:
        cq = cq.filter(models.Customer.store_id == store_id)
    customer = cq.first()
    if not customer:
        customer = models.Customer(nama=payload.nama, wa=payload.wa, store_id=store_id)
        db.add(customer)
        db.flush()  # dapat id
    else:
        # update nama jika berubah
        if customer.nama != payload.nama:
            customer.nama = payload.nama

    # cari technician_id jika nama teknisi diberikan (di toko yang sama)
    tech_id = None
    if payload.teknisi:
        tq = db.query(models.Technician).filter(models.Technician.nama == payload.teknisi)
        if store_id is not None:
            tq = tq.filter(models.Technician.store_id == store_id)
        tech = tq.first()
        if tech:
            tech_id = tech.id

    # deadline berbasis estimasi_selesai: jika estimasi ada, deadline = estimasi
    dl, dtype = compute_deadline_from_estimasi(payload.estimasi_selesai, date.today(), payload.deadline_type, payload.deadline)

    svc = models.Service(
        invoice=invoice,
        store_id=store_id,
        customer_id=customer.id,
        technician_id=tech_id,
        nama=payload.nama,
        wa=payload.wa,
        device=payload.device,
        imei=payload.imei,
        keluhan=payload.keluhan,
        keterangan=payload.keterangan,
        kelengkapan=kelengkapan_to_str(payload.kelengkapan),
        biaya=payload.biaya,
        teknisi=payload.teknisi,
        penerima=payload.penerima,
        metode_bayar=getattr(payload, 'metode_bayar', None),
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
    # garansi: masa hari diisi pada record selesai/diambil & batas masih kosong -> isi otomatis
    if data.get("garansi_hari"):
        try:
            cur_status = data.get("status", svc.status)
            if cur_status in ("Sudah Diambil", "Service Sukses", "Selesai") and "garansi_sampai" not in data and not svc.garansi_sampai:
                data["garansi_sampai"] = date.today() + datetime.timedelta(days=int(data["garansi_hari"]))
        except Exception:
            pass
    # tgl pengambilan: dicatat saat status berubah jadi Sukses/Sudah Diambil
    if data.get("status") in ("Sudah Diambil", "Service Sukses", "Selesai"):
        data["diambil_at"] = datetime.datetime.now()
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

def get_stats(db: Session, store_id=None):
    sq = db.query(models.Service)
    if store_id is not None:
        sq = sq.filter(models.Service.store_id == store_id)
    total = sq.count()
    dalam_proses = sq.filter(models.Service.status.in_(["Antri","Menunggu Konfirmasi","Dikerjakan","Menunggu Sparepart"])).count()
    selesai_hari = sq.filter(models.Service.status.in_(["Selesai","Service Sukses"]), models.Service.date==date.today()).count()
    pendapatan = sq.with_entities(func.coalesce(func.sum(models.Service.biaya),0)).filter(models.Service.date==date.today()).scalar() or 0
    antri = sq.filter(models.Service.status=="Antri").count()
    dikerjakan = sq.filter(models.Service.status=="Dikerjakan").count()
    sparepart = sq.filter(models.Service.status=="Menunggu Sparepart").count()
    selesai = sq.filter(models.Service.status.in_(["Selesai","Service Sukses"])).count()
    # deadline stats
    all_svc = sq.all()
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
def get_technicians(db: Session, store_id=None):
    q = db.query(models.Technician).filter(models.Technician.is_active==1)
    if store_id is not None:
        q = q.filter(models.Technician.store_id == store_id)
    return q.all()

def create_technician(db: Session, payload: schemas.TechnicianCreate, store_id=None):
    t = models.Technician(nama=payload.nama, foto=payload.foto,
                          level=(payload.level or "junior"), store_id=store_id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t

# ----- Customer -----
def get_customers(db: Session, search: str = None, device: str = None, skip: int=0, limit: int=50, store_id=None):
    # customer unik by WA, agregasi dari service
    # kita query service dulu lalu group, tapi simpel: query customer + join
    q = db.query(models.Customer)
    if store_id is not None:
        q = q.filter(models.Customer.store_id == store_id)
    if search:
        like = f"%{search}%"
        q = q.filter((models.Customer.nama.ilike(like)) | (models.Customer.wa.ilike(like)))
    # device filter via join service
    if device:
        q = q.join(models.Service, models.Service.customer_id==models.Customer.id).filter(models.Service.device.ilike(f"%{device}%")).distinct()
    return q.offset(skip).limit(limit).all()

def get_customer_detail(db: Session, customer_id: int, store_id=None):
    cq = db.query(models.Customer).filter(models.Customer.id==customer_id)
    if store_id is not None:
        cq = cq.filter(models.Customer.store_id == store_id)
    c = cq.first()
    if not c:
        return None
    sq = db.query(models.Service).filter(models.Service.customer_id==c.id)
    if store_id is not None:
        sq = sq.filter(models.Service.store_id == store_id)
    total = sq.count()
    last = sq.order_by(desc(models.Service.date)).first()
    return c, total, last

# ----- Sparepart (multi-PC sync) -----
def get_spareparts(db: Session, search: str = None, merk: str = None, kategori: str = None, store_id=None):
    q = db.query(models.Sparepart)
    if store_id is not None:
        q = q.filter(models.Sparepart.store_id == store_id)
    if search:
        like = f"%{search}%"
        q = q.filter((models.Sparepart.nama.ilike(like)) | (models.Sparepart.merk.ilike(like)) | (models.Sparepart.kategori.ilike(like)))
    if merk and merk != "all":
        q = q.filter(models.Sparepart.merk == merk.upper())
    if kategori and kategori != "all":
        q = q.filter(models.Sparepart.kategori == kategori)
    return q.order_by(models.Sparepart.updated_at.desc(), models.Sparepart.id.desc()).all()

def create_sparepart(db: Session, payload: schemas.SparepartCreate, store_id=None):
    # stok auto = masuk - keluar jika tidak dikirim
    stok = payload.stok
    if stok is None:
        stok = max(0, (payload.masuk or 0) - (payload.keluar or 0))
    # merk bebas — hanya rapikan huruf
    merk = (payload.merk or "LAIN").upper().strip()[:40] or "LAIN"
    sp = models.Sparepart(
        store_id=store_id,
        nama=payload.nama.strip(),
        merk=merk,
        kategori=payload.kategori or "Display",
        masuk=payload.masuk or 0,
        keluar=payload.keluar or 0,
        stok=stok,
        harga=payload.harga or 0,
        harga_beli=payload.harga_beli or 0,
        tgl=payload.tgl or date.today()
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp

def update_sparepart(db: Session, sp_id: int, payload: schemas.SparepartUpdate, actor=None):
    sp = db.query(models.Sparepart).filter(models.Sparepart.id == sp_id).first()
    if not sp:
        return None
    data = payload.model_dump(exclude_unset=True)
    # merk bebas — hanya rapikan huruf
    if "merk" in data and data["merk"]:
        data["merk"] = str(data["merk"]).upper().strip()[:40] or "LAIN"
    stok_awal = int(sp.stok or 0)
    for k, v in data.items():
        setattr(sp, k, v)
    # jika masuk/keluar berubah dan stok tidak di-set manual, auto
    if ("masuk" in data or "keluar" in data) and "stok" not in data:
        sp.stok = max(0, (sp.masuk or 0) - (sp.keluar or 0))
    # jika stok dikirim, pastikan konsisten
    if sp.stok is None:
        sp.stok = max(0, (sp.masuk or 0) - (sp.keluar or 0))
    # jejak: setiap ubah stok lewat edit manual dicatat sebagai penyesuaian
    stok_akhir = int(sp.stok or 0)
    if stok_akhir != stok_awal:
        bagian = []
        if "masuk" in data: bagian.append(f"masuk={data['masuk']}")
        if "keluar" in data: bagian.append(f"keluar={data['keluar']}")
        if "stok" in data: bagian.append(f"stok={data['stok']}")
        catat_mutasi(db, sp, "penyesuaian", stok_akhir - stok_awal, stok_awal, stok_akhir,
                     ref="edit: " + ",".join(bagian) if bagian else "edit", actor=actor)
    db.commit()
    db.refresh(sp)
    return sp

def delete_sparepart(db: Session, sp_id: int):
    sp = db.query(models.Sparepart).filter(models.Sparepart.id == sp_id).first()
    if not sp:
        return False
    db.delete(sp)
    db.commit()
    return True

# ----- Buku mutasi stok (jejak perubahan stok) -----
def catat_mutasi(db: Session, sp, tipe: str, qty: int, stok_sebelum, stok_sesudah,
                 ref=None, actor=None):
    """Catat 1 baris stock_moves. Tidak pernah gagalkan operasi utama (best-effort)."""
    try:
        db.add(models.StockMove(
            store_id=getattr(sp, "store_id", None),
            sparepart_id=sp.id,
            nama_snapshot=sp.nama,
            tipe=tipe,
            qty=int(qty),
            stok_sebelum=int(stok_sebelum or 0),
            stok_sesudah=int(stok_sesudah or 0),
            ref=(ref or None),
            actor=(getattr(actor, "username", None) or (actor if isinstance(actor, str) else None)),
        ))
    except Exception:
        pass


def catat_mutasi_plain(db: Session, sp_id: int, store_id, nama: str, tipe: str, qty: int,
                       stok_sebelum, stok_sesudah, ref=None, actor=None):
    """Varian kalau objek ORM sparepart sudah tidak tersedia (mis. setelah delete)."""
    try:
        db.add(models.StockMove(
            store_id=store_id, sparepart_id=sp_id, nama_snapshot=nama, tipe=tipe,
            qty=int(qty), stok_sebelum=int(stok_sebelum or 0), stok_sesudah=int(stok_sesudah or 0),
            ref=(ref or None),
            actor=(getattr(actor, "username", None) or (actor if isinstance(actor, str) else None)),
        ))
    except Exception:
        pass


def get_stock_moves(db: Session, store_id=None, sparepart_id=None, tipe=None, limit=100):
    q = db.query(models.StockMove)
    if store_id is not None:
        q = q.filter(models.StockMove.store_id == store_id)
    if sparepart_id is not None:
        q = q.filter(models.StockMove.sparepart_id == sparepart_id)
    if tipe:
        q = q.filter(models.StockMove.tipe == tipe)
    rows = q.order_by(models.StockMove.id.desc()).limit(int(limit or 100)).all()
    return [schemas.StockMoveOut(
        id=r.id, store_id=r.store_id, sparepart_id=r.sparepart_id, nama_snapshot=r.nama_snapshot,
        tipe=r.tipe, tipe_label=schemas.LABEL_MUTASI.get(r.tipe, r.tipe),
        qty=int(r.qty or 0), stok_sebelum=int(r.stok_sebelum or 0), stok_sesudah=int(r.stok_sesudah or 0),
        ref=r.ref, actor=r.actor, created_at=r.created_at,
    ) for r in rows]


def pakai_part(db: Session, sp, svc, qty: int = 1, actor=None):
    """Kurangi stok + catat pemakaian di service_parts dalam SATU transaksi.

    Service yang sudah terminal dikunci di router (lihat schemas.BISA_PAKAI_PART).
    Return (sparepart, service_part, error).
    """
    from sqlalchemy import text
    if sp is None:
        return None, None, "Sparepart tidak ditemukan"
    if svc is None:
        return None, None, "Service tidak ditemukan"
    stok = sp.stok if sp.stok is not None else max(0, (sp.masuk or 0) - (sp.keluar or 0))
    if stok < qty:
        return None, None, f"Stok tidak cukup (sisa {stok})"
    sid = getattr(sp, "store_id", None)
    res = db.execute(
        text(
            "UPDATE spareparts SET keluar = COALESCE(keluar,0) + :qty, stok = COALESCE(stok,0) - :qty, tgl = :tgl "
            "WHERE id = :id AND COALESCE(stok,0) >= :qty AND (:sid IS NULL OR store_id IS NULL OR store_id = :sid)"
        ),
        {"qty": qty, "tgl": date.today().isoformat(), "id": sp.id, "sid": sid},
    )
    if res.rowcount == 0:
        db.rollback()
        sp2 = db.query(models.Sparepart).filter(models.Sparepart.id == sp.id).first()
        return None, None, f"Stok tidak cukup (sisa {sp2.stok if sp2 else 0}) — ada yang pakai barusan"
    part = models.ServicePart(
        store_id=getattr(svc, "store_id", None) or sid,
        invoice=svc.invoice,
        sparepart_id=sp.id,
        nama_snapshot=sp.nama,
        harga_up_snapshot=int(sp.harga or 0),
        modal_asli_snapshot=int(sp.harga_beli or 0),
        qty=qty,
    )
    db.add(part)
    catat_mutasi(db, sp, "pakai", -qty, stok, stok - qty, ref=svc.invoice, actor=actor)
    db.commit()
    db.refresh(part)
    # Buku besar (prinsip mentor): TERPAKAI = HPP terbentuk (tanpa gerak kas).
    try:
        from .routers.finance import _ledger_add
        _ledger_add(db, part.store_id,
                    date.today(), "keluar", "B1",
                    f"HPP {svc.invoice}: {part.nama_snapshot} x{qty}",
                    int(part.modal_asli_snapshot or 0) * int(part.qty or 0),
                    "stok", ref_type="servicepart", ref_id=part.id,
                    oleh=getattr(actor, "username", None),
                    masuk_laba=True, pengaruh_kas=False)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print("ledger pakai_part skip:", e)
    sp = db.query(models.Sparepart).filter(models.Sparepart.id == sp.id).first()
    return sp, part, None


def kembalikan_part(db: Session, part, actor=None):
    """Hapus catatan service_parts + kembalikan stok (keluar turun, stok naik)."""
    from sqlalchemy import text
    if part is None:
        return False
    nama, qty = part.nama_snapshot, int(part.qty or 1)
    sp = None
    if part.sparepart_id:
        sp = db.query(models.Sparepart).filter(models.Sparepart.id == part.sparepart_id).first()
        db.execute(
            text(
                "UPDATE spareparts SET keluar = MAX(0, COALESCE(keluar,0) - :qty), "
                "stok = COALESCE(stok,0) + :qty, tgl = :tgl WHERE id = :id"
            ),
            {"qty": qty, "tgl": date.today().isoformat(), "id": part.sparepart_id},
        )
    db.delete(part)
    catat_mutasi_plain(db, part.sparepart_id, part.store_id, nama, "batal", qty,
                       (sp.stok if sp is not None else 0), (sp.stok + qty if sp is not None else qty),
                       ref=part.invoice, actor=actor)
    # batal pakai = HPP yang terbentuk ikut batal
    try:
        from . import models as _m
        db.query(_m.LedgerEntry).filter(
            _m.LedgerEntry.ref_type == "servicepart",
            _m.LedgerEntry.ref_id == part.id).delete(synchronize_session=False)
    except Exception as e:
        print("ledger kembalikan skip:", e)
    db.commit()
    return True


def masuk_part(db: Session, sp, qty: int = 1, actor=None, ref=None):
    """Terima barang: masuk naik, stok naik. Proper-nya pakai ini, bukan edit kolom manual."""
    from sqlalchemy import text
    if sp is None:
        return None, "Sparepart tidak ditemukan"
    if qty <= 0:
        return None, "Jumlah harus >= 1"
    stok = sp.stok if sp.stok is not None else max(0, (sp.masuk or 0) - (sp.keluar or 0))
    db.execute(
        text("UPDATE spareparts SET masuk = COALESCE(masuk,0) + :qty, stok = COALESCE(stok,0) + :qty, tgl = :tgl WHERE id = :id"),
        {"qty": qty, "tgl": date.today().isoformat(), "id": sp.id},
    )
    catat_mutasi(db, sp, "masuk", qty, stok, stok + qty, ref=ref, actor=actor)
    db.commit()
    sp = db.query(models.Sparepart).filter(models.Sparepart.id == sp.id).first()
    return sp, None


def list_service_parts(db: Session, store_id=None, invoice=None, teknisi_scope=None):
    """Semua pemakaian part di toko aktif. Label merk & teknisi di-join untuk tampilan."""
    q = db.query(models.ServicePart)
    if store_id is not None:
        q = q.filter(models.ServicePart.store_id == store_id)
    if invoice:
        q = q.filter(models.ServicePart.invoice == invoice)
    rows = q.order_by(models.ServicePart.id.desc()).all()
    if not rows:
        return []
    sp_ids = {r.sparepart_id for r in rows if r.sparepart_id}
    merks = {}
    if sp_ids:
        for p in db.query(models.Sparepart).filter(models.Sparepart.id.in_(sp_ids)).all():
            merks[p.id] = p.merk
    invs = {r.invoice for r in rows}
    if teknisi_scope:
        svc_q = db.query(models.Service).filter(models.Service.invoice.in_(invs))
        svc_q = svc_q.filter(models.Service.teknisi.in_(list(teknisi_scope)) | models.Service.teknisi.in_(["Menunggu Teknisi", "-", ""]))
        invs = {s.invoice for s in svc_q.all()}
        rows = [r for r in rows if r.invoice in invs]
    teknisis = {}
    if rows:
        for s in db.query(models.Service).filter(models.Service.invoice.in_({r.invoice for r in rows})).all():
            teknisis[s.invoice] = s.teknisi
    out = []
    for r in rows:
        out.append(
            schemas.ServicePartOut(
                id=r.id,
                store_id=r.store_id,
                invoice=r.invoice,
                sparepart_id=r.sparepart_id,
                nama_snapshot=r.nama_snapshot,
                merk=merks.get(r.sparepart_id) or "LAIN",
                harga_up_snapshot=int(r.harga_up_snapshot or 0),
                modal_asli_snapshot=int(r.modal_asli_snapshot or 0),
                qty=int(r.qty or 1),
                teknisi=teknisis.get(r.invoice) or "-",
                created_at=r.created_at,
            )
        )
    return out

# ----- Alat (multi-PC sync) -----
def get_alats(db: Session, search: str = None, kondisi: str = None, store_id=None):
    q = db.query(models.Alat)
    if store_id is not None:
        q = q.filter(models.Alat.store_id == store_id)
    if search:
        like = f"%{search}%"
        q = q.filter((models.Alat.nama.ilike(like)) | (models.Alat.kondisi.ilike(like)) | (models.Alat.peminjam.ilike(like)))
    if kondisi and kondisi != "all":
        q = q.filter(models.Alat.kondisi == kondisi)
    return q.order_by(models.Alat.updated_at.desc(), models.Alat.id.desc()).all()

def create_alat(db: Session, payload: schemas.AlatCreate, store_id=None):
    stok = payload.stok
    if stok is None:
        stok = max(0, (payload.masuk or 0) - (payload.keluar or 0))
    alat = models.Alat(
        store_id=store_id,
        nama=payload.nama.strip(),
        kondisi=payload.kondisi or "Baik",
        peminjam=payload.peminjam or "-",
        masuk=payload.masuk or 0,
        keluar=payload.keluar or 0,
        stok=stok,
        harga=payload.harga or 0
    )
    # auto kondisi Dipinjam jika peminjam != -
    if alat.peminjam != "-" and alat.kondisi == "Baik":
        alat.kondisi = "Dipinjam"
    db.add(alat)
    db.commit()
    db.refresh(alat)
    return alat

def update_alat(db: Session, alat_id: int, payload: schemas.AlatUpdate):
    alat = db.query(models.Alat).filter(models.Alat.id == alat_id).first()
    if not alat:
        return None
    data = payload.model_dump(exclude_unset=True)
    for k,v in data.items():
        setattr(alat, k, v)
    if ("masuk" in data or "keluar" in data) and "stok" not in data:
        alat.stok = max(0, (alat.masuk or 0) - (alat.keluar or 0))
    if alat.stok is None:
        alat.stok = max(0, (alat.masuk or 0) - (alat.keluar or 0))
    # auto kondisi
    if "peminjam" in data:
        if alat.peminjam != "-" and alat.kondisi == "Baik":
            alat.kondisi = "Dipinjam"
        elif alat.peminjam == "-" and alat.kondisi == "Dipinjam":
            alat.kondisi = "Baik"
    db.commit()
    db.refresh(alat)
    return alat

def delete_alat(db: Session, alat_id: int):
    alat = db.query(models.Alat).filter(models.Alat.id == alat_id).first()
    if not alat:
        return False
    db.delete(alat)
    db.commit()
    return True
