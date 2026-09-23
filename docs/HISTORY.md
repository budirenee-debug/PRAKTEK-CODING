# HISTORI SESI — POS → Platform BOS SERVICE

> Terakhir update: 23 Sep 2026 malam (BOS6 DONE + push, repo bersih sejajar origin/main).

## 1. Penanda Git (SUDAH push 23 Sep 2026, main sejajar origin/main)
- `POS1` (4b8d28c, empty commit) — titik beku POS satu-toko sebelum platform.
- `BOS1` (a8b6424, 20 files, +1606/-215) — platform multi-toko Fase 1+2.
- `BOS2` (342d094, 14 files, +941/-14) — Fase 3 undang tim + dev dashboard + audit log.
- `d391d00` — klaim garansi + tgl pengambilan + pendapatan real.
- `dc39584` — peran teknisi + foto profil + template WA.
- `BOS3` (5d6b4b0) — profil toko + dashboard compact + metode bayar + tab Pembayaran.
- `BOS4` (7211e31) — laporan Service + rekap pendapatan Mingguan/Bulanan + pagination + legacy redirect.
- `BOS5` (11291b4) — identitas warna navy #04074a.
- `BOS6` (82e806d, HEAD) — nota digital WA + cetak Thermal/A4 + keterangan/kondisi awal.
- Remote: `https://github.com/budirenee-debug/PRAKTEK-CODING.git` — main sejajar origin/main per 23 Sep 17:30.

## 2. Runner (3 file, jangan dicampur)
| File | Mode | Bind |
|---|---|---|
| `run.bat` | LOKAL ONLY (ngoding harian) | 127.0.0.1 |
| `run-lan.bat` | Review 1 jaringan, tanpa tunnel/deploy | 0.0.0.0 + deteksi IP + cek firewall |
| `run-tunnel.bat` | Publik via Cloudflare | 127.0.0.1 + tunnel |
- Server review jalan di `0.0.0.0:8000`. IP LAN terakhir tercatat: **192.168.1.187** (DHCP hotspot — bisa berubah, cek ulang via `run-lan.bat`).
- Link LAN: `/frontend/landing.html`, `/register.html`, `/login.html`, `/index.html` di `http://<IP-LAN>:8000`.

## 3. Keputusan Platform BOS SERVICE (final)
1. Register **invite-only** (sementara).
2. Nama: **BOS SERVICE (Bisnis Operasional System)** — service HP & laptop.
3. 1 akun **boleh** multi-toko (via `memberships`).
4. Fase 1 done (landing+register+login), Fase 2 done (scoping+switcher), Fase 3 done (undang tim).

