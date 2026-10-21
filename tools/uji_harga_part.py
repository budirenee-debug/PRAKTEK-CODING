"""Uji: harga part yang dipakai KELUAR dari basis komisi teknisi (pajak toko).

Aturan: komisi = % x (biaya - harga_part_up), harga_part_up otomatis = total harga
part yang dipakai (x qty). Override manual owner = max(manual, total part).
Row yang sudah 'cair' TIDAK disentuh (forward-only, sesuai keputusan owner).

    python tools/uji_harga_part.py <path_salinan.db>
"""
import os, shutil, sqlite3, sys, tempfile

SRC = sys.argv[1] if len(sys.argv) > 1 else None
if not SRC:
    print("pakai: python tools/uji_harga_part.py <salinan.db>")
    sys.exit(2)

WORK = tempfile.mkdtemp(prefix="hpp_uj_")
DB = os.path.join(WORK, "uj.db")
shutil.copyfile(SRC, DB)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.environ["DATABASE_URL"] = "sqlite:///" + DB

import app.main as main  # noqa: E402  (migrasi jalan di import)
from app.database import SessionLocal  # noqa: E402
from app import models, engine_logic  # noqa: E402
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

# --- cari data uji: toko, teknisi, sparepart berstok ---
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
store = con.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()
S = store["id"]
tech = con.execute("SELECT id, nama, level FROM technicians WHERE store_id=? ORDER BY id LIMIT 1",
                    (S,)).fetchone()
sp = con.execute("""SELECT id, nama, harga, harga_beli, stok FROM spareparts
                    WHERE store_id=? AND COALESCE(harga,0) > 0 AND COALESCE(stok,0) >= 2
                    ORDER BY id LIMIT 1""", (S,)).fetchone()
con.close()
if not tech or not sp:
    print("data uji kurang (teknisi/sparepart) - skip")
    sys.exit(0)

# persen komisi dari settings
db = SessionLocal()
sett = engine_logic.get_settings(db, S)
pct = sett.komisi_senior if (tech["level"] or "junior") == "senior" else sett.komisi_junior
pct = pct or 0
print(f"toko={S} teknisi={tech['nama']} level={tech['level']} pct={pct}% part={sp['nama']} "
      f"harga={sp['harga']} modal={sp['harga_beli']}")

BIAYA = 200000
harga_part = int(sp["harga"] or 0)

print()
print("=== A) Service baru tanpa part ===")
r = client.post(f"/api/services?store_id={S}", json={
    "nama": "Uji HPP", "wa": "", "device": "Uji HPP", "imei": "",
    "keluhan": "Ganti layar pecah", "biaya": BIAYA, "teknisi": tech["nama"],
    "status": "Antri"})
chk("service dibuat (201)", r.status_code == 201, r.status_code)
INV = r.json().get("invoice") if r.status_code == 201 else None
if not INV:
    print(r.text[:300]); sys.exit(1)

def eng(inv):
    db = SessionLocal()
    se = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == inv).first()
    out = (se.harga_part_up, se.harga_part_manual, se.jasa_bersih, se.komisi_teknisi,
           se.komisi_status) if se else None
    db.close()
    return out

