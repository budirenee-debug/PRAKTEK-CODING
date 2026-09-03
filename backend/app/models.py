"""
Models - SQLAlchemy ORM
B_gadget POS Service HP
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, func, Boolean
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Technician(Base):
    __tablename__ = "technicians"

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(100), unique=True, nullable=False, index=True)
    foto = Column(String(255), nullable=True)  # URL avatar
    is_active = Column(Integer, default=1)  # 1 aktif, 0 nonaktif
    created_at = Column(DateTime, default=func.now())

    services = relationship("Service", back_populates="technician_obj")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(120), nullable=False, index=True)
    wa = Column(String(20), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    services = relationship("Service", back_populates="customer")


class Service(Base):
    __tablename__ = "services"

    # Invoice sebagai PK string: INV-2026-XXXX
    invoice = Column(String(20), primary_key=True, index=True)
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

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    customer = relationship("Customer", back_populates="services")
    technician_obj = relationship("Technician", back_populates="services")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)  # superadmin
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="superadmin")  # superadmin, admin, kasir
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime, nullable=True)
