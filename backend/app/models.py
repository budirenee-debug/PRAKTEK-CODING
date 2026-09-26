"""
Models - SQLAlchemy ORM
B_gadget POS Service HP
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, func, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Technician(Base):
    __tablename__ = "technicians"
    __table_args__ = (UniqueConstraint("nama", "store_id", name="uq_technician_nama_store"),)

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)  # multi-toko BOS
    nama = Column(String(100), nullable=False, index=True)  # unik per toko (composite)
    foto = Column(String(255), nullable=True)  # URL avatar
    is_active = Column(Integer, default=1)  # 1 aktif, 0 nonaktif
    level = Column(String(20), default="junior")  # Business Engine: senior / junior
    created_at = Column(DateTime, default=func.now())

    services = relationship("Service", back_populates="technician_obj")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("wa", "store_id", name="uq_customer_wa_store"),)

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)  # multi-toko BOS
    nama = Column(String(120), nullable=False, index=True)
    wa = Column(String(20), nullable=False, index=True)  # unik per toko (composite)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    services = relationship("Service", back_populates="customer")


class Service(Base):
    __tablename__ = "services"

    # Invoice sebagai PK string: INV-2026-XXXX
    invoice = Column(String(20), primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)  # multi-toko BOS
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)

    # Denormalized untuk kompatibilitas frontend lama (cepat)
    nama = Column(String(120), nullable=False)
    wa = Column(String(20), nullable=False, index=True)
    device = Column(String(120), nullable=False)
    imei = Column(String(30), nullable=True)
    keluhan = Column(Text, nullable=False)
    kelengkapan = Column(Text, nullable=True)  # JSON string: ["HP Saja","+ Charger"]
    biaya = Column(Integer, default=0)
    teknisi = Column(String(100), nullable=True)  # nama teknisi (denormalized)
    status = Column(String(30), default="Antri", index=True)  # Antri, Dikerjakan, Menunggu Sparepart, Selesai, Dibatalkan

    date = Column(Date, default=datetime.date.today)  # tanggal masuk
    estimasi_selesai = Column(Date, nullable=True)
    # deadline: harian = 3 hari, mingguan = 7 hari — sekarang deadline berbasis estimasi_selesai jika ada
    deadline_type = Column(String(20), default="harian")  # harian / mingguan (auto dari estimasi)
    deadline = Column(Date, nullable=True)  # tanggal deadline (auto = estimasi_selesai atau today+3/7)
    penerima = Column(String(100), nullable=True)  # penerima di Service Masuk (anggota terdaftar)
    hasil = Column(String(10), nullable=True)  # JADI / TIDAK - untuk Bisa Diambil (apakah HP jadi diperbaiki)
    keterangan = Column(Text, nullable=True)  # keterangan pengerjaan di Proses Service
    # garansi: klaim ulang tanpa input baru — masa garansi opsional dari tanggal diambil
    garansi_hari = Column(Integer, nullable=True)  # lama garansi hari (opsional, editable)
    garansi_sampai = Column(Date, nullable=True)  # batas klaim (auto = tgl diambil + hari, editable)
    garansi_dari = Column(String(20), nullable=True)  # invoice asal jika ini hasil klaim garansi
    metode_bayar = Column(String(20), nullable=True)  # Tunai / Transfer / QRIS (diisi saat Sukses via popup garansi)
    diambil_at = Column(DateTime, nullable=True)  # kapan status jadi Sukses/Sudah Diambil (auto, untuk tgl pengambilan & basis garansi)
    diambil_oleh = Column(String(120), nullable=True)  # siapa yang ambil HP (default = nama pelanggan, diisi via popup garansi)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    customer = relationship("Customer", back_populates="services")
    technician_obj = relationship("Technician", back_populates="services")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)  # superadmin
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="superadmin")  # superadmin, owner, admin, kasir, teknisi
    nama = Column(String(120), nullable=True)  # nama lengkap (wajib untuk owner baru via invite)
    wa = Column(String(20), nullable=True)  # no WA (wajib untuk owner baru via invite)
    foto = Column(String(255), nullable=True)  # path foto profil (/assets/images/avatars/u{id}.jpg)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime, nullable=True)

    memberships = relationship("Membership", back_populates="user")


class Sparepart(Base):
    __tablename__ = "spareparts"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)  # multi-toko BOS
    nama = Column(String(120), nullable=False, index=True)
    merk = Column(String(20), nullable=False, default="LAIN", index=True)  # IPHONE/SAMSUNG/XIAOMI/OPPO/VIVO/INFINIX/LAIN
    kategori = Column(String(30), nullable=False, default="Display")
    masuk = Column(Integer, default=0)
    keluar = Column(Integer, default=0)
    stok = Column(Integer, default=0)
    harga = Column(Integer, default=0)  # harga JUAL ke pelanggan
    harga_beli = Column(Integer, default=0)  # harga BELI/modal dari supplier
    tgl = Column(Date, default=datetime.date.today)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Alat(Base):
    __tablename__ = "alats"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)  # multi-toko BOS
    nama = Column(String(120), nullable=False, index=True)
    kondisi = Column(String(30), nullable=False, default="Baik")  # Baik/Perlu Kalibrasi/Rusak/Dipinjam
    peminjam = Column(String(100), nullable=False, default="-")
    masuk = Column(Integer, default=0)
    keluar = Column(Integer, default=0)
    stok = Column(Integer, default=0)
    harga = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# ---------- BOS SERVICE multi-toko ----------

class Store(Base):
    """Toko/cabang. 1 owner bisa punya banyak toko, 1 user bisa jadi anggota banyak toko."""
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(120), nullable=False)
    kode = Column(String(10), unique=True, nullable=False, index=True)  # prefix invoice, mis. BGJ
    alamat = Column(String(255), nullable=True)
    wa = Column(String(20), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    memberships = relationship("Membership", back_populates="store")


class Membership(Base):
    """Keanggotaan user di toko + peran di toko itu. 1 user boleh multi-toko."""
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    role = Column(String(20), default="kasir")  # owner, admin, kasir, teknisi
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="memberships")
    store = relationship("Store", back_populates="memberships")


class Invite(Base):
    """Kode undangan. kind=owner -> daftar jadi owner + buat toko baru.
    kind=member -> gabung ke store_id sebagai role tertentu."""
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)  # BOS-XXXX-XXXX
    kind = Column(String(10), default="owner")  # owner | member
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)  # wajib untuk member
    role = Column(String(20), nullable=True)  # role untuk member: admin/kasir/teknisi
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_used = Column(Boolean, default=False)
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())


class AuditLog(Base):
    """Jejak aksi penting platform (dev dashboard). Ditulis setelah aksi sukses commit."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=func.now(), index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_username = Column(String(50), nullable=True)
    action = Column(String(50), nullable=False, index=True)  # mis. invite.create_owner
    target = Column(String(120), nullable=True)  # mis. kode invite / username
    detail = Column(Text, nullable=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)


