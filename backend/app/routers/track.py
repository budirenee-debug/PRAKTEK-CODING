"""Tracking publik untuk pelanggan: lacak via invoice atau IMEI, tanpa login.

Privasi: hanya field aman yang dikembalikan (tanpa no WA full, tanpa biaya,
tanpa nama teknisi). Nama pelanggan disamarkan.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from pydantic import BaseModel
from typing import Optional, List
import datetime

from ..database import get_db
from .. import models

router = APIRouter(prefix="/track", tags=["Track"])


class TrackStep(BaseModel):
    key: str
    label: str
    state: str  # done | current | todo


class TrackOut(BaseModel):
    invoice: str
    toko: Optional[str] = None
    device: str
    keluhan: str
    status: str
    status_label: str
    nama_masked: str
    tgl_masuk: Optional[datetime.date] = None
    estimasi_selesai: Optional[datetime.date] = None
    garansi_sampai: Optional[datetime.date] = None
    updated_at: Optional[datetime.datetime] = None
    steps: List[TrackStep] = []


STATUS_LABEL = {
    "Antri": "Antrean — HP sudah diterima toko",
    "Menunggu Konfirmasi": "Menunggu konfirmasi pelanggan",
    "Dikerjakan": "Sedang dikerjakan teknisi",
    "Menunggu Sparepart": "Menunggu sparepart datang",
    "Selesai": "Selesai — bisa diambil",
    "Service Sukses": "Selesai — bisa diambil",
    "Bisa Diambil": "Bisa diambil di toko",
    "Sudah Diambil": "Sudah diambil pelanggan",
    "Service Failed": "Gagal diperbaiki",
    "Dibatalkan": "Dibatalkan",
    "Garansi": "Dalam masa garansi",
}

FAILED = {"Service Failed", "Dibatalkan"}
DONE = {"Service Sukses", "Selesai", "Bisa Diambil", "Sudah Diambil"}
WORKING = {"Menunggu Konfirmasi", "Dikerjakan", "Menunggu Sparepart", "Garansi"}


def _mask_nama(nama: str) -> str:
    nama = (nama or "").strip()
    if not nama:
        return "***"
    parts = nama.split()
    first = parts[0]
    if len(parts) == 1:
        return first[0] + "***" if len(first) > 1 else "***"
    return f"{first} {parts[1][0]}***"


def _steps(status: str) -> List[TrackStep]:
    if status in FAILED:
        return [
            TrackStep(key="terima", label="Diterima", state="done"),
            TrackStep(key="kerja", label="Dikerjakan", state="done"),
            TrackStep(key="selesai", label="Gagal / Batal", state="current"),
        ]
    if status in DONE:
        cur = "todo" if status == "Sudah Diambil" else "current"
        # Sudah Diambil = semua done
        states = ["done", "done", "done"] if status == "Sudah Diambil" else ["done", "done", cur]
        return [
            TrackStep(key="terima", label="Diterima", state=states[0]),
            TrackStep(key="kerja", label="Dikerjakan", state=states[1]),
            TrackStep(key="selesai", label="Bisa Diambil", state=states[2]),
        ]
    if status in WORKING:
        return [
            TrackStep(key="terima", label="Diterima", state="done"),
            TrackStep(key="kerja", label="Dikerjakan", state="current"),
            TrackStep(key="selesai", label="Bisa Diambil", state="todo"),
        ]
    # Antri & default
    return [
        TrackStep(key="terima", label="Diterima", state="current"),
        TrackStep(key="kerja", label="Dikerjakan", state="todo"),
        TrackStep(key="selesai", label="Bisa Diambil", state="todo"),
    ]


def _to_out(svc: models.Service, toko_nama: Optional[str]) -> TrackOut:
    # HP yang sudah lewat pengambilan (ada tgl/pengambil) = "Sudah Diambil",
    # walau status tersimpan "Service Sukses" (dipakai juga untuk pendapatan).
    status = svc.status
    if status in ("Service Sukses", "Selesai") and (svc.diambil_at or svc.diambil_oleh):
        status = "Sudah Diambil"
    return TrackOut(
        invoice=svc.invoice,
        toko=toko_nama,
        device=svc.device,
        keluhan=svc.keluhan,
        status=status,
        status_label=STATUS_LABEL.get(status, status),
        nama_masked=_mask_nama(svc.nama),
        tgl_masuk=svc.date,
        estimasi_selesai=svc.estimasi_selesai,
        garansi_sampai=svc.garansi_sampai,
        updated_at=svc.updated_at,
        steps=_steps(status),
    )


@router.get("", response_model=List[TrackOut])
def track(q: str, db: Session = Depends(get_db)):
    """Cari service by invoice atau IMEI — boleh sebagian (case-insensitive).

    Contoh: GET /api/track?q=REN-2026-0001 , ?q=356938035643809 , atau ?q=8675
    (4 digit terakhir IMEI). Exact match diutamakan, lalu terbaru.
    Publik — tanpa token. Return max 5.
    """
    key = (q or "").strip()
    if len(key) < 3:
        raise HTTPException(status_code=400, detail="Kode nota / IMEI minimal 3 karakter")
    like = f"%{key}%"
    cands = (
        db.query(models.Service)
        .filter(or_(models.Service.invoice.ilike(like), models.Service.imei.ilike(like)))
        .order_by(desc(models.Service.updated_at))
        .limit(20)
        .all()
    )
    if not cands:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan — cek lagi kode nota / IMEI di struk")
    low = key.lower()

    def rank(svc: models.Service):
        if (svc.invoice or "").lower() == low:
            return 0
        if (svc.imei or "") == key:
            return 1
        if (svc.invoice or "").lower().startswith(low):
            return 2
        return 3

    rows = sorted(cands, key=lambda s: (rank(s),))[:5]
    out: List[TrackOut] = []
    for svc in rows:
        toko_nama = None
        if svc.store_id:
            toko = db.query(models.Store).filter(models.Store.id == svc.store_id).first()
            if toko:
                toko_nama = toko.nama
        out.append(_to_out(svc, toko_nama))
    return out
