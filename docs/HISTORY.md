# HISTORI SESI — POS → Platform BOS SERVICE

> Terakhir update: 22 Sep 2026 (sesi malam, Fase 3 + Dev Dashboard DONE di code). Next: uji browser + push POS1+BOS1.

## 1. Penanda Git (lokal, BELUM push)
- `POS1` (4b8d28c, empty commit) — titik beku POS satu-toko sebelum platform.
- `BOS1` (a8b6424, 20 files, +1606/-215) — platform multi-toko Fase 1+2.
- Remote: `https://github.com/budirenee-debug/PRAKTEK-CODING.git` — terakhir push `7da53a6`.
- **TODO push:** `POS1` + `BOS1` sekaligus (user minta digabung nanti).

## 2. Runner (3 file, jangan dicampur)
| File | Mode | Bind |
|---|---|---|
| `run.bat` | LOKAL ONLY (ngoding harian) | 127.0.0.1 |
| `run-lan.bat` | Review 1 jaringan, tanpa tunnel/deploy | 0.0.0.0 + deteksi IP + cek firewall |
| `run-tunnel.bat` | Publik via Cloudflare | 127.0.0.1 + tunnel |
- Server review jalan di `0.0.0.0:8000`. IP LAN saat ini: **192.168.1.187** (DHCP hotspot — bisa berubah!).
- Link LAN: `/frontend/landing.html`, `/register.html`, `/login.html`, `/index.html` di `http://192.168.1.187:8000`.

## 3. Keputusan Platform BOS SERVICE (final)
1. Register **invite-only** (sementara).
2. Nama: **BOS SERVICE (Bisnis Operasional System)** — service HP & laptop.
3. 1 akun **boleh** multi-toko (via `memberships`).
4. Fase 1 done (landing+register+login), Fase 2 done (scoping+switcher).

## 4. Yang Sudah Jadi & Terverifikasi
- **Frontend Fase 1:** `landing.html`, `register.html` (invite+kode, nama toko pertama, kontrak `POST /api/auth/register {invite_code,nama,username,wa,password,nama_toko}`), `login.html` rebrand (tab register terbuka DIHAPUS → link invite), `bos.css` terpisah.
- **Backend Fase 1:** tabel `stores/memberships/invites`, `User`+nama/wa, register owner/member, login bawa `stores[]+primary_store_id`, router `/api/invites` + `/api/stores`, migrasi toko `B_gadget (Toko Utama)/BGJ` + backfill.
- **Backend Fase 2:** `store_ctx.py` (resolve: eksplisit→cek member 403/anon 401; superadmin bebas; member→primer; anon→default), scoping semua endpoint + `/api/search`, invoice prefix per toko (**REN-2026-0001 terbukti**), UNIQUE komposit `(wa,store_id)`/`(nama,store_id)` via rebuild atomic, backfill membership user lama (TOLE/APUD/ANGDEDI/opi).
- **Frontend Fase 2:** `apiFetch` injeksi `?store_id=` (kecuali auth/stores/invites/seed), switcher 🏪 + brand dinamis, login simpan toko, logout bersihkan.
- **Uji:** isolasi 401/403 OK; akun `rpl` → toko **ReneePonsel/REN** (id 2); kode bootstrap owner: `BOS-VDZL-F4Y5` (belum dipakai — rpl daftar sebelum reset? cek: invite bootstrap direset `is_used=0` pas cleanup Fase 1, lalu rpl memakainya → sekarang USED. Butuh invite baru? buat via `POST /api/invites {"kind":"owner"}`).
- **DB:** `backend/b_gadget.db` (110 services); backup `b_gadget.backup-pre-multistore.db` (184KB, pre-Fase 1).

## 5. Gotcha (jangan diulang)
- Ganti `127.0.0.1`→LAN wajib stop server lama dulu (pernah nyangkut 2 proses: parent + orphan `--reload`).
- WiFi **Public** bikin rule firewall Private tidak berlaku → set Private (`Set-NetConnectionProfile`).
- PC ini via hotspot HP "Renee ponsel 4G" — reviewer WAJIB join hotspot yang sama.
- Ganti `script.js` wajib bump `?v=` di `index.html` (sekarang `?v=multistore-fase2`) + hard refresh.
- WA test jangan `081999999999` (itu data asli Fajar Nugroho!) — pakai `08100000000x`.
- Harness bash strip karakter `$` — hindari snippet PowerShell `$_` saat verifikasi.

## 6. NEXT (belum dikerjakan)
- **Fase 3 DONE di code (belum uji browser):** backend `GET/POST /api/stores/{id}/invites` + `POST .../revoke` + `PATCH/DELETE .../members/{membership_id}` (owner/admin only, guard anti-lockout); dashboard menu+view **Kelola Tim** (`?v=multistore-fase3`); `register.html?invite=` dukung member. Catatan: `backend/.env` pakai `DATABASE_URL` relatif — jalanin server via `run.bat`/dari `backend/` agar pakai DB asli.
- **Dev Dashboard DONE di code (22 Sep malam, belum uji browser):** `frontend/dev.html` terpisah (superadmin only, guard via `/api/auth/me`): kelola invite owner (buat/lihat/batalkan via `/api/invites` existing), reset password akun toko (`PUT /api/auth/users/{id}` password-only — catatan: jangan kirim role owner, ditolak validator), log aktivitas (`audit_logs` + `GET /api/audit` filter action/q, wiring: invite×3, member×2, user×5, store.create, register×3). E2E lolos di DB copy (403 non-superadmin OK). Pintu masuk: tombol 🛠️ Dev di view Persetujuan Akun + URL langsung `/frontend/dev.html`.
- Push `POS1`+`BOS1` ke GitHub (sekarang termasuk Fase 3 + dev, belum di-commit).
- Nanti: laporan gabungan owner, paket/billing, root `/` → landing (butuh edit `main.py`).
