"""
Schemas - Pydantic untuk validasi & response
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import datetime
from datetime import datetime as dt
import json

# ---------- Technician ----------
class TechnicianBase(BaseModel):
    nama: str = Field(..., min_length=2, max_length=100)
    foto: Optional[str] = None
    is_active: Optional[int] = 1

class TechnicianCreate(TechnicianBase):
    pass

class TechnicianOut(TechnicianBase):
    id: int
    created_at: Optional[dt] = None
    class Config:
        from_attributes = True

# ---------- Customer ----------
class CustomerBase(BaseModel):
    nama: str = Field(..., min_length=2, max_length=120)
    wa: str = Field(..., min_length=9, max_length=20)

    @field_validator('wa')
    @classmethod
    def wa_must_numeric(cls, v):
        # hapus spasi dan cek numeric
        cleaned = v.replace(" ", "").replace("-", "").replace("+", "")
        if not cleaned.isdigit():
            raise ValueError('No WA harus angka')
        return v

class CustomerCreate(CustomerBase):
    pass

class CustomerOut(CustomerBase):
    id: int
    created_at: Optional[dt] = None
    total_service: Optional[int] = 0
    terakhir_service: Optional[datetime.date] = None
    class Config:
        from_attributes = True

# ---------- Service ----------
class ServiceBase(BaseModel):
    nama: str = Field(..., min_length=2, max_length=120)
    wa: str = Field(..., min_length=9, max_length=20)
    device: str = Field(..., min_length=2, max_length=120)
    imei: Optional[str] = Field(None, max_length=30)
    keluhan: str = Field(..., min_length=5)
    kelengkapan: Optional[List[str]] = Field(default_factory=list)
    biaya: int = Field(default=0, ge=0)
    teknisi: Optional[str] = Field(None, max_length=100)
    penerima: Optional[str] = Field(None, max_length=100)  # penerima di Service Masuk (anggota terdaftar)
    hasil: Optional[str] = Field(None, max_length=10, description="JADI / TIDAK untuk Bisa Diambil")
    keterangan: Optional[str] = Field(None, max_length=1000, description="Keterangan pengerjaan di Proses Service")
    status: Optional[str] = Field(default="Antri")
    estimasi_selesai: Optional[datetime.date] = None
    deadline_type: Optional[str] = Field(default=None)  # harian=3 hari, mingguan=7 hari — auto dari estimasi_selesai jika kosong
    deadline: Optional[datetime.date] = None  # auto hitung dari estimasi_selesai jika kosong
    garansi_hari: Optional[int] = Field(default=None, ge=0, description="masa garansi hari, opsional/editable")
    garansi_sampai: Optional[datetime.date] = Field(default=None, description="batas klaim garansi (auto dari tgl diambil + hari, editable)")
    metode_bayar: Optional[str] = Field(default=None, max_length=20, description="Tunai / Transfer / QRIS")

    @field_validator('metode_bayar')
    @classmethod
    def validate_bayar(cls, v):
        if v is None or v == "":
            return None
        v = v.strip()
        allowed = ["Tunai", "Transfer", "QRIS"]
        if v not in allowed:
            raise ValueError(f'metode_bayar harus salah satu: {allowed}')
        return v

    @field_validator('hasil')
    @classmethod
    def validate_hasil(cls, v):
        if v is None or v == "":
            return None
        up = v.upper().strip()
        if up not in ["JADI", "TIDAK"]:
            raise ValueError('hasil harus JADI atau TIDAK')
        return up

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        # 'Selesai' legacy tetap diterima, tapi FE sekarang pakai 'Service Sukses'
        allowed = ["Antri", "Menunggu Konfirmasi", "Dikerjakan", "Menunggu Sparepart", "Selesai", "Service Sukses", "Dibatalkan", "Bisa Diambil", "Sudah Diambil", "Service Failed", "Garansi"]
        if v not in allowed:
            raise ValueError(f'Status harus salah satu: {allowed}')
        # normalisasi: simpan sebagai 'Service Sukses' agar konsisten
        if v == "Selesai":
            return "Service Sukses"
        return v

    @field_validator('deadline_type')
    @classmethod
    def validate_deadline_type(cls, v):
        if v is None:
            return v
        v = v.lower().strip()
        allowed = ["harian", "mingguan"]
        if v not in allowed:
            raise ValueError(f'deadline_type harus salah satu: {allowed}')
        return v

class ServiceCreate(ServiceBase):
    pass

class KlaimGaransiIn(BaseModel):
    """Body klaim garansi: keluhan baru wajib, teknisi & biaya opsional (default ikut asli / 0)."""
    keluhan: str = Field(..., min_length=5, max_length=1000)
    teknisi: Optional[str] = Field(None, max_length=100)
    biaya: int = Field(default=0, ge=0)

class ServiceUpdate(BaseModel):
    nama: Optional[str] = None
    wa: Optional[str] = None
    device: Optional[str] = None
    imei: Optional[str] = None
    keluhan: Optional[str] = None
    kelengkapan: Optional[List[str]] = None
    biaya: Optional[int] = Field(None, ge=0)
    teknisi: Optional[str] = None
    penerima: Optional[str] = None
    hasil: Optional[str] = Field(None, max_length=10)
    keterangan: Optional[str] = Field(None, max_length=1000)
    status: Optional[str] = None
    estimasi_selesai: Optional[datetime.date] = None
    deadline_type: Optional[str] = None
    deadline: Optional[datetime.date] = None
    garansi_hari: Optional[int] = Field(None, ge=0)
    garansi_sampai: Optional[datetime.date] = None
    metode_bayar: Optional[str] = Field(None, max_length=20)

    @field_validator('hasil')
    @classmethod
    def validate_hasil(cls, v):
        if v is None or v == "":
            return None
        up = v.upper().strip()
        if up not in ["JADI", "TIDAK"]:
            raise ValueError('hasil harus JADI atau TIDAK')
        return up

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = ["Antri", "Menunggu Konfirmasi", "Dikerjakan", "Menunggu Sparepart", "Selesai", "Service Sukses", "Dibatalkan", "Bisa Diambil", "Sudah Diambil", "Service Failed", "Garansi"]
        if v not in allowed:
            raise ValueError(f'Status harus salah satu: {allowed}')
        if v == "Selesai":
            return "Service Sukses"
        return v

    @field_validator('deadline_type')
    @classmethod
    def validate_deadline_type(cls, v):
        if v is None:
            return v
        v = v.lower().strip()
        allowed = ["harian", "mingguan"]
        if v not in allowed:
            raise ValueError(f'deadline_type harus {allowed}')
        return v

    @field_validator('metode_bayar')
    @classmethod
    def validate_bayar_upd(cls, v):
        if v is None or v == "":
            return None
        v = v.strip()
        allowed = ["Tunai", "Transfer", "QRIS"]
        if v not in allowed:
            raise ValueError(f'metode_bayar harus salah satu: {allowed}')
        return v

class ServiceOut(BaseModel):
    invoice: str
    nama: str
    wa: str
    device: str
    imei: Optional[str] = None
    keluhan: str
    kelengkapan: List[str] = []
    biaya: int
    teknisi: Optional[str] = None
    penerima: Optional[str] = None
    hasil: Optional[str] = None
    keterangan: Optional[str] = None
    status: str
    date: Optional[datetime.date] = None
    estimasi_selesai: Optional[datetime.date] = None
    deadline_type: Optional[str] = None
    deadline: Optional[datetime.date] = None
    sisa_hari: Optional[int] = None  # computed: deadline - today
    is_overdue: Optional[bool] = None
    garansi_hari: Optional[int] = None
    garansi_sampai: Optional[datetime.date] = None
    garansi_dari: Optional[str] = None  # invoice asal jika hasil klaim garansi
    metode_bayar: Optional[str] = None  # Tunai / Transfer / QRIS
    diambil_at: Optional[dt] = None  # kapan jadi Sukses/Sudah Diambil (auto)
    created_at: Optional[dt] = None
    updated_at: Optional[dt] = None

    @field_validator('kelengkapan', mode='before')
    @classmethod
    def parse_kelengkapan(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return [v] if v else []
        if v is None:
            return []
        return v

    class Config:
        from_attributes = True

# ---------- Sparepart (multi-PC sync) ----------
class SparepartBase(BaseModel):
    nama: str = Field(..., min_length=2, max_length=120)
    merk: str = Field(default="LAIN", max_length=20)
    kategori: str = Field(default="Display", max_length=30)
    masuk: int = Field(default=0, ge=0)
    keluar: int = Field(default=0, ge=0)
    stok: Optional[int] = Field(default=None, ge=0)  # jika None auto = masuk - keluar
    harga: int = Field(default=0, ge=0)
    tgl: Optional[datetime.date] = None

    @field_validator('merk')
    @classmethod
    def validate_merk(cls, v):
        if v is None:
            return "LAIN"
        up = v.upper().strip()
        allowed = ["IPHONE","SAMSUNG","XIAOMI","OPPO","VIVO","INFINIX","LAIN"]
        return up if up in allowed else "LAIN"

class SparepartCreate(SparepartBase):
    pass

class SparepartUpdate(BaseModel):
    nama: Optional[str] = None
    merk: Optional[str] = None
    kategori: Optional[str] = None
    masuk: Optional[int] = Field(None, ge=0)
    keluar: Optional[int] = Field(None, ge=0)
    stok: Optional[int] = Field(None, ge=0)
    harga: Optional[int] = Field(None, ge=0)
    tgl: Optional[datetime.date] = None

class SparepartOut(SparepartBase):
    id: int
    stok: int
    tgl: Optional[datetime.date] = None
    created_at: Optional[dt] = None
    updated_at: Optional[dt] = None
    class Config:
        from_attributes = True

# ---------- Alat (multi-PC sync) ----------
class AlatBase(BaseModel):
    nama: str = Field(..., min_length=2, max_length=120)
    kondisi: str = Field(default="Baik", max_length=30)
    peminjam: str = Field(default="-", max_length=100)
    masuk: int = Field(default=0, ge=0)
    keluar: int = Field(default=0, ge=0)
    stok: Optional[int] = Field(default=None, ge=0)
    harga: int = Field(default=0, ge=0)

    @field_validator('kondisi')
    @classmethod
    def validate_kondisi(cls, v):
        if v is None:
            return "Baik"
        allowed = ["Baik","Perlu Kalibrasi","Rusak","Dipinjam"]
        return v if v in allowed else "Baik"

class AlatCreate(AlatBase):
    pass

class AlatUpdate(BaseModel):
    nama: Optional[str] = None
    kondisi: Optional[str] = None
    peminjam: Optional[str] = None
    masuk: Optional[int] = Field(None, ge=0)
    keluar: Optional[int] = Field(None, ge=0)
    stok: Optional[int] = Field(None, ge=0)
    harga: Optional[int] = Field(None, ge=0)

class AlatOut(AlatBase):
    id: int
    stok: int
    created_at: Optional[dt] = None
    updated_at: Optional[dt] = None
    class Config:
        from_attributes = True

# ---------- Stats ----------
class StatsOut(BaseModel):
    total_masuk: int
    dalam_proses: int
    selesai_hari_ini: int
    estimasi_pendapatan: int
    antri: int
    dikerjakan: int
    menunggu_sparepart: int
    selesai: int
    overdue: int = 0
    deadline_hari_ini: int = 0
    harian: int = 0
    mingguan: int = 0

# ---------- BOS SERVICE multi-toko ----------
class StoreMini(BaseModel):
    id: int
    nama: str
    kode: str
    role: str  # peran user di toko ini
    class Config:
        from_attributes = True

class StoreCreate(BaseModel):
    nama: str = Field(..., min_length=2, max_length=120)
    kode: Optional[str] = Field(None, max_length=10, description="Prefix invoice, mis. BGJ. Auto dari nama jika kosong")
    alamat: Optional[str] = Field(None, max_length=255)
    wa: Optional[str] = Field(None, max_length=20)

class StoreOut(BaseModel):
    id: int
    nama: str
    kode: str
    alamat: Optional[str] = None
    wa: Optional[str] = None
    owner_id: Optional[int] = None
    owner_username: Optional[str] = None
    is_active: bool = True
    role_saya: Optional[str] = None  # peran requester di toko ini
    created_at: Optional[dt] = None
    class Config:
        from_attributes = True

class MembershipOut(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    store_id: int
    store_nama: Optional[str] = None
    role: str
    is_active: bool = True
    created_at: Optional[dt] = None
    class Config:
        from_attributes = True

class StoreUpdate(BaseModel):
    nama: Optional[str] = Field(None, min_length=2, max_length=120)
    alamat: Optional[str] = Field(None, max_length=255)
    wa: Optional[str] = Field(None, max_length=20)

    @field_validator('wa')
    @classmethod
    def validate_wa(cls, v):
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return None
        cleaned = v.replace(" ", "").replace("-", "").replace("+", "")
        if not cleaned.isdigit():
            raise ValueError('No WA toko harus angka')
        if len(cleaned) < 9:
            raise ValueError('No WA toko minimal 9 digit')
        return v

# ---------- BOS Fase 3: undang tim per toko ----------
class StoreInviteCreate(BaseModel):
    role: str = Field(..., description="admin/kasir/teknisi")
    expires_days: Optional[int] = Field(default=30, description="masa berlaku hari, 0 = tanpa batas")

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        v = (v or "").strip().lower()
        if v not in ["admin", "kasir", "teknisi"]:
            raise ValueError('role harus admin/kasir/teknisi')
        return v

class MembershipUpdate(BaseModel):
    role: Optional[str] = Field(None, description="owner/admin/kasir/teknisi")
    is_active: Optional[bool] = None

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v is None:
            return v
        v = v.strip().lower()
        if v not in ["owner", "admin", "kasir", "teknisi"]:
            raise ValueError('role harus owner/admin/kasir/teknisi')
        return v

# ---------- BOS dev dashboard: audit log ----------
class AuditLogOut(BaseModel):
    id: int
    created_at: Optional[dt] = None
    actor_username: Optional[str] = None
    action: str
    target: Optional[str] = None
    detail: Optional[str] = None
    store_id: Optional[int] = None
    class Config:
        from_attributes = True

# ---------- Pengaturan toko: template WA per status ----------
class WaTemplateIn(BaseModel):
    key: str = Field(..., description="service_masuk/bisa_diambil/gagal/sudah_diambil/klaim_garansi/umum")
    template: str = Field(..., description="kosongkan untuk reset ke default")

class WaTemplateOut(BaseModel):
    key: str
    template: str
    is_custom: bool = False
    updated_at: Optional[dt] = None
    class Config:
        from_attributes = True

class InviteCreate(BaseModel):
    kind: str = Field(..., description="owner | member")
    store_id: Optional[int] = Field(None, description="wajib jika kind=member")
    role: Optional[str] = Field(None, description="admin/kasir/teknisi, wajib jika kind=member")
    expires_days: Optional[int] = Field(default=30, description="masa berlaku hari, 0 = tanpa batas")

    @field_validator('kind')
    @classmethod
    def validate_kind(cls, v):
        v = v.lower().strip()
        if v not in ["owner", "member"]:
            raise ValueError('kind harus owner atau member')
        return v

class InviteOut(BaseModel):
    id: int
    code: str
    kind: str
    store_id: Optional[int] = None
    store_nama: Optional[str] = None
    role: Optional[str] = None
    is_used: bool = False
    used_by_username: Optional[str] = None
    expires_at: Optional[dt] = None
    created_at: Optional[dt] = None
    class Config:
        from_attributes = True

class InviteValidateOut(BaseModel):
    valid: bool
    reason: Optional[str] = None
    kind: Optional[str] = None
    role: Optional[str] = None
    store_id: Optional[int] = None
    store_nama: Optional[str] = None

class RegisterOwnerIn(BaseModel):
    invite_code: str = Field(..., min_length=8, max_length=20)
    nama: str = Field(..., min_length=2, max_length=120)
    username: str = Field(..., min_length=3, max_length=50)
    wa: str = Field(..., min_length=9, max_length=20)
    password: str = Field(..., min_length=6)
    nama_toko: Optional[str] = Field(None, max_length=120, description="wajib jika invite kind=owner")

class RegisterOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    nama: Optional[str] = None
    store_id: Optional[int] = None
    store_nama: Optional[str] = None
    store_kode: Optional[str] = None
    created_at: Optional[dt] = None
    class Config:
        from_attributes = True
