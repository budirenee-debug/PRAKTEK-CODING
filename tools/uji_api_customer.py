"""Uji API level: WA kosong BEBAS (walk-in), IMEI unik per toko, service tanpa identitas
tidak lagi ditumpuk ke satu customer. Jalankan dengan DB salinan (aman, tidak sentuh DB asli).

    python tools/uji_api_customer.py <path_salinan.db>
"""
import os, shutil, sqlite3, sys, tempfile

SRC = sys.argv[1] if len(sys.argv) > 1 else None
if not SRC:
    print("pakai: python tools/uji_api_customer.py <salinan.db>")
    sys.exit(2)

WORK = tempfile.mkdtemp(prefix="api_uj_")
DB = os.path.join(WORK, "uj.db")
shutil.copyfile(SRC, DB)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.environ["DATABASE_URL"] = "sqlite:///" + DB

import app.main as main  # noqa: E402  (migrasi jalan di import)
from app.database import engine, SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

db0 = SessionLocal()
su = db0.query(models.User).filter(models.User.role == "superadmin").first()
if su is None:
    su = db0.query(models.User).first()
db0.close()
assert su is not None, "tidak ada user di DB salinan"

main.app.dependency_overrides[auth_router.get_current_user] = lambda: su
client = TestClient(main.app)

ok = True
def chk(label, cond, extra=""):
    global ok
    print(("  LULUS  " if cond else "  GAGAL  ") + label + ((" | " + str(extra)) if extra else ""))
    ok = ok and bool(cond)

S1, S2 = 1, 2
# cari 2 toko yang ada
con = sqlite3.connect(DB)
stores = [r[0] for r in con.execute("SELECT id FROM stores ORDER BY id")]
con.close()
if len(stores) >= 2:
    S1, S2 = stores[0], stores[1]

print("=== A) CUSTOMER tanpa WA (walk-in) ===")
r1 = client.post(f"/api/customers?store_id={S1}", json={"nama": "Uji Guest A", "wa": "", "imei": ""})
chk("customer WA kosong dibuat (201)", r1.status_code == 201, r1.status_code)
r2 = client.post(f"/api/customers?store_id={S1}", json={"nama": "Uji Guest B", "wa": "", "imei": ""})
chk("customer WA kosong kedua di toko sama BOLEH (201)", r2.status_code == 201,
    f"{r2.status_code} {r2.text[:120]}")

print()
print("=== B) CUSTOMER WA terisi & duplikat ===")
r3 = client.post(f"/api/customers?store_id={S1}", json={"nama": "Uji WA Isi", "wa": "089998880001", "imei": ""})
chk("customer WA baru (201)", r3.status_code == 201, r3.status_code)
r4 = client.post(f"/api/customers?store_id={S1}", json={"nama": "Uji WA Kembar", "wa": "089998880001", "imei": ""})
chk("WA sama toko sama DITOLAK (400)", r4.status_code == 400, f"{r4.status_code} {r4.text[:100]}")
r5 = client.post(f"/api/customers?store_id={S2}", json={"nama": "Uji WA Toko2", "wa": "089998880001", "imei": ""})
chk("WA sama toko lain BOLEH (201)", r5.status_code == 201, f"{r5.status_code} {r5.text[:100]}")

print()
print("=== C) CUSTOMER by IMEI ===")
r6 = client.post(f"/api/customers?store_id={S1}", json={"nama": "Uji Imei A", "wa": "", "imei": "356938035643809"})
chk("customer IMEI baru (201)", r6.status_code == 201, f"{r6.status_code} {r6.text[:120]}")
r7 = client.post(f"/api/customers?store_id={S1}", json={"nama": "Uji Imei B", "wa": "", "imei": "356938035643809"})
chk("IMEI sama toko sama DITOLAK (400)", r7.status_code == 400, f"{r7.status_code} {r7.text[:100]}")
r8 = client.post(f"/api/customers?store_id={S2}", json={"nama": "Uji Imei Toko2", "wa": "", "imei": "356938035643809"})
chk("IMEI sama toko lain BOLEH (201)", r8.status_code == 201, f"{r8.status_code} {r8.text[:120]}")
chk("response customer ada field imei", "imei" in (r6.json() if r6.status_code == 201 else {}),
    list(r6.json().keys()) if r6.status_code == 201 else r6.text[:120])

print()
print("=== D) SERVICE tanpa WA & tanpa IMEI -> tanpa customer (tak ditumpuk) ===")
before = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM customers").fetchone()[0]
rs1 = client.post(f"/api/services?store_id={S1}", json={
    "nama": "Uji Walkin", "wa": "", "device": "Xiaomi Redmi", "imei": "",
    "keluhan": "Layar pecah", "biaya": 0})
chk("service walk-in dibuat (201)", rs1.status_code == 201, f"{rs1.status_code} {rs1.text[:200]}")
con = sqlite3.connect(DB)
inv = rs1.json().get("invoice") if rs1.status_code == 201 else None
cid = con.execute("SELECT customer_id FROM services WHERE invoice=?", (inv,)).fetchone()[0] if inv else "?"
con.close()
chk("service walk-in TIDAK nempel ke customer lama", cid is None, f"customer_id={cid}")

print()
print("=== E) SERVICE tanpa WA tapi dengan IMEI -> customer by IMEI ===")
rs2 = client.post(f"/api/services?store_id={S1}", json={
    "nama": "Uji By Imei", "wa": "", "device": "Samsung A17", "imei": "356938035643777",
    "keluhan": "Baterai drop", "biaya": 0})
chk("service by IMEI dibuat (201)", rs2.status_code == 201, f"{rs2.status_code} {rs2.text[:200]}")
con = sqlite3.connect(DB)
inv2 = rs2.json().get("invoice") if rs2.status_code == 201 else None
row2 = con.execute("SELECT customer_id FROM services WHERE invoice=?", (inv2,)).fetchone() if inv2 else None
cust = con.execute("SELECT id,nama,wa,imei FROM customers WHERE id=?", (row2[0],)).fetchone() if row2 and row2[0] else None
con.close()
chk("service by IMEI nyambung ke customer dengan IMEI itu", cust is not None and cust[3] == "356938035643777", cust)

print()
print("=== F) LIST customers memuat imei ===")
rl = client.get(f"/api/customers?store_id={S1}")
rows = rl.json() if rl.status_code == 200 else []
chk("GET customers 200", rl.status_code == 200, rl.status_code)
chk("field imei ada di list", bool(rows) and "imei" in rows[0], list(rows[0].keys()) if rows else "kosong")

print()
print("=== G) CLEANUP ===")
con = sqlite3.connect(DB)
for nm in ("Uji Guest A", "Uji Guest B", "Uji WA Isi", "Uji WA Toko2", "Uji Imei A", "Uji Imei Toko2", "Uji By Imei"):
    con.execute("DELETE FROM customers WHERE nama=?", (nm,))
for invx in (inv, inv2):
    if invx:
        con.execute("DELETE FROM services WHERE invoice=?", (invx,))
con.commit()
con.close()
print("  data uji dihapus")

engine.dispose()
shutil.rmtree(WORK, ignore_errors=True)
print()
print("=" * 50)
print("HASIL:", "SEMUA LULUS" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
