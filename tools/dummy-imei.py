#!/usr/bin/env python3
"""
Dummy IMEI generator - tiap HP ada IMEI 15-digit, suffix 4-digit unik untuk tes keyword search
Sync ke LOCAL + PUBLIC (service.reneepsl.my.id)
"""
import httpx
import json
from datetime import date, timedelta

LOCAL = "http://127.0.0.1:8000"
PUBLIC = "https://service.reneepsl.my.id"

# 15 dummy dengan IMEI unik, keyword suffix 4-digit beda-beda
DUMMIES = [
    # suffix 1111, 2222 etc mudah diingat untuk tes keyword
    {"nama":"Riko Saputra","wa":"081111111111","device":"iPhone 15 Pro 256GB","imei":"352756084321111","keluhan":"LCD retak pojok kanan","teknisi":"TOLE","biaya":750000,"status":"Antri","kelengkapan":["HP Saja","+ Charger"]},
    {"nama":"Mela Sari","wa":"081222222222","device":"Samsung Galaxy S24 Ultra","imei":"352756084322222","keluhan":"Baterai boros & panas","teknisi":"ANGDEDI","biaya":450000,"status":"Dikerjakan","kelengkapan":["HP Saja","+ Dus"]},
    {"nama":"Joko Anwar","wa":"081333333333","device":"Xiaomi Poco F5 12/256","imei":"352756084333333","keluhan":"Mati total habis jatuh","teknisi":"APUD","biaya":550000,"status":"Antri","kelengkapan":["HP Saja"]},
    {"nama":"Siska Amelia","wa":"081444444444","device":"Oppo Reno 10 Pro","imei":"352756084344444","keluhan":"Kamera blur tidak fokus","teknisi":"TOLE","biaya":350000,"status":"Menunggu Sparepart","kelengkapan":["HP Saja","+ Charger","+ Dus"]},
    {"nama":"Bambang Wijaya","wa":"081555555555","device":"Vivo V29 5G","imei":"352756084355555","keluhan":"Speaker sember","teknisi":"ANGDEDI","biaya":250000,"status":"Antri","kelengkapan":["HP Saja"]},
    {"nama":"Lina Marlina","wa":"081666666666","device":"iPhone 13 128GB","imei":"352756084366666","keluhan":"Face ID tidak berfungsi","teknisi":"APUD","biaya":650000,"status":"Dikerjakan","kelengkapan":["HP Saja","+ Charger"]},
    {"nama":"Dedi Setiawan","wa":"081777777777","device":"Infinix Hot 40 Pro","imei":"352756084377777","keluhan":"Charger tidak mengisi","teknisi":"TOLE","biaya":150000,"status":"Antri","kelengkapan":["HP Saja"]},
    {"nama":"Ayu Lestari","wa":"081888888888","device":"Realme 11 Pro+ 5G","imei":"352756084388888","keluhan":"Layar kedip hijau","teknisi":"ANGDEDI","biaya":850000,"status":"Menunggu Konfirmasi","kelengkapan":["HP Saja","+ Dus"]},
    {"nama":"Fajar Nugroho","wa":"081999999999","device":"Samsung A54 5G","imei":"352756084399999","keluhan":"Sinyal hilang","teknisi":"APUD","biaya":300000,"status":"Antri","kelengkapan":["HP Saja","+ Kartu SIM"]},
    {"nama":"Nadia Putri","wa":"082000000001","device":"iPhone 12 Mini","imei":"352756084300001","keluhan":"Baterai kembung","teknisi":"TOLE","biaya":400000,"status":"Dikerjakan","kelengkapan":["HP Saja"]},
    # suffix cantik untuk tes
    {"nama":"Eko Prasetyo","wa":"082121212121","device":"iPhone 11 Pro Max","imei":"352756084312121","keluhan":"Mic mati lawan tidak dengar","teknisi":"ANGDEDI","biaya":350000,"status":"Antri","kelengkapan":["HP Saja","+ Charger"]},
    {"nama":"Wulan Dari","wa":"082343434343","device":"Oppo A78","imei":"352756084334343","keluhan":"Tombol power macet","teknisi":"APUD","biaya":180000,"status":"Antri","kelengkapan":["HP Saja"]},
    {"nama":"Haris Maulana","wa":"082567856785","device":"Vivo Y100 5G","imei":"352756084356785","keluhan":"Getar tidak berfungsi","teknisi":"TOLE","biaya":220000,"status":"Menunggu Sparepart","kelengkapan":["HP Saja","+ Charger"]},
    {"nama":"Citra Kirana","wa":"082876543210","device":"Xiaomi 13T Pro","imei":"352756084387654","keluhan":"HP lemot lag parah","teknisi":"ANGDEDI","biaya":250000,"status":"Antri","kelengkapan":["HP Saja","+ Dus"]},
    {"nama":"Dinda Kirana","wa":"082999988887","device":"Samsung Z Flip 5","imei":"352756084399887","keluhan":"Engsel bunyi & layar bergaris","teknisi":"APUD","biaya":1200000,"status":"Dikerjakan","kelengkapan":["HP Saja","+ Charger","+ Dus"]},
]

