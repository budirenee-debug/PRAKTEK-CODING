"""Penjualan kasir: barang (potong stok otomatis) + jasa langsung. Struk simple."""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from ..database import get_db
from .. import models, crud
from ..audit import log_action
from ..store_ctx import resolve_store, store_role, default_store
from .auth import get_current_user

router = APIRouter(prefix="/sales", tags=["Sales"])

METODE = ["Tunai", "Transfer", "QRIS"]
KASIR_ROLES = ["superadmin", "owner", "admin", "kasir"]


def _ctx(db, current, store_id):
    """Kasir boleh catat jual (dia kasirnya). Teknisi ditolak."""
    if not current:
        raise HTTPException(status_code=401, detail="Belum login")
    store = resolve_store(db, current, store_id)
    if store is None:
        store = default_store(db)
    if store is None:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    role = store_role(db, current, store)
    if role not in KASIR_ROLES:
        raise HTTPException(status_code=403, detail="Hanya owner/admin/kasir yang boleh kasir")
    return store, role


def _parse_tgl(v):
    if not v:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="tanggal harus format YYYY-MM-DD")


def _sale_row(db, s: models.Sale):
    items = db.query(models.SaleItem).filter(models.SaleItem.sale_id == s.id).all()
    return {"id": s.id, "kode": s.kode, "tanggal": s.tanggal,
            "pelanggan": s.pelanggan, "metode": s.metode,
            "total": s.total, "profit": s.profit,
            "dibuat_oleh": s.dibuat_oleh, "created_at": s.created_at,
            "items": [{"id": i.id, "tipe": i.tipe, "sparepart_id": i.sparepart_id,
                       "nama": i.nama_snapshot, "qty": i.qty,
                       "harga_jual": i.harga_jual, "harga_beli": i.harga_beli,
                       "profit": i.profit} for i in items]}


