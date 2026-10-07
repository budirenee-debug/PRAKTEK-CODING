#!/usr/bin/env python3
"""Backfill modal sparepart lama -> Expense B1 + ledger persediaan.

Latar: input master Stok (nama+harga) tidak menyentuh Keuangan, sehingga modal
yang sudah keluar tidak tercatat. Script ini membikinkan 1 Expense B1 + 1 baris
ledger per sparepart (nominal = harga_beli x masuk).

Idempotent: item yang sudah punya expense berketerangan marker `backfill-sp:{id}`
di-skip, aman diulang.

Default TANPA gerak kas (--tanpa-kas): stok lama = saldo awal persediaan, uangnya
keluar sebelum sistem berjalan, jadi kas tidak dikurangi (pengaruh_kas=False)
tapi nilai persediaan tercatat (masuk_laba=False). Pakai --dengan-kas jika uangnya
memang baru keluar dari laci sekarang.

Contoh:
  python tools/backfill_modal_sparepart.py --dry-run
  python tools/backfill_modal_sparepart.py --apply --metode Tunai
  python tools/backfill_modal_sparepart.py --apply --dengan-kas --metode Transfer
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.database import SessionLocal  # noqa: E402
from app import models, ledger_meta as lm  # noqa: E402
from app.routers.finance import _ledger_add  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Backfill modal sparepart -> B1 + persediaan")
    ap.add_argument("--apply", dest="apply", action="store_true", help="tulis DB (default: dry-run)")
    ap.add_argument("--dry-run", dest="apply", action="store_false", help="cetak rencana saja (default)")
    ap.add_argument("--metode", default="Tunai", choices=["Tunai", "Transfer", "QRIS"])
    ap.add_argument("--tanpa-kas", dest="tanpa_kas", action="store_true", default=True,
                    help="persediaan tanpa gerak kas / saldo awal (default)")
    ap.add_argument("--dengan-kas", dest="tanpa_kas", action="store_false",
                    help="kas ikut berkurang (uang baru keluar sekarang)")
    ap.add_argument("--oleh", default="backfill")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        items = db.query(models.Sparepart).filter(
            models.Sparepart.harga_beli > 0, models.Sparepart.masuk > 0).all()
        print(f" kandidat: {len(items)} item (harga_beli>0 & masuk>0)")
        total, skip, buat = 0, 0, []
        for sp in items:
            marker = f"backfill-sp:{sp.id}"
            ada = db.query(models.Expense).filter(
                models.Expense.keterangan == marker).first()
            if ada:
                skip += 1
                continue
            nominal = int(sp.harga_beli) * int(sp.masuk)
            total += nominal
            buat.append((sp, nominal, marker))
        print(f" sudah ada: {skip} item | akan dibuat: {len(buat)} item | total Rp{total:,}".replace(",", "."))
        if not buat:
            print("tidak ada yang perlu dibuat. SELESAI.")
            return
        if not args.apply:
            print("DRY-RUN (tambah --apply untuk tulis):")
            for sp, nominal, _ in buat[:15]:
                print(f"  #{sp.id} {sp.nama} x{sp.masuk} @ {sp.harga_beli} = Rp{nominal:,}".replace(",", "."))
            if len(buat) > 15:
                print(f"  ... +{len(buat) - 15} lagi")
            return
        media = lm.METODE_KE_MEDIA.get(args.metode, "kas_utama")
        n = 0
        for sp, nominal, marker in buat:
            tgl = sp.tgl or datetime.date.today()
            exp = models.Expense(
                store_id=sp.store_id, tanggal=tgl, kategori="B1",
                keperluan=f"Belanja {sp.nama} x{sp.masuk}", nominal=nominal,
                metode=args.metode, keterangan=marker, dibuat_oleh=args.oleh)
            db.add(exp)
            db.flush()
            _ledger_add(db, sp.store_id, tgl, "keluar", "B1",
                        f"Belanja Sparepart: {sp.nama} x{sp.masuk}", nominal,
                        "stok" if args.tanpa_kas else media,
                        ref_type="expense", ref_id=exp.id, oleh=args.oleh,
                        masuk_laba=False, pengaruh_kas=not args.tanpa_kas)
            n += 1
        db.commit()
        print(f"OK: {n} expense B1 + {n} ledger persediaan "
              f"({'tanpa gerak kas' if args.tanpa_kas else 'kas ' + media + ' berkurang'}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