def login(base):
    r = httpx.post(f"{base}/api/auth/login", json={"username":"superadmin","password":"bismillah"}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]

def create(base, token, payload):
    headers = {"Authorization": f"Bearer {token}"}
    # payload ke API: kelengkapan list, imei string
    body = {
        "nama": payload["nama"],
        "wa": payload["wa"],
        "device": payload["device"],
        "imei": payload["imei"],
        "keluhan": payload["keluhan"],
        "kelengkapan": payload["kelengkapan"],
        "biaya": payload["biaya"],
        "teknisi": payload["teknisi"],
        "status": payload["status"],
        "penerima": "superadmin",
    }
    # auto estimasi harian 3 hari
    r = httpx.post(f"{base}/api/services", json=body, headers=headers, timeout=15)
    return r

def main():
    for base, label in [(LOCAL, "LOCAL"), (PUBLIC, "PUBLIC")]:
        print(f"\n=== {label} {base} ===")
        try:
            token = login(base)
            print(f"login OK token len={len(token)}")
        except Exception as e:
            print(f"login FAIL {base}: {e}")
            continue

        created = []
        failed = []
        for d in DUMMIES:
            try:
                resp = create(base, token, d)
                if resp.status_code in (200,201):
                    j = resp.json()
                    inv = j.get("invoice")
                    print(f"  OK {inv} | {d['device']} | IMEI {d['imei']} -> suffix {d['imei'][-4:]}")
                    created.append(inv)
                else:
                    print(f"  FAIL {d['wa']} {resp.status_code} {resp.text[:300]}")
                    failed.append((d['wa'], resp.text[:200]))
            except Exception as e:
                print(f"  ERR {d['wa']}: {e}")
                failed.append((d['wa'], str(e)))

        print(f"--- {label} Summary: {len(created)} OK, {len(failed)} FAIL ---")

        # Verify search IMEI works
        print(f"  Verifikasi search IMEI di {label}:")
        headers = {"Authorization": f"Bearer {token}"}
        for suffix in ["1111","2222","3333","1212","8765"]:
            try:
                r = httpx.get(f"{base}/api/services", params={"search": suffix}, timeout=10)
                data = r.json()
                # crud search cari di imei juga
                hits = [x for x in data if suffix in (x.get("imei") or "")]
                print(f"    search '{suffix}' -> {len(data)} row(s) API, {len(hits)} hit IMEI exact | contoh: {[h['imei'] for h in hits[:2]]}")
            except Exception as e:
                print(f"    search {suffix} err {e}")

        # Global search juga
        try:
            r = httpx.get(f"{base}/api/search", params={"q": "3527560843"}, timeout=10)
            data = r.json()
            print(f"  /api/search q=3527560843 -> {len(data)} hits")
        except Exception as e:
            print(f"  /api/search err {e}")

    print("\nDONE - silahkan tes keyword di:")
    print("  Local : http://127.0.0.1:8000/frontend/login.html -> login superadmin/bismillah -> search IMEI suffix misal 1111")
    print("  Public: https://service.reneepsl.my.id/frontend/login.html -> sama")
    print("\nKeyword rekomendasi untuk tes (tiap suffix unik):")
    for d in DUMMIES:
        print(f"  {d['imei'][-4:]} -> {d['nama']} - {d['device']} - {d['imei']}")

if __name__ == "__main__":
    main()