e = eng(INV)
chk("harga_part_up awal 0", e[0] == 0, e)
chk("jasa_bersih = biaya", e[2] == BIAYA, e)
chk("komisi = %d%% dari jasa" % pct, e[3] == BIAYA * pct // 100, e)

print()
print("=== B) Pakai part -> harga part keluar dari basis komisi ===")
r = client.post(f"/api/inventory/spareparts/{sp['id']}/pakai?invoice={INV}&qty=1&store_id={S}")
chk("pakai part (200)", r.status_code == 200, f"{r.status_code} {r.text[:150]}")
e = eng(INV)
chk("harga_part_up = harga part", e[0] == harga_part, e)
chk("jasa_bersih = biaya - harga part", e[2] == BIAYA - harga_part, e)
chk("komisi = %d%% dari jasa (tidak ikut part)" % pct, e[3] == (BIAYA - harga_part) * pct // 100, e)
komisi_baru = e[3]

print()
print("=== C) Part dikembalikan -> komisi balik lagi ===")
part_id = r.json()["part"]["id"] if r.status_code == 200 else None
r2 = client.delete(f"/api/inventory/service-parts/{part_id}?store_id={S}")
chk("part dibatalkan (200)", r2.status_code == 200, f"{r2.status_code} {r2.text[:150]}")
e = eng(INV)
chk("harga_part_up balik 0", e[0] == 0, e)
chk("komisi balik penuh", e[3] == BIAYA * pct // 100, e)

print()
print("=== D) Override manual owner (max(manual, total part)) ===")
r = client.post(f"/api/inventory/spareparts/{sp['id']}/pakai?invoice={INV}&qty=1&store_id={S}")
part_id = r.json()["part"]["id"] if r.status_code == 200 else None
manual_kecil = max(1, harga_part - 1000)
r = client.put(f"/api/engine/service/{INV}/part?store_id={S}",
               json={"harga_part_up": manual_kecil})
chk("PUT part manual (200)", r.status_code == 200, f"{r.status_code} {r.text[:150]}")
e = eng(INV)
chk("manual < harga part -> efektif tetap harga part", e[0] == harga_part, e)
chk("manual tersimpan di harga_part_manual", e[1] == manual_kecil, e)
manual_besar = harga_part + 5000
r = client.put(f"/api/engine/service/{INV}/part?store_id={S}",
               json={"harga_part_up": manual_besar})
e = eng(INV)
chk("manual > harga part -> efektif = manual", e[0] == manual_besar, e)
# kembalikan ke harga part (manual = 0 -> efektif = harga part)
r = client.put(f"/api/engine/service/{INV}/part?store_id={S}", json={"harga_part_up": 0})
e = eng(INV)
chk("manual 0 -> efektif = harga part lagi", e[0] == harga_part, e)

print()
print("=== E) CAIR (Service Sukses) -> komisi + info HPP di ledger ===")
r = client.put(f"/api/services/{INV}/status?status=Service Sukses&store_id={S}")
chk("status -> Service Sukses (200)", r.status_code == 200, f"{r.status_code} {r.text[:150]}")
db = SessionLocal()
row = db.query(models.CommissionLedger).filter(
    models.CommissionLedger.invoice == INV, models.CommissionLedger.tipe == "komisi_cair").first()
chk("ada baris komisi_cair", row is not None)
if row:
    expect = (BIAYA - harga_part) * pct // 100
    chk("komisi_cair = %d (tidak ikut harga part)" % expect, row.masuk_rp == expect,
        f"masuk={row.masuk_rp} masuk+pot={row.masuk_rp}")
    chk("hpp_rp = harga part", (row.hpp_rp or 0) == harga_part, row.hpp_rp)
    chk("keterangan menyebut harga part", "harga part" in (row.keterangan or ""), row.keterangan)
db.close()

print()
print("=== F) FORWARD-ONLY: service yang sudah cair tidak diubah ===")
db = SessionLocal()
svc = db.query(models.Service).filter(models.Service.invoice == INV).first()
se = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == INV).first()
se_before = (se.harga_part_up, se.jasa_bersih, se.komisi_teknisi)
# paksa tambah part di DB (melewati lock terminal)
db.add(models.ServicePart(store_id=S, invoice=INV, sparepart_id=sp["id"],
                          nama_snapshot=sp["nama"], harga_up_snapshot=harga_part,
                          modal_asli_snapshot=int(sp["harga_beli"] or 0), qty=1))
db.commit()
engine_logic.sync_harga_part(db, svc, se)
db.commit()
se = db.query(models.ServiceEngine).filter(models.ServiceEngine.invoice == INV).first()
se_after = (se.harga_part_up, se.jasa_bersih, se.komisi_teknisi)
chk("baris cair tidak berubah", se_before == se_after, f"{se_before} -> {se_after}")
# bersihkan part palsu
db.query(models.ServicePart).filter(models.ServicePart.invoice == INV).delete(synchronize_session=False)
db.commit()
db.close()

print()
print("=== G) Kas teknisi: info Potong HPP ===")
db = SessionLocal()
tid = db.query(models.Technician).filter(models.Technician.nama == tech["nama"]).first().id
db.close()
r = client.get(f"/api/engine/kas/teknisi/{tid}?store_id={S}")
chk("GET kas teknisi (200)", r.status_code == 200, r.status_code)
if r.status_code == 200:
    j = r.json()
    chk("ada field potongan_hpp", "potongan_hpp" in j, list(j.keys())[:12])
    chk("potongan_hpp >= harga part uji", (j.get("potongan_hpp") or 0) >= harga_part,
        j.get("potongan_hpp"))
    rw = [x for x in (j.get("riwayat") or []) if x.get("invoice") == INV]
    chk("riwayat baris uji punya hpp", rw and (rw[0].get("hpp") or 0) == harga_part, rw[:1])

db = SessionLocal()
db.close()

print()
print("HASIL: " + ("SEMUA LULUS" if ok else "ADA YANG GAGAL"))
sys.exit(0 if ok else 1)
