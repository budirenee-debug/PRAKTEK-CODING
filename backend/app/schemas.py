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
    status: Optional[str] = Field(default="Antri")
    estimasi_selesai: Optional[datetime.date] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        allowed = ["Antri", "Dikerjakan", "Menunggu Sparepart", "Selesai", "Dibatalkan", "Bisa Diambil", "Sudah Diambil", "Service Failed", "Garansi"]
        if v not in allowed:
            raise ValueError(f'Status harus salah satu: {allowed}')
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
    status: Optional[str] = None
    estimasi_selesai: Optional[datetime.date] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = ["Antri", "Dikerjakan", "Menunggu Sparepart", "Selesai", "Dibatalkan", "Bisa Diambil", "Sudah Diambil", "Service Failed", "Garansi"]
        if v not in allowed:
            raise ValueError(f'Status harus salah satu: {allowed}')
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
    status: str
    date: Optional[datetime.date] = None
    estimasi_selesai: Optional[datetime.date] = None
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
