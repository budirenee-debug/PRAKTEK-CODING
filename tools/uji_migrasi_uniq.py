"""Uji migrasi UNIQUE per toko + WA kosong bebas + IMEI unik per toko (DB temp, tanpa menyentuh DB asli)."""
import os, sqlite3, sys, tempfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

WORK = tempfile.mkdtemp(prefix="mig_uj_")
DB = os.path.join(WORK, "uj.db")

def _dispose():
    """Lepas engine SQLAlchemy yang masih memegang file DB (Windows lock)."""
    try:
        from app.database import engine
        engine.dispose()
    except Exception:
        pass

def build_db(with_leftover=True, drop_main=False, dup=False, blank_wa=False):
    _dispose()
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("""CREATE TABLE stores (id INTEGER NOT NULL PRIMARY KEY, nama VARCHAR(120) NOT NULL,
                 kode VARCHAR(10) UNIQUE NOT NULL, alamat VARCHAR(255), wa VARCHAR(20),
                 owner_id INTEGER, is_active INTEGER DEFAULT 1, created_at DATETIME)""")
    c.execute("INSERT INTO stores (id,kode,nama) VALUES (1,'RPL','Toko 1')")
    c.execute("INSERT INTO stores (id,kode,nama) VALUES (2,'BGJ','Toko 2')")
    # customers versi lama: UNIQUE GLOBAL di wa (index unik terpisah, bukan constraint di DDL)
    c.execute("""CREATE TABLE customers (id INTEGER NOT NULL, nama VARCHAR(120) NOT NULL,
                 wa VARCHAR(20) NOT NULL, created_at DATETIME, updated_at DATETIME,
                 store_id INTEGER, PRIMARY KEY (id))""")
    c.execute("CREATE INDEX ix_customers_nama ON customers (nama)")
    c.execute("CREATE INDEX ix_customers_id ON customers (id)")
    if not dup:
        c.execute("CREATE UNIQUE INDEX ix_customers_wa ON customers (wa)")
    c.execute("INSERT INTO customers VALUES (1,'Andi','081200000001',NULL,NULL,1)")
    c.execute("INSERT INTO customers VALUES (2,'Budi','081200000002',NULL,NULL,1)")
    if blank_wa:
        # pelanggan tanpa WA (walk-in). DB lama punya UNIQUE GLOBAL wa, jadi
        # hanya boleh 1 baris WA kosong -> 1 Guest1 saja (Guest2 diuji
        # SETELAH migrasi, harusnya boleh)
        c.execute("INSERT INTO customers VALUES (3,'Guest1','',NULL,NULL,1)")
    if dup:
        # duplikat (wa, store_id) - harus bikin rebuild di-SKIP, data tetap utuh
        c.execute("INSERT INTO customers VALUES (3,'Andi2','081200000001',NULL,NULL,1)")
    c.execute("""CREATE TABLE technicians (id INTEGER NOT NULL, nama VARCHAR(100) NOT NULL,
                 foto VARCHAR(255), is_active INTEGER, created_at DATETIME,
                 store_id INTEGER, level VARCHAR(20) DEFAULT 'junior', PRIMARY KEY (id))""")
    c.execute("CREATE UNIQUE INDEX ix_technicians_nama ON technicians (nama)")
    c.execute("INSERT INTO technicians VALUES (1,'TOLE',NULL,1,NULL,1,'junior')")
    c.execute("INSERT INTO technicians VALUES (2,'ANGDEDI',NULL,1,NULL,1,'junior')")
    # sisa customers_new dari run crash
    if with_leftover:
        c.execute("""CREATE TABLE customers_new (id INTEGER NOT NULL PRIMARY KEY,
                     store_id INTEGER REFERENCES stores(id), nama VARCHAR(120) NOT NULL,
                     wa VARCHAR(20) NOT NULL, created_at DATETIME, updated_at DATETIME,
                     CONSTRAINT uq_customer_wa_store UNIQUE (wa, store_id))""")
    if drop_main:
        c.execute("DROP TABLE customers")
    con.commit()
    con.close()

def run_migration():
    """Import app.main (migrasi jalan di import time) dengan DATABASE_URL = DB temp."""
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
    import app.main  # noqa: F401
    # lepas koneksi SQLAlchemy supaya file DB bisa dihapus (Windows lock)
    from app.database import engine
    engine.dispose()

