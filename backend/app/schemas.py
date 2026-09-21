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
