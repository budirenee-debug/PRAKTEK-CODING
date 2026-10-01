from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from ..database import get_db
from .. import schemas, crud
from ..store_ctx import (resolve_store, ensure_in_store, default_store, store_role,
                         teknisi_scope_names, is_own_or_free)
from .auth import get_current_user, require_superadmin
from ..audit import log_action


def _teknisi_scope(db, current, store):
    """Set nama milik teknisi jika requester role teknisi, else None (bebas)."""
    if store_role(db, current, store) == "teknisi":
        return teknisi_scope_names(current)
    return None


def _toko_writer(db, current, store):
    """Tulis stok: owner/admin/kasir (terima barang) + superadmin. Teknisi via Pakai saja."""
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin", "kasir"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin/kasir yang boleh ubah stok — teknisi pakai via Proses Service")
    return role


def _toko_owner(db, current, store):
    """Hapus item: owner/admin/superadmin (scope toko sendiri)."""
    role = store_role(db, current, store)
    if role not in ["superadmin", "owner", "admin"]:
        raise HTTPException(status_code=403, detail="Hanya owner/admin yang boleh hapus item")
    return role

router = APIRouter(prefix="/inventory", tags=["Inventory"])

def _sid(store) -> Optional[int]:
    return store.id if store is not None else None

def _need_store(db: Session, store):
    if store is None:
        store = default_store(db)
    return store

