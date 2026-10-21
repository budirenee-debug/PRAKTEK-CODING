"""Dry-run migrasi UNIQUE per toko pada SALINAN DB produksi.

Jalankan: python tools/dryrun_migrasi_prodb.py <path_salinan.db>
Yang dicek: tidak ada data hilang, constraint komposit terpasang, app tetap bisa import.
"""
import os, sqlite3, sys

DB = sys.argv[1] if len(sys.argv) > 1 else "b_gadget.dryrun.db"
DB = os.path.abspath(DB)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

def dump(path):
    con = sqlite3.connect(path)
    c = con.cursor()
    out = {}
    for t in ('customers', 'technicians', 'services', 'ledger_entries', 'expenses',
              'spareparts', 'users', 'stores', 'memberships', 'audit_logs',
              'stock_moves', 'commission_ledgers', 'cash_closes', 'service_parts'):
        try:
            out[t] = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        except Exception:
            out[t] = 'n/a'
    # checksum isi tabel kritikal (urutan tetap)
    for t in ('customers', 'technicians'):
        try:
            cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % t)]
            key = 'wa' if t == 'customers' else 'nama'
            rows = c.execute('SELECT id, store_id, %s FROM %s ORDER BY id' % (key, t)).fetchall()
            out['__sum_' + t] = (''.join((r[2] or '') for r in rows), len(rows))
        except Exception:
            out['__sum_' + t] = 'n/a'
    con.close()
    return out

before = dump(DB)
print("SEBELUM:", {k: before[k] for k in sorted(before) if not k.startswith('__')})

os.environ['DATABASE_URL'] = 'sqlite:///' + DB
import app.main  # noqa: F401  -> migrasi jalan
from app.database import engine
engine.dispose()

after = dump(DB)
print("SESUDAH:", {k: after[k] for k in sorted(after) if not k.startswith('__')})

ok = True
def chk(label, cond, extra=''):
    global ok
    print(("  LULUS  " if cond else "  GAGAL  ") + label + ((" | " + str(extra)) if extra else ''))
    ok = ok and bool(cond)

print()
print("=== CEK DATA ===")
for t in before:
    if t.startswith('__'):
        continue
    chk("%s jumlah baris tetap" % t, before[t] == after[t], "%s -> %s" % (before[t], after[t]))
for t in ('customers', 'technicians'):
    chk("%s isi/id tetap" % t, before['__sum_' + t] == after['__sum_' + t],
        "%s -> %s" % (before['__sum_' + t], after['__sum_' + t]))

print()
print("=== CEK CONSTRAINT ===")
con = sqlite3.connect(DB)
c = con.cursor()
sqls = {r[0]: r[1] for r in c.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")}
idxs = {r[0]: r[1] for r in c.execute("SELECT name, sql FROM sqlite_master WHERE type='index'")}
chk("customers_new hilang", 'customers_new' not in sqls)
chk("customers punya index partial WA", 'uq_customer_wa_store' in idxs, idxs.get('uq_customer_wa_store'))
chk("customers punya index partial IMEI", 'uq_customer_imei_store' in idxs, idxs.get('uq_customer_imei_store'))
chk("index partial WA punya WHERE (WA kosong bebas)", 'WHERE' in (idxs.get('uq_customer_wa_store') or '').upper())
chk("index partial IMEI punya WHERE (IMEI kosong bebas)", 'WHERE' in (idxs.get('uq_customer_imei_store') or '').upper())
chk("constraint tabel UNIQUE(wa,store_id) dicabut", 'UNIQUE (WA, STORE_ID)' not in ' '.join((sqls.get('customers') or '').upper().split()))
chk("kolom imei ada di customers", 'imei' in [r[1] for r in c.execute('PRAGMA table_info(customers)')])
chk("technicians UNIQUE komposit", 'uq_technician_nama_store' in (sqls.get('technicians') or ''))
chk("ix_customers_wa bukan UNIQUE global", 'UNIQUE' not in (idxs.get('ix_customers_wa') or ''), idxs.get('ix_customers_wa'))
chk("ix_technicians_nama bukan UNIQUE global", 'UNIQUE' not in (idxs.get('ix_technicians_nama') or ''), idxs.get('ix_technicians_nama'))
chk("ix_customers_id ada lagi", 'ix_customers_id' in idxs)
chk("ix_technicians_id ada lagi", 'ix_technicians_id' in idxs)

# sanity: WA yang SAMA harus boleh di toko lain, DITOLAK di toko yang sama
row = c.execute("SELECT wa, store_id FROM customers WHERE wa IS NOT NULL AND wa <> '' AND store_id IS NOT NULL LIMIT 1").fetchone()
if not row:
    row = c.execute("SELECT wa, store_id FROM customers WHERE wa IS NOT NULL LIMIT 1").fetchone()
wa0, st0 = row
print("  (uji dengan wa=%s store_id=%s)" % (wa0, st0))
try:
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (99999,'TES-SAMA',?,?)", (wa0, st0))
    chk("WA sama toko SAMA DITOLAK", False, "tidak ditolak!")
    con.rollback()
except Exception:
    chk("WA sama toko SAMA DITOLAK", True)
# toko lain (tidak ada di DB ini) -> harus boleh
try:
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (99999,'TES-LAIN',?,99)", (wa0,))
    chk("WA sama toko lain BOLEH", True)
    con.rollback()
except Exception as e:
    chk("WA sama toko lain BOLEH", False, e)

# WA KOSONG di toko sama -> BOLEH (bug 400 "WA sudah terdaftar")
try:
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (99998,'TES-KOSONG-1','',?)", (st0,))
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (99997,'TES-KOSONG-2','',?)", (st0,))
    chk("WA kosong di toko sama BOLEH (walk-in)", True)
    con.rollback()
except Exception as e:
    chk("WA kosong di toko sama BOLEH (walk-in)", False, e)

# IMEI sama di toko sama -> DITOLAK; di toko lain -> BOLEH
try:
    c.execute("INSERT INTO customers (id,nama,wa,imei,store_id) VALUES (99996,'TES-IMEI-1','089990000001','356938035643809',?)", (st0,))
    chk("customer dengan IMEI baru BOLEH", True)
    con.rollback()
except Exception as e:
    chk("customer dengan IMEI baru BOLEH", False, e)
try:
    c.execute("INSERT INTO customers (id,nama,wa,imei,store_id) VALUES (99996,'TES-IMEI-1','089990000001','356938035643809',?)", (st0,))
    c.execute("INSERT INTO customers (id,nama,wa,imei,store_id) VALUES (99995,'TES-IMEI-2','089990000002','356938035643809',?)", (st0,))
    chk("IMEI sama toko SAMA DITOLAK", False, "tidak ditolak!")
    con.rollback()
except Exception:
    chk("IMEI sama toko SAMA DITOLAK", True)
con.close()

print()
print("HASIL:", "LULUS" if ok else "GAGAL")
sys.exit(0 if ok else 1)