class WaTemplate(Base):
    """Template pesan WA per toko per status. Kosong = pakai default."""
    __tablename__ = "wa_templates"
    __table_args__ = (UniqueConstraint("store_id", "key", name="uq_wa_tpl_store_key"),)

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    key = Column(String(30), nullable=False, index=True)  # service_masuk/bisa_diambil/gagal/sudah_diambil/klaim_garansi/umum
    template = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# ---------- BUSINESS ENGINE (1 toko dulu, semua bawa store_id) ----------

class StoreSettings(Base):
    """Aturan Business Engine per toko. 1 baris per toko. Edit hanya owner."""
    __tablename__ = "store_settings"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, unique=True, index=True)
    uang_hadir = Column(Integer, default=25000)  # flat harian saat check-in tepat waktu
    jam_masuk = Column(String(5), default="09:00")  # HH:MM
    toleransi_mnt = Column(Integer, default=15)
    komisi_senior = Column(Integer, default=50)  # persen
    komisi_junior = Column(Integer, default=35)  # persen
    kuota_ringan_per_berat = Column(Integer, default=2)  # revisi blueprint: 2:1 harian
    cicilan_max_pct = Column(Integer, default=20)  # max potong komisi harian
    toleransi_junior_rp = Column(Integer, default=100000)  # 1x/bln ditanggung toko
    keyword_berat = Column(String(255), default="IC,BOARD,MATI TOTAL,MESIN")
    keyword_ringan = Column(String(255), default="LCD,BATERAI,SOFTWARE")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ServiceEngine(Base):
    """Jantung engine 1-to-1 dengan services via invoice. services tetap ramping."""
    __tablename__ = "service_engine"

    invoice = Column(String(20), ForeignKey("services.invoice"), primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    kategori = Column(String(20), default="ringan")  # berat / ringan (manual + default auto)
    harga_part_up = Column(Integer, default=0)  # harga UP yg dilihat teknisi (pajak toko)
    modal_asli = Column(Integer, default=0)  # rahasia owner only
    jasa_bersih = Column(Integer, default=0)  # auto = biaya - harga_part_up
    komisi_teknisi = Column(Integer, default=0)  # auto % senior/junior
    komisi_status = Column(String(20), default="pending")  # pending / cair (cair saat Sudah Diambil)
    dioper_dari = Column(String(100), nullable=True)
    dioper_ke = Column(String(100), nullable=True)
    dioper_oleh = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ServicePart(Base):
    """Snapshot part yg dipakai per invoice. Kunci harga saat itu."""
    __tablename__ = "service_parts"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    invoice = Column(String(20), ForeignKey("services.invoice"), nullable=False, index=True)
    sparepart_id = Column(Integer, ForeignKey("spareparts.id"), nullable=True)
    nama_snapshot = Column(String(120), nullable=False)
    harga_up_snapshot = Column(Integer, default=0)
    modal_asli_snapshot = Column(Integer, default=0)
    qty = Column(Integer, default=1)
    created_at = Column(DateTime, default=func.now())


class Attendance(Base):
    """Check-in harian teknisi. 1x per hari per teknisi."""
    __tablename__ = "attendances"
    __table_args__ = (UniqueConstraint("technician_id", "tanggal", name="uq_attendance_tech_tgl"),)

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False, index=True)
    tanggal = Column(Date, nullable=False, index=True)
    jam_checkin = Column(String(5), nullable=True)  # HH:MM
    on_time = Column(Boolean, default=False)
    allowance_rp = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