## 4. Yang Sudah Jadi & Terverifikasi
- **Frontend Fase 1:** `landing.html`, `register.html` (invite+kode, nama toko pertama, kontrak `POST /api/auth/register {invite_code,nama,username,wa,password,nama_toko}`), `login.html` rebrand (tab register terbuka DIHAPUS → link invite), `bos.css` terpisah.
- **Backend Fase 1:** tabel `stores/memberships/invites`, `User`+nama/wa, register owner/member, login bawa `stores[]+primary_store_id`, router `/api/invites` + `/api/stores`, migrasi toko `B_gadget (Toko Utama)/BGJ` + backfill.
- **Backend Fase 2:** `store_ctx.py` (resolve: eksplisit→cek member 403/anon 401; superadmin bebas; member→primer; anon→default), scoping semua endpoint + `/api/search`, invoice prefix per toko (**REN-2026-0001 terbukti**), UNIQUE komposit `(wa,store_id)`/`(nama,store_id)` via rebuild atomic, backfill membership user lama (TOLE/APUD/ANGDEDI/opi).
- **Frontend Fase 2:** `apiFetch` injeksi `?store_id=` (kecuali auth/stores/invites/seed), switcher 🏪 + brand dinamis, login simpan toko, logout bersihkan.
- **Uji isolasi:** 401/403 OK; akun `rpl` → toko **ReneePonsel/REN** (id 2); kode bootstrap owner `BOS-VDZL-F4Y5` sudah USED (buat invite baru via `POST /api/invites {"kind":"owner"}` bila perlu).
- **Garansi + Pengambilan + Pendapatan (d391d00):** kolom `garansi_hari/sampai/dari` + `diambil_at` (migrasi auto + backfill dari `updated_at`); `POST /services/{inv}/klaim-garansi` (jendela ikut root); popup masa garansi saat Sukses; Sukses dalam garansi tampil di Sudah Diambil DAN tab Garansi; badge "📥 Diambil ..." di Sudah Diambil; semua tab urut terbaru (`updated_at` ikut frontend); Pendapatan hanya hitung status Service Sukses; modal Detail read-only di tab terminal/pendapatan; search topbar ngikutin tab aktif.
- **Teknisi + Foto + WA (dc39584):** filter teknisi per tab (7 tab); teknisi hanya lihat service miliknya + Menunggu Teknisi (backend enforce, ubah/oper milik orang ditolak); pelanggan 403 + menu disembunyikan; assign teknisi terbatas ke diri sendiri; foto profil upload kompres otomatis max 256px JPG q70 (maks 5MB, Pillow, folder avatars di-ignore git) tampil sidebar+laporan; `wa_templates` per toko (masuk/sukses/gagal/diambil/garansi/umum + variabel); view Pengaturan Toko; tombol WA Proses pakai template service_masuk; alasan gagal wajib dari tab mana pun, kartu Failed tampil "📋 Alasan:".
- **BOS3 — Toko + Bayar:** `PATCH /stores/{id}` (nama/alamat/WA) + dashboard compact 1-layar + reset filter Semua Service; kolom `metode_bayar` (Tunai/Transfer/QRIS) + badge picker di popup Sukses + tampil di kartu/Semua/Pendapatan/Detail + export CSV; tab Pembayaran 3 kolom + rincian filter + search.
- **BOS4 — Laporan:** ringkasan Masuk/Sukses/Failed/Garansi + tab Harian/Mingguan/Bulanan + export CSV (fix zona waktu Senin lokal); Pendapatan rekap Mingguan 8 minggu + Bulanan 12 bulan, pagination 10/halaman, Mingguan/Bulanan jadi lipatan, kartu stat pindah ke atas; legacy root `index.html`/`login.html` jadi redirect ke `frontend/`.
- **BOS5 — Navy:** identitas `#04074a` (sidebar + tombol gelap + tab/chip/badge/progress/focus/toast, var `--brand`); login logo navy; `bos.css` diseragamkan (landing/register/dev); cache-bust `navy1`.
- **BOS6 — Nota (HEAD):** template `nota_digital` per toko (`backend/app/routers/stores.py`) + popup nota setelah simpan (preview, kirim via `wa.me`, cetak); tombol Nota WA di detail; area print + ukuran Thermal 58/80mm & A4 (pilihan diingat); form kotak Keterangan/Kondisi Awal (tersimpan + ikut nota WA/cetak); fix `crud.create_service` teruskan keterangan (tes in-memory OK). Label sidebar `vBOS3-nota3`, `script.js?v=nota3`, css `?v=navy1`.
- **Fase 3 + Dev Dashboard (di code):** backend `GET/POST /api/stores/{id}/invites` + `POST .../revoke` + `PATCH/DELETE .../members/{membership_id}` (owner/admin only, guard anti-lockout); dashboard menu+view **Kelola Tim**; `register.html?invite=` dukung member; `frontend/dev.html` superadmin only (kelola invite owner, reset password `PUT /api/auth/users/{id}` password-only, log `GET /api/audit` filter action/q, wiring invite×3/member×2/user×5/store.create/register×3). E2E lolos di DB copy (403 non-superadmin OK). Pintu masuk: tombol 🛠️ Dev di view Persetujuan Akun + URL langsung `/frontend/dev.html`. Catatan: `backend/.env` pakai `DATABASE_URL` relatif — jalanin server via `run.bat`/dari `backend/` agar pakai DB asli.
- **DB:** `backend/b_gadget.db` aktif (+`-shm`/`-wal` saat server jalan); backup: `b_gadget.backup-20260918-153454.db`, `b_gadget.backup-20260921-224415.db`, `b_gadget.backup-4b137c6.db`, `b_gadget.backup-pre-multistore.db` (184KB, pre-Fase 1).
- Push selesai (POS1+BOS1+BOS2+BOS3+BOS4+BOS5+BOS6 + 2 feat di antaranya) — repo bersih.

## 5. Gotcha (jangan diulang)
- Ganti `127.0.0.1`→LAN wajib stop server lama dulu (pernah nyangkut 2 proses: parent + orphan `--reload`).
- WiFi **Public** bikin rule firewall Private tidak berlaku → set Private (`Set-NetConnectionProfile`).
- PC ini via hotspot HP "Renee ponsel 4G" — reviewer WAJIB join hotspot yang sama.
- Ganti `script.js` wajib bump `?v=` di `index.html` (sekarang `?v=nota3`, css `?v=navy1`) + hard refresh.
- WA test jangan `081999999999` (itu data asli Fajar Nugroho!) — pakai `08100000000x`.
- Harness bash strip karakter `$` — hindari snippet PowerShell `$_` saat verifikasi.

## 6. NEXT (belum dikerjakan)
- **Uji browser BOS3→BOS6:** profil toko, metode bayar + tab Pembayaran, laporan Harian/Mingguan/Bulanan + export CSV, tema navy di semua halaman, nota digital WA (preview/kirim/cetak) + cetak Thermal 58/80 & A4 + keterangan/kondisi awal.
- Nanti: laporan gabungan owner, paket/billing, root `/` → landing (butuh edit `main.py`).