@router.get("")
def list_sales(store_id: Optional[int] = Query(None), since: Optional[str] = Query(None),
               limit: int = Query(100, le=300),
               db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx(db, current, store_id)
    q = db.query(models.Sale).filter(models.Sale.store_id == store.id)
    if since:
        try:
            d0 = datetime.datetime.strptime(since[:10], "%Y-%m-%d").date()
            q = q.filter(models.Sale.tanggal >= d0)
        except Exception:
            raise HTTPException(status_code=400, detail="since harus YYYY-MM-DD")
    rows = q.order_by(models.Sale.id.desc()).limit(limit).all()
    return [_sale_row(db, s) for s in rows]


@router.get("/ringkasan")
def ringkasan_sales(store_id: Optional[int] = Query(None),
                    db: Session = Depends(get_db), current=Depends(get_current_user)):
    store, _ = _ctx(db, current, store_id)
    rows = db.query(models.Sale).filter(models.Sale.store_id == store.id).all()
    today = datetime.date.today()
    iso, ym = today.isoformat(), today.strftime("%Y-%m")
    hari = [s for s in rows if str(s.tanggal or "") == iso]
    bln = [s for s in rows if str(s.tanggal or "")[:7] == ym]
    per_metode = {}
    for s in rows:
        m = s.metode or "Tunai"
        per_metode[m] = per_metode.get(m, 0) + int(s.total or 0)
    items = db.query(models.SaleItem).filter(models.SaleItem.store_id == store.id).all()
    agg = {}
    for i in items:
        k = i.nama_snapshot or "-"
        a = agg.get(k, {"nama": k, "qty": 0, "omzet": 0, "profit": 0})
        a["qty"] += int(i.qty or 0)
        a["omzet"] += int(i.harga_jual or 0) * int(i.qty or 0)
        a["profit"] += int(i.profit or 0)
        agg[k] = a
    top = sorted(agg.values(), key=lambda a: a["qty"], reverse=True)[:10]
    return {
        "total": len(rows),
        "omzet": sum(int(s.total or 0) for s in rows),
        "profit": sum(int(s.profit or 0) for s in rows),
        "hari_ini": len(hari),
        "omzet_hari_ini": sum(int(s.total or 0) for s in hari),
        "profit_hari_ini": sum(int(s.profit or 0) for s in hari),
        "bulan_ini": len(bln),
        "omzet_bulan_ini": sum(int(s.total or 0) for s in bln),
        "profit_bulan_ini": sum(int(s.profit or 0) for s in bln),
        "per_metode": per_metode,
        "terlaris": top,
    }


@router.post("", status_code=201)
def create_sale(payload: dict = Body(...), store_id: Optional[int] = Query(None),
                db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Catat struk. items: [{tipe:'barang', sparepart_id, qty} | {tipe:'jasa', nama, harga, qty}].
    Harga barang ikut master (anti markup kasir). Stok kurang → 400."""
    store, _ = _ctx(db, current, store_id)
    raw = payload.get("items") or []
    if not raw or not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="items wajib diisi (min 1)")
    if len(raw) > 50:
        raise HTTPException(status_code=400, detail="maks 50 item per struk")
    metode = (payload.get("metode") or "Tunai").strip()
    if metode not in METODE:
        raise HTTPException(status_code=400, detail="metode harus Tunai/Transfer/QRIS")
    tanggal = _parse_tgl(payload.get("tanggal"))
    pelanggan = (payload.get("pelanggan") or "").strip() or None

    built = []
    for it in raw:
        tipe = (it.get("tipe") or "barang").strip().lower()
        qty = int(it.get("qty") or 1)
        if qty <= 0 or qty > 999:
            raise HTTPException(status_code=400, detail="qty harus 1-999")
        if tipe == "jasa":
            nama = (it.get("nama") or "").strip()
            harga = int(it.get("harga") or 0)
            if not nama:
                raise HTTPException(status_code=400, detail="item jasa wajib ada nama")
            if harga <= 0:
                raise HTTPException(status_code=400, detail="item jasa wajib ada harga > 0")
            built.append({"tipe": "jasa", "sp": None, "nama": nama, "qty": qty,
                          "jual": harga, "beli": 0, "profit": harga * qty})
        elif tipe == "barang":
            if not it.get("sparepart_id"):
                raise HTTPException(status_code=400, detail="item barang wajib sparepart_id")
            sp = db.query(models.Sparepart).filter(
                models.Sparepart.id == int(it["sparepart_id"]),
                models.Sparepart.store_id == store.id).first()
            if not sp:
                raise HTTPException(status_code=404, detail="barang tidak ditemukan di toko ini")
            if int(sp.stok or 0) < qty:
                raise HTTPException(status_code=400, detail=f"Stok kurang: {sp.nama} (sisa {sp.stok})")
            jual, beli = int(sp.harga or 0), int(sp.harga_beli or 0)
            built.append({"tipe": "barang", "sp": sp, "nama": sp.nama, "qty": qty,
                          "jual": jual, "beli": beli, "profit": (jual - beli) * qty})
        else:
            raise HTTPException(status_code=400, detail="tipe harus barang/jasa")

    total = sum(b["jual"] * b["qty"] for b in built)
    profit = sum(b["profit"] for b in built)
    if total <= 0:
        raise HTTPException(status_code=400, detail="total struk harus > 0")
    s = models.Sale(store_id=store.id, tanggal=tanggal, pelanggan=pelanggan,
                    metode=metode, total=total, profit=profit,
                    dibuat_oleh=getattr(current, "username", None))
    db.add(s)
    db.commit()
    db.refresh(s)
    s.kode = f"JL-{tanggal.strftime('%Y%m')}-{s.id:04d}"
    for b in built:
        if b["tipe"] == "barang":
            stok_lama = int(b["sp"].stok or 0)
            b["sp"].stok = stok_lama - b["qty"]
            b["sp"].keluar = int(b["sp"].keluar or 0) + b["qty"]
            crud.catat_mutasi(db, b["sp"], "jual", -b["qty"], stok_lama, b["sp"].stok,
                              ref=s.kode, actor=current)
        db.add(models.SaleItem(sale_id=s.id, store_id=store.id, tipe=b["tipe"],
                               sparepart_id=b["sp"].id if b["sp"] else None,
                               nama_snapshot=b["nama"], qty=b["qty"],
                               harga_jual=b["jual"], harga_beli=b["beli"], profit=b["profit"]))
    db.commit()
    db.refresh(s)
    log_action(db, "sale.create", target=s.kode,
               detail=f"{len(built)} item total={total} profit={profit} metode={metode}",
               actor=current, store_id=store.id)
    return _sale_row(db, s)


@router.delete("/{sale_id}")
def void_sale(sale_id: int, store_id: Optional[int] = Query(None),
              db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Void struk salah input: stok barang balik, struk dihapus."""
    store, _ = _ctx(db, current, store_id)
    s = db.query(models.Sale).filter(models.Sale.id == sale_id,
                                     models.Sale.store_id == store.id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Struk tidak ditemukan di toko ini")
    items = db.query(models.SaleItem).filter(models.SaleItem.sale_id == s.id).all()
    for i in items:
        if i.tipe == "barang" and i.sparepart_id:
            # scope toko: jangan hanya filter id (part bisa pindah toko /_no validasi)
            sp = db.query(models.Sparepart).filter(
                models.Sparepart.id == i.sparepart_id,
                models.Sparepart.store_id == s.store_id).first()
            if sp:
                stok_lama = int(sp.stok or 0)
                sp.stok = stok_lama + int(i.qty or 0)
                sp.keluar = max(0, int(sp.keluar or 0) - int(i.qty or 0))
                crud.catat_mutasi(db, sp, "batal", int(i.qty or 0), stok_lama, sp.stok,
                                  ref=f"void {s.kode or s.id}", actor=current)
        db.delete(i)
    info = f"{s.kode} total={s.total} profit={s.profit}"
    db.flush()  # pastikan item terhapus dulu (FK sale_items.sale_id)
    db.delete(s)
    db.commit()
    log_action(db, "sale.void", target=s.kode or f"JL-{sale_id}",
               detail=info, actor=current, store_id=store.id)
    return {"ok": True, "id": sale_id}