class TechDebt(Base):
    """Hutang nombok kelalaian 50:50. Cicil max 20% komisi harian."""
    __tablename__ = "tech_debts"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False, index=True)
    invoice_penyebab = Column(String(20), nullable=True, index=True)
    total_rugi = Column(Integer, default=0)  # harga modal yg rusak
    beban_teknisi = Column(Integer, default=0)  # 50% (0 jika toleransi junior)
    beban_toko = Column(Integer, default=0)  # 50% (+ toleransi)
    sudah_dicicil = Column(Integer, default=0)
    sisa = Column(Integer, default=0)
    sebab = Column(String(20), default="kelalaian")  # kelalaian / cacat_pabrik
    status = Column(String(20), default="belum")  # belum / lunas
    created_at = Column(DateTime, default=func.now())


class CommissionLedger(Base):
    """Buku kas resmi. Sumber untuk Laporan Teknisi Tab2 & Kas Saya."""
    __tablename__ = "commission_ledgers"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False, index=True)
    tanggal = Column(Date, default=datetime.date.today, index=True)
    invoice = Column(String(20), nullable=True, index=True)
    tipe = Column(String(30), nullable=False, index=True)  # komisi_cair / allowance / potongan_cicilan / hutang_baru / toleransi_toko
    masuk_rp = Column(Integer, default=0)
    keluar_rp = Column(Integer, default=0)
    sisa_hutang_saat_itu = Column(Integer, default=0)
    keterangan = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