def snapshot():
    con = sqlite3.connect(DB)
    c = con.cursor()
    sqls = {r[0]: r[1] for r in c.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table'")}
    idxs = {r[0]: r[1] for r in c.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index'")}
    cnt_c = c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    cnt_t = c.execute("SELECT COUNT(*) FROM technicians").fetchone()[0]
    rows_c = c.execute("SELECT id,nama,wa,store_id FROM customers ORDER BY id").fetchall()
    cols_c = [r[1] for r in c.execute("PRAGMA table_info(customers)")]
    con.close()
    return sqls, idxs, cnt_c, cnt_t, rows_c, cols_c

def check(label, cond, extra=""):
    print(("  LULUS  " if cond else "  GAGAL  ") + label + ((" | " + str(extra)) if extra else ""))
    return cond

ok = True

print("=== KASUS 1: leftover customers_new (0 baris) + UNIQUE global ===")
build_db(with_leftover=True)
run_migration()
sqls, idxs, cnt_c, cnt_t, rows_c, cols_c = snapshot()
ok &= check("customers_new hilang", "customers_new" not in sqls)
ok &= check("kolom imei ada di customers", "imei" in cols_c, cols_c)
ok &= check("index partial uq_customer_wa_store ada", "uq_customer_wa_store" in idxs,
            idxs.get("uq_customer_wa_store"))
ok &= check("index partial uq_customer_imei_store ada", "uq_customer_imei_store" in idxs,
            idxs.get("uq_customer_imei_store"))
ok &= check("index WA punya WHERE (WA kosong bebas)", "WHERE" in (idxs.get("uq_customer_wa_store") or "").upper())
ok &= check("index IMEI punya WHERE (IMEI kosong bebas)", "WHERE" in (idxs.get("uq_customer_imei_store") or "").upper())
ok &= check("constraint tabel UNIQUE(wa,store_id) DICABUT", "UNIQUE (WA, STORE_ID)" not in " ".join((sqls.get("customers") or "").upper().split()))
ok &= check("teknicians punya constraint komposit", "uq_technician_nama_store" in (sqls.get("technicians") or ""))
ok &= check("ix_customers_wa bukan UNIQUE global", "UNIQUE" not in (idxs.get("ix_customers_wa") or ""), idxs.get("ix_customers_wa"))
ok &= check("ix_technicians_nama bukan UNIQUE global", "UNIQUE" not in (idxs.get("ix_technicians_nama") or ""), idxs.get("ix_technicians_nama"))
ok &= check("data customers utuh (2)", cnt_c == 2, cnt_c)
ok &= check("data teknisi utuh (2)", cnt_t == 2, cnt_t)
ok &= check("index ix_customers_id tetap ada", "ix_customers_id" in idxs)

# UNIQUE komposit harus berlaku: WA sama di toko BERBEDA boleh
con = sqlite3.connect(DB)
c = con.cursor()
try:
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (99,'Warung','081200000001',2)")
    ok &= check("WA sama toko berbeda BOLEH", True)
except Exception as e:
    ok &= check("WA sama toko berbeda BOLEH", False, e)
try:
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (98,'Duplikat','081200000001',1)")
    ok &= check("WA sama toko SAMA DITOLAK", False, "tidak ditolak!")
except Exception:
    ok &= check("WA sama toko SAMA DITOLAK", True)
con.rollback()
con.close()

print()
print("=== KASUS 1b: WA KOSONG bebas (walk-in) + IMEI unik per toko ===")
build_db(with_leftover=False, blank_wa=True)
run_migration()
sqls, idxs, cnt_c, cnt_t, rows_c, cols_c = snapshot()
ok &= check("data tetap 3 (2 walk-in ikut)", cnt_c == 3, cnt_c)
con = sqlite3.connect(DB)
c = con.cursor()
try:
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (90,'Guest3','',1)")
    ok &= check("WA kosong di toko sama BOLEH (tidak lagi 400)", True)
except Exception as e:
    ok &= check("WA kosong di toko sama BOLEH (tidak lagi 400)", False, e)
try:
    c.execute("INSERT INTO customers (id,nama,wa,store_id) VALUES (91,'Guest4','',1)")
    ok &= check("WA kosong tambahan BOLEH", True)
except Exception as e:
    ok &= check("WA kosong tambahan BOLEH", False, e)
try:
    c.execute("INSERT INTO customers (id,nama,wa,imei,store_id) VALUES (92,'Budi2','081200000009','356938035643809',1)")
    ok &= check("customer baru dengan IMEI BOLEH", True)
except Exception as e:
    ok &= check("customer baru dengan IMEI BOLEH", False, e)
try:
    c.execute("INSERT INTO customers (id,nama,wa,imei,store_id) VALUES (93,'Budi3','081200000010','356938035643809',1)")
    ok &= check("IMEI sama toko SAMA DITOLAK", False, "tidak ditolak!")
except Exception:
    ok &= check("IMEI sama toko SAMA DITOLAK", True)
try:
    c.execute("INSERT INTO customers (id,nama,wa,imei,store_id) VALUES (94,'Budi4','081200000011','356938035643809',2)")
    ok &= check("IMEI sama toko BERBEDA BOLEH", True)
except Exception as e:
    ok &= check("IMEI sama toko BERBEDA BOLEH", False, e)
con.rollback()
con.close()

print()
print("=== KASUS 2: idempotent (jalan 2x, 3x) ===")
for i in range(2):
    run_migration()
    sqls, idxs, cnt_c, cnt_t, rows_c, cols_c = snapshot()
    ok &= check(f"run ulang #{i+1}: customers_new tak muncul", "customers_new" not in sqls)
    ok &= check(f"run ulang #{i+1}: data tetap 3/2", cnt_c == 3 and cnt_t == 2, f"{cnt_c}/{cnt_t}")
    ok &= check(f"run ulang #{i+1}: index partial tetap ada",
                "uq_customer_wa_store" in idxs and "uq_customer_imei_store" in idxs)
    ok &= check(f"run ulang #{i+1}: tak ada rebuild ulang (ix_customers_wa non-unique)",
                "UNIQUE" not in (idxs.get("ix_customers_wa") or ""))

print()
print("=== KASUS 3: crash setelah DROP TABLE (customers hilang, customers_new ada) ===")
build_db(with_leftover=True, drop_main=True)
# isi customers_new dengan data supaya promote meaningful
con = sqlite3.connect(DB)
c = con.cursor()
c.execute("INSERT INTO customers_new (id,nama,wa,store_id) VALUES (5,'Sisa','081200000005',1)")
c.execute("INSERT INTO technicians VALUES (3,'SISA',NULL,1,NULL,1,'junior')")
con.commit()
con.close()
run_migration()
sqls, idxs, cnt_c, cnt_t, rows_c, cols_c = snapshot()
ok &= check("customers dipromote balik", "customers" in sqls)
ok &= check("customers_new hilang", "customers_new" not in sqls)
ok &= check("data sisa terpromote (1)", cnt_c == 1, rows_c)
ok &= check("index partial terpasang", "uq_customer_wa_store" in idxs and "uq_customer_imei_store" in idxs)

print()
print("=== KASUS 4: duplikat -> rebuild SKIP, data tetap utuh ===")
build_db(with_leftover=False, dup=True)
run_migration()
sqls, idxs, cnt_c, cnt_t, rows_c, cols_c = snapshot()
ok &= check("customers tetap ada (tidak dihapus)", "customers" in sqls)
ok &= check("data duplikat utuh (3)", cnt_c == 3, cnt_c)
ok &= check("constraint global tetap (belum komposit)",
            "uq_customer_wa_store" not in idxs)

print()
print("=== KASUS 5: DB sudah komposit -> idempotent, tak ada error ===")
build_db(with_leftover=False)
run_migration()
run_migration()
sqls, idxs, cnt_c, cnt_t, rows_c, cols_c = snapshot()
ok &= check("tetap komposit", "uq_customer_wa_store" in idxs)
ok &= check("data utuh", cnt_c == 2 and cnt_t == 2)

shutil.rmtree(WORK, ignore_errors=True)
print()
print("=" * 50)
print("HASIL:", "SEMUA LULUS" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