@router.get("/spareparts", response_model=List[schemas.SparepartOut])
def list_spareparts(
    search: Optional[str] = None,
    merk: Optional[str] = None,
    kategori: Optional[str] = None,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    return crud.get_spareparts(db, search=search, merk=merk, kategori=kategori, store_id=_sid(store))

@router.post("/spareparts", response_model=schemas.SparepartOut, status_code=201)
def create_sparepart(
    payload: schemas.SparepartCreate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = _need_store(db, resolve_store(db, current, store_id))
    _toko_writer(db, current, store)
    # cek duplikat nama di toko yang sama
    sq = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.nama.ilike(payload.nama.strip()))
    if store is not None:
        sq = sq.filter(crud.models.Sparepart.store_id == store.id)
    existing = sq.first()
    if existing:
        raise HTTPException(status_code=400, detail="Nama part sudah ada di toko ini — pakai Edit")
    sp = crud.create_sparepart(db, payload, store_id=store.id if store else None)
    log_action(db, "stok.create", target=sp.nama,
               detail=f"Masuk {sp.masuk} • stok {sp.stok} • beli {sp.harga_beli} • jual {sp.harga} • {sp.merk}/{sp.kategori}",
               actor=current, store_id=store.id if store else None)
    return sp

@router.put("/spareparts/{sp_id}", response_model=schemas.SparepartOut)
def update_sparepart(
    sp_id: int,
    payload: schemas.SparepartUpdate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    _toko_writer(db, current, store)
    # cek duplikat nama kecuali diri sendiri (di toko yang sama)
    if payload.nama:
        dq = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.nama.ilike(payload.nama.strip()), crud.models.Sparepart.id != sp_id)
        if store is not None:
            dq = dq.filter(crud.models.Sparepart.store_id == store.id)
        dup = dq.first()
        if dup:
            raise HTTPException(status_code=400, detail="Nama sudah dipakai item lain")
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    lama = {k: getattr(sp, k, None) for k in ("nama", "stok", "harga", "harga_beli", "keluar")}
    sp = crud.update_sparepart(db, sp_id, payload, actor=current)
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ubah = []
    for k, v in lama.items():
        if getattr(sp, k, None) != v:
            ubah.append(f"{k} {v} -> {getattr(sp, k, None)}")
    if ubah:
        log_action(db, "stok.update", target=sp.nama, detail="; ".join(ubah)[:400],
                   actor=current, store_id=_sid(store))
    return sp

@router.delete("/spareparts/{sp_id}")
def delete_sparepart(
    sp_id: int,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    _toko_owner(db, current, store)
    ok = crud.delete_sparepart(db, sp_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    log_action(db, "stok.hapus", target=sp.nama,
               detail=f"Hapus {sp.merk}/{sp.kategori} • stok {sp.stok} • harga {sp.harga}",
               actor=current, store_id=_sid(store))
    return {"message": f"{sp_id} dihapus"}

@router.post("/spareparts/{sp_id}/pakai", response_model=schemas.PakaiPartOut)
def pakai_sparepart(
    sp_id: int,
    invoice: str = Query(..., description="Invoice service yang memakai part (wajib)"),
    qty: int = Query(1, ge=1, description="Jumlah pakai"),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """Pakai part untuk sebuah service: potong stok + catat di service_parts (snapshot harga).

    Invoice WAJIB — tanpa ini stok berkurang tanpa jejak. Part terkunci begitu service
    masuk status terminal (Sudah Diambil/Sukses/Failed/Garansi/Dibatalkan)."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    svc = db.query(crud.models.Service).filter(crud.models.Service.invoice == invoice).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    ensure_in_store(svc, store, "Service")
    if (svc.status or "") not in schemas.BISA_PAKAI_PART:
        raise HTTPException(
            status_code=400,
            detail=f"Part terkunci — service sudah berstatus {svc.status}. Harga sudah fix, tidak bisa tambah part.",
        )
    # teknisi hanya boleh pakai part di service miliknya / belum bertuan
    scope = _teknisi_scope(db, current, store)
    if scope is not None and not is_own_or_free(svc.teknisi, scope):
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")
    sp, part, err = crud.pakai_part(db, sp, svc, qty, actor=current)
    if err:
        raise HTTPException(status_code=400, detail=err)
    log_action(db, "stok.pakai", target=sp.nama,
               detail=f"{sp.merk}/{sp.kategori} x{qty} untuk {invoice} • sisa stok {sp.stok} • modal {part.modal_asli_snapshot}",
               actor=current, store_id=_sid(store))
    return schemas.PakaiPartOut(
        sparepart=schemas.SparepartOut.model_validate(sp),
        part=schemas.ServicePartOut(
            id=part.id, store_id=part.store_id, invoice=part.invoice, sparepart_id=part.sparepart_id,
            nama_snapshot=part.nama_snapshot, merk=sp.merk,
            harga_up_snapshot=part.harga_up_snapshot, modal_asli_snapshot=part.modal_asli_snapshot,
            qty=part.qty, teknisi=svc.teknisi, created_at=part.created_at,
        ),
    )


# ----- Part terpakai per service (tabel service_parts) -----
@router.get("/service-parts", response_model=List[schemas.ServicePartOut])
def list_service_parts(
    invoice: Optional[str] = Query(None, description="Filter 1 invoice; kosong = semua"),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """Semua pemakaian part di toko aktif — sumber kebenaran laporan 'Sparepart Dipakai'."""
    store = resolve_store(db, current, store_id)
    return crud.list_service_parts(db, store_id=_sid(store), invoice=invoice, teknisi_scope=_teknisi_scope(db, current, store))


@router.delete("/service-parts/{part_id}")
def batal_service_part(
    part_id: int,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """Batalkan pemakaian part: hapus catatan + kembalikan stok. Terkunci jika service sudah terminal."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    part = db.query(crud.models.ServicePart).filter(crud.models.ServicePart.id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="Catatan part tidak ditemukan")
    ensure_in_store(part, store, "Part")
    svc = db.query(crud.models.Service).filter(crud.models.Service.invoice == part.invoice).first()
    if svc and (svc.status or "") not in schemas.BISA_PAKAI_PART:
        raise HTTPException(
            status_code=400,
            detail=f"Tidak bisa dibatalkan — service sudah berstatus {svc.status}. Hubungi owner/admin.",
        )
    nama, qty, inv = part.nama_snapshot, part.qty, part.invoice
    crud.kembalikan_part(db, part, actor=current)
    log_action(db, "stok.pakai.batal", target=nama,
               detail=f"kembalikan {qty} dari {inv} • stok naik lagi",
               actor=current, store_id=_sid(store))
    return {"message": f"{nama} x{qty} dibatalkan — stok dikembalikan"}


# ----- Buku mutasi stok (jejak perubahan stok) -----
@router.get("/stock-moves", response_model=List[schemas.StockMoveOut])
def list_stock_moves(
    sparepart_id: Optional[int] = Query(None),
    tipe: Optional[str] = Query(None),
    limit: int = Query(80, ge=1, le=300),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """Mutasi stok terbaru. `sparepart_id` = riwayat 1 part (modal Riwayat di tabel Stok)."""
    store = resolve_store(db, current, store_id)
    return crud.get_stock_moves(db, store_id=_sid(store), sparepart_id=sparepart_id, tipe=tipe, limit=limit)


@router.get("/spareparts/{sp_id}/riwayat", response_model=List[schemas.StockMoveOut])
def riwayat_sparepart(
    sp_id: int,
    limit: int = Query(50, ge=1, le=300),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """Riwayat mutasi 1 part: terima barang, dipakai, terjual, dibatalkan, penyesuaian."""
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    return crud.get_stock_moves(db, store_id=_sid(store), sparepart_id=sp_id, limit=limit)


@router.post("/spareparts/{sp_id}/masuk", response_model=schemas.SparepartOut)
def terima_barang(
    sp_id: int,
    qty: int = Query(..., ge=1, description="Jumlah barang masuk"),
    ref: Optional[str] = Query(None, description="No. nota supplier / PO (opsional)"),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """Terima barang: `masuk` & `stok` naik. Dipakai daripada mengetik angka di kolom Masuk."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    sp = db.query(crud.models.Sparepart).filter(crud.models.Sparepart.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Sparepart tidak ditemukan")
    ensure_in_store(sp, store, "Sparepart")
    _toko_writer(db, current, store)
    sp, err = crud.masuk_part(db, sp, qty, actor=current, ref=ref)
    if err:
        raise HTTPException(status_code=400, detail=err)
    log_action(db, "stok.masuk", target=sp.nama,
               detail=f"terima {qty} • stok {sp.stok}{(' • ' + ref) if ref else ''}",
               actor=current, store_id=_sid(store))
    return sp

# ----- Alat -----
@router.get("/alats", response_model=List[schemas.AlatOut])
def list_alats(
    search: Optional[str] = None,
    kondisi: Optional[str] = None,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    return crud.get_alats(db, search=search, kondisi=kondisi, store_id=_sid(store))

@router.post("/alats", response_model=schemas.AlatOut, status_code=201)
def create_alat(
    payload: schemas.AlatCreate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = _need_store(db, resolve_store(db, current, store_id))
    _toko_writer(db, current, store)
    aq = db.query(crud.models.Alat).filter(crud.models.Alat.nama.ilike(payload.nama.strip()))
    if store is not None:
        aq = aq.filter(crud.models.Alat.store_id == store.id)
    dup = aq.first()
    if dup:
        raise HTTPException(status_code=400, detail="Nama alat sudah ada di toko ini")
    alat = crud.create_alat(db, payload, store_id=store.id if store else None)
    log_action(db, "alat.create", target=alat.nama,
               detail=f"{alat.kondisi} • peminjam {alat.peminjam} • stok {alat.stok} • harga {alat.harga}",
               actor=current, store_id=_sid(store))
    return alat

@router.put("/alats/{alat_id}", response_model=schemas.AlatOut)
def update_alat(
    alat_id: int,
    payload: schemas.AlatUpdate,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    alat = db.query(crud.models.Alat).filter(crud.models.Alat.id == alat_id).first()
    if not alat:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    ensure_in_store(alat, store, "Alat")
    from ..store_ctx import store_role as _sr
    if _sr(db, current, store) == "teknisi":
        # Teknisi hanya boleh pinjam/kembalikan alat (peminjam) — stok/harga/kondisi milik owner/admin/kasir.
        keys = set(payload.model_dump(exclude_unset=True).keys())
        if keys - {"peminjam"}:
            raise HTTPException(status_code=403, detail="Teknisi hanya boleh ubah peminjam (pinjam/kembali) — stok milik owner/admin/kasir")
        alat.peminjam = payload.peminjam
        if (alat.kondisi or "") == "Baik" and (payload.peminjam or "-") != "-":
            alat.kondisi = "Dipinjam"
        elif (alat.kondisi or "") == "Dipinjam" and (payload.peminjam or "-") == "-":
            alat.kondisi = "Baik"
        db.commit()
        db.refresh(alat)
        log_action(db, "alat.pinjam", target=alat.nama,
                   detail=f"kondisi {alat.kondisi} • peminjam {alat.peminjam}",
                   actor=current, store_id=_sid(store))
        return alat
    _toko_writer(db, current, store)
    if payload.nama:
        dq = db.query(crud.models.Alat).filter(crud.models.Alat.nama.ilike(payload.nama.strip()), crud.models.Alat.id != alat_id)
        if store is not None:
            dq = dq.filter(crud.models.Alat.store_id == store.id)
        dup = dq.first()
        if dup:
            raise HTTPException(status_code=400, detail="Nama sudah dipakai alat lain")
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    alat = crud.update_alat(db, alat_id, payload)
    if not alat:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    log_action(db, "alat.update", target=alat.nama,
               detail=f"kondisi {alat.kondisi} • peminjam {alat.peminjam} • stok {alat.stok} • harga {alat.harga}",
               actor=current, store_id=_sid(store))
    return alat

@router.delete("/alats/{alat_id}")
def delete_alat(
    alat_id: int,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    store = resolve_store(db, current, store_id)
    alat = db.query(crud.models.Alat).filter(crud.models.Alat.id == alat_id).first()
    if not alat:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    ensure_in_store(alat, store, "Alat")
    _toko_owner(db, current, store)
    ok = crud.delete_alat(db, alat_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    log_action(db, "alat.hapus", target=alat.nama,
               detail=f"kondisi {alat.kondisi} • peminjam {alat.peminjam} • stok {alat.stok}",
               actor=current, store_id=_sid(store))
    return {"message": f"{alat_id} dihapus"}
