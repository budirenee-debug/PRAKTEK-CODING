# HISTORI SESI — POS → Platform BOS SERVICE

> Terakhir update: 30 Sep 2026 (Data Sungguhan — Dummy Dihapus).

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
- **Engine1 (36c78bd):** `engine_logic`-cairkan saat Sudah Diambil + cicil 20% + kuota 2:1 + uang hadir + kas teknisi (buku kas) + oper garansi + nombok 50:50; `POST /engine/check-in`, `/nombok`, `PUT /engine/service/{inv}/part`, `GET /engine/debts`.
- **Owner Space (b91d055):** `login-owner.html` → `owner.html` (10 menu: ringkas/keuangan/pendapatan/bayar/pengeluaran/penjualan/inventori/toko/engine/tim) + switcher toko + `BOSAuth` routing per role.
- **MODUL KEUANGAN — Kecelakaan Kerja + Refund Dana (28 Sep 2026, belum commit):**
  - Tabel baru `work_accidents` (jenis part_rusak/komponen_pelanggan/catatan, kronologi, part pengganti, sumber persediaan/beli_luar, modal, `siapa_bayar` toko/pelanggan, `beban_persen` 0/25/50/75/100, `beban_teknisi`/`beban_toko`/`nota_pelanggan`, status tercatat/selesai) + `refunds` (kode `RFD-YYYYMM-0001`, alasan, nominal, metode, `dari_pendapatan`/`jadi_pengeluaran`, `komisi_dibalik`).
  - Router baru `backend/app/routers/finance.py` → `GET/POST /api/finance/accidents`, `GET /api/finance/accidents/ringkasan`, `POST /api/finance/accidents/{id}/selesai`, `GET/POST /api/finance/refunds`, `GET /api/finance/refunds/ringkasan`. Guard: owner/admin/superadmin saja (403 untuk kasir/teknisi).
  - `GET /api/engine/potongans` (owner/admin) — semua pengurangan buku kas teknisi (`keluar_rp > 0`): `potongan_cicilan` + `refund_balik`; filter `technician_id`/`tipe`; `ringkasan` = total/cicilan/refund/lainnya/jumlah/bulan_ini/sisa_hutang/`per_teknisi` (selalu global, tidak ikut filter).
  - `engine_logic.apply_teknisi_beban()` = satu sumber kebenaran bagi beban teknisi (persen + proteksi junior 1×/bulan + TechDebt + ledger) — dipakai accidents & siap dipakai nombok. `engine_logic.cek_penghasilan_hari_ini()` = omzet cair hari ini (dasar sumber dana refund).
  - Refund: komisi teknisi **dibalik proporsional** (`komisi × nominal/biaya`) via ledger tipe `refund_balik`; sumber dana dari omzet hari ini, sisanya jadi pengeluaran; `tutup_klaim` mengubah service status Garansi → Service Failed + hasil TIDAK + alasan masuk `keterangan`; reply `wa_link` siap dikirim manual.
  - Frontend `owner.html`: menu "Keuangan Teknisi" → "Keuangan" + **3 sub-tab** (`ownKeuTab('kas'|'celaka'|'refund')`): Kas Teknisi / Kecelakaan Kerja (stat 4 kartu + tabel 11 kolom + filter status + modal + pratinjau beban live) / Refund Dana (stat 4 kartu + tabel 12 kolom + tombol WA per baris + modal + pratinjau sumber dana & komisi dibalik).
  - Sub-tab di dalam **Kas Teknisi** (`ownPotonganTab('all'|'kas'|'pot')`): 📊 Semua Teknisi / 📄 Rincian Kas / ✂️ **Potongan**. Panel Potongan: 4 stat (Total Potongan, Cicilan Hutang, Refund Dibalik, Sisa Hutang) + ranking teknisi paling banyak dipotong + filter teknisi/jenis + tabel 7 kolom. Klik baris di Semua Teknisi → langsung pindah ke Rincian Kas teknisi itu (`ownKasOpen`).
  - Kolom **Potongan** ditambahkan di tabel Semua Teknisi. `_kas_summary()` kini mengembalikan `komisi_bruto` / `potongan` / `potongan_refund` / `netto` (lama `total_diterima` tetap untuk backward compat). Identitas: `Komisi (bruto) − Potongan + Hadir = Total`. Penting: `komisi_cair` di ledger **sudah** net dari cicilan (masuk = komisi − potong), jadi `komisi_bruto = komisi_cair + potongan_cicilan` supaya tidak double-count. `engine.js` (Kas Saya + Buku Kas) ikut pakai `netto` + label `refund_balik`; cache-bust `engine.js?v=eng3`.
  - **Data ilustrasi (frontend, bukan DB):** `OWN_DUMMY_KAS` / `OWN_DUMMY_POTONGAN` / `OWN_DUMMY_CELAKA` / `OWN_DUMMY_REFUND` dipakai **hanya saat API mengembalikan kosong** (pola `OWN_DUMMY_SERVICES`), dengan banner kuning "DATA CONTOH (ilustrasi)" per panel (`ownDemoOn/ownDemoOff`). Angka antar panel konsisten: kolom Potongan di tabel Kas == total per teknisi di tab Potongan (Andi 840rb, Sinta 620rb, Rizky 240rb, Budi 370rb, Dimas 98rb = 2.168.000), identity `bruto − potongan + hadir = Total` selalu true, `dari_pendapatan + jadi_pengeluaran = nominal` tiap refund, `beban_teknisi + beban_toko + nota_pelanggan = modal` tiap kecelakaan. Tiap baris ilustrasi diberi `_demo: true` (tidak pernah dikirim ke API).
  - Uji: unit + HTTP `TestClient` pada salinan DB (semua 400/403/404 valid, 50:50, 100%, pelanggan bayar, junior proteksi, ledger refund_balik, tutup klaim, potongans 20% + sisa hutang + filter) — LULUS.
  - Catatan: sisi "jadi pengeluaran" baru dicatat di tabel `refunds` (view **Pengeluaran** masih placeholder, modul `expenses` belum ada).
- **KONTROL — Log Anti-fraud + Kelola Cabang (28 Sep 2026, belum commit):**
  - Kategori menu `TOKO` → **`KONTROL`**; tambah menu **🛡️ Log Anti-fraud** (`view-own-antifraud`) dan sub-tab **🏪 Kelola Cabang** di dalam Kelola Tim (`ownTimTab('tim'|'cabang')`).
  - `GET /api/audit/antifraud` (`routers/audit.py`) — owner/admin/superadmin, **scoped per toko** (403 teknisi/kasir). Klasifikasi otomatis: `POLA` (prefix action → Service/Stok/Engine/Keuangan/WA/Toko/Tim/Akun/Masuk/Sistem/Pelanggan), `LABEL` bahasa manusia, `level` **tinggi** untuk aksi sensitif (`SENSITIF` substring + `SENSITIF_AKSI` eksplisit: hapus, ubah harga, refund, nombok, set_part, settings, `stok.update`, `store.update`, role, password, seed). Filter `level`/`pola`/`actor`/`q`/`since` + `limit`/`offset` (40/halaman). `GET /api/audit` lama tetap superadmin-only (dipakai `dev.html`). `GET /api/audit/antifraud/aksi` = daftar action untuk filter UI.
  - **Pencatatan log baru ditambahkan** (dulu cuma aksi dev): `service.create`, `service.update` / `service.update_harga` (bedakan `biaya` → harga **lama → baru**), `service.status` (lama → baru + diambil_oleh + metode bayar), `service.hapus`, `stok.create`, `stok.update` (stok/harga/harga_beli/nama/keluar), `stok.hapus`.
  - `GET /api/stores/jaringan/ringkasan` (`routers/stores.py`) — ringkasan per cabang untuk Kelola Cabang: anggota/technisi, total service/sukses/proses, omzet total & bulan ini, jumlah part, nilai stok, stok tipis, total refund, kecelakaan kerja. Gate owner/admin/superadmin. Frontend: tabel 10 kolom + 4 stat + modal buat/ubah toko (`ownCabangForm/ownCabangSave/ownCabangBuka`).
  - Uji: E2E di salinan DB — POST/PATCH/PUT/DELETE service & sparepart → 5 log muncul, `service.update_harga` & `stok.update` level **tinggi** ✓, filter pola/actor/q/level benar, 403 teknisi di kedua endpoint. Semuanya LULUS.
  - **Revisi Log Anti-fraud ( padat + simple):** tabel 6 kolom → **daftar div 1 baris = 1 aksi** (`af-list`/`af-row`, grid `44px 20px 1fr auto`, isi: jam · ikon · label + detail (ellipsis 1 baris) + target · pelaku + badge JANGGAL). Pemisah hari (`HARI INI` / `KEMARIN` / `3 HARI LALU` / tanggal), teks penuh di `title=`. Filter jadi 1 baris ringkas (level · pelaku · jenis · sejak · cari · checkbox "hanya janggal"), 3 stat (Total/Janggal/Normal) + pill jumlah. Paginasi 50/baris.
  - **Filter Pelaku bisa "kembali"** (bug yang dilaporkan user): nama pelaku di tiap baris bisa diklik → set filter; chip filter aktif tampil di bawah toolbar dengan tombol **×** per filter + **↺ Hapus semua**; tombol **↺ Reset** di header; chip jenis (pill) toggle on/off; saat hasil kosong muncul pesan "tekan ↺ Hapus semua". Dropdown Pelaku diisi dari `aktor` (backend baru kirim daftar pelaku + jumlah + jumlah janggal).
  - Bug yang ketemu saat uji: chip "Hanya janggal" baca `.value` (checkbox) → harus `.checked`. Diuji Node 27 assertion (mock DOM): pasang/lepas/toggle/reset filter, dropdown, pemisah hari, urutan, empty state — semua OK.
  - **Fix teks ganda di dropdown "Semua jenis"**: di `POLA` (routers/audit.py) field ikon ikut berisi nama (`"🛠 Service"`), sementara frontend menambah nama lagi → tampil `🛠 Service Service (4)`. Sekarang ikon = **emoji saja** (`🛠`, `📦`, `⚙️`, `💸`, `💬`, `🏪`, `👥`, `🔑`, `🔐`, `🧩`, `👤`), nama dirangkai di UI. Ikon `seed` `🛠` → `🧩` (bentrok dengan `service`), `engine` pakai `⚙️` (pakai selector agar tidak muncul kotak kosong). Prefix `alat.*` dipetakan ke pola **Stok** (bukan "Lainnya"). Uji anti-ganda: setiap `ikon` bebas dari nama pola, tiap chip/dropdown nama muncul tepat 1×, tidak ada pola kembar — LULUS.
  - **KELOLA TIM -> digabung jadi 1 tab "👥 Anggota & Kode Undangan" (29 Sep 2026):** sub-tab cuma 2: [Anggota & Kode Undangan] / [🏬 Kelola Cabang]. Panel "Toko & Kode" yang terpisah DIHAPUR (fungsinya kembar) -> digabung ke panel Anggota. Konsep: satu **dropdown toko terpilih** jadi payung - mengubahnya langsung mengganti isi 4 bagian: 4 stat, tabel kode, tabel anggota, dan pratinjau form.
    - Backend baru `GET /api/stores/manage/invites` (`routers/stores.py`) - daftar kode lintas toko yang dikelola user + ringkasan per toko (`total/aktif/terpakai`) + status tiap kode (`aktif`/`terpakai`/`kadaluarsa`) + `sisa_hari` + `link` register. Toko yang tidak dikelola user TIDAK ikut (teknisi dapat 0 toko = tidak ada kebocoran kode).
    - Frontend: form "Buat Kode Undangan" dengan **Toko Tujuan** (dropdown, wajib), peran, masa berlaku, **jumlah kode 1-10** + pratinjau langsung; tabel kode 7 kolom (kode, toko tujuan, peran, status, sisa hari, dipakai oleh, aksi **Salin**/**x batalkan**); filter toko + status; 4 stat (toko, kode aktif, terpakai, total).
    - `ownCopyLink()` menyalin `register.html?invite=KODE` memakai `path.slice(0, path.lastIndexOf('/')+1)`. JANGAN `pathname.replace(/[^/]*$/, '')` - regex itu cocok string kosong di akhir sehingga hasilnya link ngaco `owner.html/frontend/register.html`.
    - Uji: backend 19 assertion (status aktif/terpakai/kadaluarsa, `sisa_hari` negatif utk kadaluarsa, infinity utk tanpa batas, per-toko, urutan aktif dulu, buat kode tertuju ke toko terpilih, revoke, gate teknisi 0 toko) + UI 26 assertion mock DOM (pilih toko -> pratinjau -> buat 1/2/5 kode semua ke toko tujuan, filter, salin link, batal, kode non-aktif tanpa tombol) - SEMUA LULUS.
    - Revisi (29 Sep, docked): dropdown kembar di header (`tkTokoPilih`, sebelah tombol refresh) **DIHAPUS** - sekarang hanya ada 1 dropdown, yaitu **"Toko Tujuan" di dalam form** (label + hint "kode, anggota & stat di bawah ikut toko ini"). `ownTokoGantiToko()` membaca `invToko`, `ownTokoPicked()` memakai `invToko.value` -> `BOSAuth.getActiveStoreId()` sebagai fallback. Judul panel memakai baris konteks `#tkCtxLine` yang menampilkan toko aktif ("Menampilkan B_gadget (Toko Utama)") supaya tidak ambigu.
    - Perubahan: kolom "Toko Tujuan" di tabel kode DIHAPUS (sudah implicit dari dropdown), dropdown `tkTokoPilih` jadi kontrol utama, `ownTeam()` kini memakai toko terpilih (`ownTokoPicked()`) bukan toko aktif, fungsi lama `ownCreateInvite()` dihapus, stat "Toko Tucked" diganti "Anggota Toko Ini" (backend `manage_invites` kirim `jumlah_anggota` per toko). Tab 1 = stat 4 kartu -> form buat kode -> tabel kode -> tabel anggota.

- **TEMA SIDEBAR HITAM ELEGANT (29 Sep 2026):** `style.css` blok `/* SIDEBAR */` diganti total dari navy `#010142` ke hitam elegan. Cache-bust `style.css?v=black1` di `index.html`, `owner.html`, `login.html`, `login-owner.html` (DILARANG lupa, gotcha di bawah). Override inline `owner.html` (`.menu-item.active` navy -> putih, select toko `#1b1d1f` -> `#131316`) ikut disesuaikan.
  - Warna: background `linear-gradient(180deg,#0c0c0e,#060607 55%,#030304)` + `border-right:#17171a` + shadow lembut + garis highlight 2px di atas. Menu aktif = **putam `#fafafa` dengan teks hitam** (kontras 18.96:1), ikon menu = `#c9c9d0`, kategori `#7c7c85`, brand icon gradien putih, scrollbar `#2e2e33`, user-card/btn-logout/badge/select semua greyscale gelap.
  - Hover TIDAK lagi `scale(1.02)` (menu bergoyang saat hover) - jadi `translateX(3px)` + background halus saja, lebih elegan & tidak bikin pusing.
  - Kontras diuji (Node, WCAG): teks menu 11.27:1, ikon 11.86:1, kategori 4.73:1, store-info 3.87:1, bagian bawah 11.88:1 - semua lolos ambang.
## 5. Gotcha (jangan diulang)
- Ganti `127.0.0.1`→LAN wajib stop server lama dulu (pernah nyangkut 2 proses: parent + orphan `--reload`).
- WiFi **Public** bikin rule firewall Private tidak berlaku → set Private (`Set-NetConnectionProfile`).
- PC ini via hotspot HP "Renee ponsel 4G" — reviewer WAJIB join hotspot yang sama.
- Ganti `script.js` wajib bump `?v=` di `index.html` (sekarang `?v=nota3`, css `?v=navy1`) + hard refresh.
- WA test jangan `081999999999` (itu data asli Fajar Nugroho!) — pakai `08100000000x`.
- Harness bash strip karakter `$` — hindari snippet PowerShell `$_` saat verifikasi.
- **JANGAN** sunting file ini (`.html`/`.js`/`.md`) lewat `Get-Content -Raw` + `[System.IO.File]::WriteAllText` — PS 5.1 baca sebagai ANSI lalu tulis UTF-8 → semua emoji/— jadi rusak (pernah ruin 661 baris di `owner.html`; balikin dengan `git checkout --`). Pakai tool edit saja. Untuk baca dari shell: `[System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)`.
- Snapshot nilai **lama** di endpoint PATCH/PUT harus diambil **sebelum** call crud (objek ORM sama, jadi sesudah update selalu sama → diff kosong, log tidak pernah tertulis).
- Kalau hasil test "aneh" (filter mengembalikan 0 padahal data ada), cek dulu **huruf e yang hilang** di string query test (mis. `pola=Kuangan`), bukan blamed backend. Bandingkan `repr()` atau `[hex(ord(c)) for c in s]`.

## 5b. LAPORAN PINDAH TOKO → OWNER (29 Sep 2026, belum commit)
- Dashboard toko (`index.html`): kategori LAPORAN dihapus dari sidebar (laporan-service/teknisi/penjualan). `Kas Saya` tetap di toko (pindah ke grup TRANSAKSI) untuk teknisi personal. Stat Estimasi Pendapatan kini → `transaksi-pendapatan` (dulu `laporan-penjualan`). `script.js?v=ambil11`.
- Deep-link lama `switchView('laporan-*')` otomatis redirect ke `owner.html#laporan` (tidak blank). Section laporan lama di `index.html` diberi banner "Pindah ke Owner Space" sebagai arsip kompatibilitas.
- Dashboard owner (`owner.html`): menu baru **📊 Laporan** (kategori LAPORAN) + `view-own-laporan` 3 sub-tab: 📄 Service (Masuk/Sukses/Failed/Garansi per Harian/Mingguan/Bulanan + export CSV — pindahan toko, melengkapi Ringkasan harian + Pendapatan nominal), 👷 Teknisi (Handle/Sukses/Failed/Rating — melengkapi Performa Ringkasan + rincian Kas di Keuangan), 📊 Penjualan (total cair + sparepart terlaris — melengkapi Pendapatan+Bayar+Penjualan). Fungsi `ownLaporan/ownLapService/ownLapTeknisi/ownLapJual/ownLapSvcCSV`, loader di `ownShow` + `ownLoadAll`, deep-link `#laporan` di guard.
- Data lewat `ownServices()` (cache + dummy DEMO) + `GET /inventory/spareparts` — pola sama seperti Ringkasan. Uji: `node --check` script.js + inline owner LULUS; semua ID view/tbody/stat terverifikasi ada.

## 5c. KAS TOKO + SUPERADMIN → KONTROL (29 Sep 2026, belum commit)
- **Kas Saya → 🏪 Kas Toko** (`index.html` TRANSAKSI, `script.js?v=ambil12`, `engine.js?v=eng4`): menu ganti nama; view jadi 2 sub-tab — 🏪 Arus Toko (owner/admin: 3 stat Total Masuk / Total Keluar / Sisa Kas + tabel riwayat gabungan max 120 baris, Masuk = cair bruto, Keluar = komisi+hadir teknisi + refund nominal + beban toko celaka, Sisa = Masuk−Keluar; sumber `/services` + `/engine/kas/teknisi/{id}` + `/finance/refunds` + `/finance/accidents`, semua try/catch 403) dan 👤 Kas Saya (personal, fungsi lama `renderKasSaya` utuh). Teknisi otomatis ke Kas Saya + tab Arus Toko disembunyikan (pola Buku Kas). Gotcha: refund dihitung nominal penuh (dari omzet + jadi pengeluaran) supaya tidak double-count lawan bruto.
- **SUPERADMIN gabung Kontrol Owner**: sidebar toko bersih (kategori SUPERADMIN + menu approval dihapus; `refreshPendingBadge` null-safe, bell/banner tetap → redirect). `switchView('approval-akun')` → `owner.html#approval`. Owner: menu ✅ Persetujuan Akun di KONTROL (khusus superadmin, `menu-approval-own` di-hide untuk owner/admin di guard) + `view-own-approval` (tabel pending + semua user + modal edit, ID baru `tbodyOwnApproval/...`) + fungsi `ownApproval/ownApproveUser/ownRejectUser/ownToggleFreeze/ownDeleteUser/ownOpenEditUser` via `ownFetch` (`/auth/pending|/users|/approve|/reject|/toggle`, PUT/DELETE users). Loader di `ownShow` + `ownLoadAll`, deep-link `#approval`.
- Uji: 19 assertion ID/fungsi OK + `node --check` script.js/engine.js/inline owner LULUS.

## 5d. MODUL PENGELUARAN + LABA-RUGI (29 Sep 2026, belum commit)
- **Backend** (`models.py` + `routers/finance.py`, tabel auto-create via `create_all`, tanpa migrasi): tabel `expenses` (tanggal/kategori/keperluan/nominal/metode/keterangan/dibuat_oleh, scope `store_id`). Endpoint `GET /finance/expenses` (filter kategori/since), `GET /finance/expenses/ringkasan` (hari/bulan/total + per_kategori), `POST` (validasi keperluan/nominal/kategori 7 macam/metode), `DELETE` (salah input). Baca: owner/admin/kasir/superadmin (kasir baca agar Kas Toko jujur, teknisi 403); tulis: owner/admin/superadmin. Audit `finance.expense` + `finance.expense_hapus` (masuk Log Anti-fraud pola Keuangan). Uji TestClient di DB temp: 12/12 LULUS (401/400/404/CRUD/ringkasan).
- **Owner** (`owner.html`): view Pengeluaran 100% real — stat Hari/Bulan/Total + chip per kategori + filter + tabel (aksi hapus) + modal + Catat Keluar (preview live). Kartu **Laba-Rugi Sederhana** (`ownLaba`): Omzet cair − komisi − hadir − refund − beban toko celaka − pengeluaran = laba bersih (hari + bulan, merah jika minus). Ringkasan `outHari` kini real (dulu hardcode Rp275rb).
- **Kas Toko** (`engine.js?v=eng5`): Total Keluar + riwayat ikut `🧾 Pengeluaran` dari `/finance/expenses` (try/catch, kasir bisa baca). Rumus Sisa Kas tetap konsisten (bruto − semua keluar).
- Catatan: refund `jadi_pengeluaran` masih angka di tabel refunds (belum auto-jadi baris expenses — disengaja, agar tidak double-count; Laba-Rugi hitung refund dari nominal).

## 5e. KASIR PENJUALAN + STRUK SIMPLE (29 Sep 2026, belum commit)
- **Keputusan:** asesories masuk aplikasi ini (kategori Aksesoris di tabel `spareparts`), tidak pisah aplikasi — stok satu kebenaran + profit otomatis (jual−beli).
- **Backend** (`models.py` Sale/SaleItem + `routers/sales.py` prefix `/sales`, daftar di `main.py`, auto-create): `POST /sales` (item barang: harga ikut master anti-markup + cek stok → 400 jika kurang, potong stok/keluar; item jasa: nama+harga manual; kode `JL-YYYYMM-XXXX`), `GET /sales`, `GET /sales/ringkasan` (omzet/profit/hari/bulan/per_metode/terlaris), `DELETE` void (stok balik + audit `sale.create`/`sale.void` pola Keuangan). Guard: owner/admin/kasir (teknisi 403). Uji TestClient DB temp: 16/16 LULUS — termasuk bug FK void yang ketemu saat uji (item harus kehapus+flush dulu sebelum struk, sudah fix).
- **Toko** (`index.html` + `script.js?v=ambil13`): tab Penjualan mati → **kasir beneran** (cari barang + tombol +, jasa manual, keranjang qty +/−, pelanggan opsional, metode, total, Simpan → modal **struk simple** monospace + 🖨 Cetak via jendela print). Struk hari ini + refresh otomatis. Teknisi tetap diblokir (kasir only).
- **Owner:** Penjualan proxy gudang → real (omzet hari/bulan, profit, tabel struk + Void, terlaris dari `/sales/ringkasan`). Laporan → Penjualan ikut real (total service+barang, struk terbaru). **Kas Toko** (`engine.js?v=eng6`): Masuk +🛒 omzet barang. **Laba-Rugi**: baris baru ➕ Profit barang/jasa.
- Konsistensi: HPP barang tidak dipotong dobel (keluar saat belanja via Pengeluaran, profit dihitung jual−beli).

## 5f. VIEW ASESORIES PISAH (29 Sep 2026, belum commit)
- Dashboard toko: menu baru **🎧 Asesories** (INVENTORY) + `view-inventory-asesoris` — tabel sendiri (Nama/Merk/Stok badge/Nilai/Harga, search, count, warning tipis, summary nilai) tapi **data sama** (`inventory` array, filter `kategori==='Aksesoris'`). Aksi per baris: 🛒 Jual (loncat ke Kasir + masuk keranjang), ✎ Edit (modal sparepart yang sama), 🗑 Hapus. + Tambah Asesories (form tambah dengan kategori terpreset Aksesoris; sukses tambah balik ke view ini). Teknisi: read-only (tanpa tombol, ikut pola Sparepart).
- Sinkron dua arah: edit/hapus/tambah/reset di mana pun me-render ulang kedua view (`renderAsesoris` dipanggil di save/delete/submit/reset + redirect tambah). Tanpa ID ganda (view Asesories tanpa input inline).
- Owner: tombol 🎧 Asesories di toolbar Inventori = toggle filter kategori Aksesoris (data tetap satu tabel).
- `script.js?v=ambil14`. Verifikasi 7 cek + `node --check` LULUS.

## 5g. MERK ASESORIES SENDIRI (29 Sep 2026, belum commit)
- Daftar merk asesories: ROBOT, OLIKE, BASEUS, ANKER, UNEED, KAKU, HIPPO, ORIGINAL, GENERIC, LAIN (bukan merk HP).
- **Backend** (`schemas.py` + `crud.py` create/update): allowlist dibuka untuk 9 merk asesories. Gotcha yang ketemu saat uji: validator schema lolos tapi `crud` memaksa jadi LAIN (2 daftar terpisah) — keduanya disamakan. Uji TestClient: ROBOT tersimpan, IPHONE tetap, merk ngaco tetap LAIN, jual ROBOT via kasir OK (4/4).
- **Toko** (`script.js?v=ambil15`): `MERK_ACC` + `merkListFor/fillMerkOptions` — dropdown merk di form Tambah & modal Edit **otomatis ganti isi ikut kategori** (Aksesoris → merk asesories, lainnya → merk HP), placeholder aman. Badge warna sendiri per merk. Filter merk + kategori di Sparepart ikut lengkap (termasuk Aksesoris yang dulu absen).
- **Owner:** `O_MERK_ACC` + `oMerkFill`, modal tambah/edit ikut dinamis, filter merk + badge ikut 9 merk baru.
- Verifikasi 8 cek + `node --check` + compile LULUS.

## 5h. MERK BEBAS KETIK (29 Sep 2026, belum commit)
- Dropdown merk diganti **input bebas + saran** (datalist): ketik apa pun bisa (maks 40 huruf, otomatis kapital), saran mengikuti kategori (Aksesoris → Robot/Olike/dll, lainnya → merk HP). Berlaku form Tambah + modal Edit, toko + Owner.
- **Backend** (`schemas.py` + `crud.py`): allowlist dihapus total (sebelumnya 2 lapis: schema + crud) — hanya rapikan huruf. Uji: merk bebas tersimpan, update bebas, jual via kasir OK (3/3).
- Filter merk dropdown tetap (opsi umum + 9 merk asesories); merk bebas di luar itu ketemu via search. Badge merk baru tampil abu-abu netral.
- `script.js?v=ambil16`. Verifikasi 8 cek + `node --check` + compile LULUS.

## 5i. AUDIT OTORITAS PER ROLE (29 Sep 2026, belum commit)
- Temuan 4 lubang, semua ditutup + diuji 14/14 TestClient (user owner/kasir/teknisi beneran + membership):
  1. Teknisi bisa tulis stok via API (tombol UI sembunyi tapi backend lolos) → `inventory.py` tambah `_toko_writer` (superadmin/owner/admin/kasir) di create/update sparepart+alat. Teknisi stok 403, kasir 201/200.
  2. Teknisi bisa lompat status langsung Sudah Diambil (= cair komisi, bypass alur kasir) → `services.py` `TERMINAL_STATUS` (Bisa Diambil/Sudah Diambil/Sukses/Selesai/Failed/Garansi) 403 untuk teknisi di PUT + PATCH. Operasional (Dikerjakan dll) tetap 200.
  3. Teknisi bisa ubah harga service → PATCH `biaya` 403 untuk teknisi (harga milik kasir/owner).
  4. Owner tidak bisa hapus stok (backend superadmin-only padahal tombol ada di Owner) → DELETE sparepart/alat dibuka untuk owner/admin (scope toko sendiri). Teknisi hapus tetap 403.
- Pengecualian disengaja: teknisi boleh ubah **peminjam** alat (pinjam/kembali, kondisi ikut otomatis) — backend hanya terima key peminjam; UI Alat teknisi: semua dikunci kecuali dropdown peminjam + tombol 📌 Pinjam. Sparepart teknisi full read-only (pakai via Proses Service).
- Frontend (`script.js?v=ambil17`): input stok disabled + tombol aksi disembunyikan untuk teknisi (sparepart/alat), guard console di semua fungsi tulis.
- Yang sudah benar (tidak diubah): superadmin full; register legacy tanpa owner; owner/admin kelola tim + engine + finance tulis; kasir kasir+status+stok; teknisi own-scope + kas saya + check-in; dev.html superadmin-only; track publik aman.
- Verifikasi: guard 14/14 + `node --check` + compile LULUS.

## 5j. NOTA MODERN (29 Sep 2026, belum commit)
- `buildNotaHTML` ditulis ulang (masuk + ambil): kop ◈ tegas, garis ganda, badge pill status (TANDA TERIMA / PENGAMBILAN • LUNAS), baris label redup + nilai tebal, **total box** berbingkai, footer terstruktur. Semua inline style (aman cetak thermal 58/80 + A4). Isi data & template WA tidak diubah.
- Preview modal: `<pre>` teks polos → render HTML asli (WYSIWYG, yang dilihat = yang tercetak). Tombol Ukuran/Cetak/WA tetap.
- `script.js?v=ambil18`. Uji: render masuk+ambil 7/7 (kop/badge/total/lacak/tanpa undefined) + `node --check` LULUS.
- Revisi: baris **Teknisi dihapus dari nota pengambilan** (cetak + template WA default frontend & backend; nota masuk tetap ada). Template custom toko yang sudah tersimpan tidak ikut berubah — hapus manual di Pengaturan → Template WA bila perlu. `script.js?v=ambil19`.
- Revisi font: nota + struk ikut font mockup TUSER — monospace (`Courier New`) dibuang, semua ukuran (58/80/A4) + struk kasir + preview pakai Inter/system sans. CSS `?v=black2` (4 halaman), `script.js?v=ambil20`.

## 5k. FIX KAS TOKO STALE (29 Sep 2026, belum commit)
- Laporan user: struk baru tidak masuk Kas Toko. Penyebab: `renderKasToko` pakai cache `dataset.filled` — sekali dibuka tidak hitung ulang. Fix: cache dihapus, Kas Toko selalu hitung ulang tiap dibuka (ikut pola view lain). `engine.js?v=eng7`.

## 5l. DATA SUNGGUHAN — DUMMY DIHAPUS (30 Sep 2026, belum commit)
- **DB** (`b_gadget.db`, backup `b_gadget.backup-pre-real-20260930-013952.db`): hapus 123 service (+engine), 112 customer, 42 sparepart, 18 alat, 1 struk test, 20 audit log, teknisi seed (Andi/Sinta/Budi/superadmin-nonaktif). **Pertahankan:** 6 user, 2 toko, 6 membership, 3 invite, settings. Teknisi tersisa: ANGDEDI + TOLE (asli).
- **Kode:** `OWN_DUMMY_*` Owner dimatikan via flag `REAL_ONLY` (8 titik: ringkas/sparepart/services/kas/potongan/celaka/refund/cabang) → kosong tampil "belum ada data". `defaultData` toko = []. Fallback teknisi Andi/Sinta/Budi dihapus (backend `available-technicians` + `loadAvailableTechs` + penerima + laporan-teknisi). Estimasi dashboard hardcode Rp 2,85jt → real (pipeline aktif + id `stat-estimasi`).
- **Kunci lokal baru** (`_v1`→`_v2`: data/inventory/pemakaian-sparepart/alat) agar sisa test di browser tidak muncul lagi.
- Uji: DB nol + smoke API real 5/5 (login, services [], techs tanpa Andi, ringkasan nol) + `node --check` LULUS.
- Siap terima CSV user (format dibahas berikutnya).

## 5m. KODE TOKO BISA DIGANTI (30 Sep 2026, belum commit)
- Kode toko (prefix nomor nota) dibuka: validasi 2-5 huruf/angka, unik antar toko. Nota lama tidak berubah (tersimpan), nota baru ikut kode baru. Berlaku di Pengaturan Toko + Profil Toko Owner. `script.js?v=ambil22`.
- Uji: kode spasi ditolak, ganti TST → nota `TST-2026-0001` ✓, kembalikan BGJ ✓ + `node --check` LULUS.

## 5n. PONDASI PEMBUKUAN MENTOR — KATEGORI A-G + BUKU BESAR + TUTUP KAS (4 Okt 2026, belum commit)
- **Sumber:** `konsep pembukuan toko.docx` (SATU pembukuan, aliran dibedakan fungsi; Omzet ≠ uang tersedia ≠ laba; 5 angka; tutup kas harian; kas kecil).
- **Backend** (`ledger_meta.py` baru = single source kategori): A1-A4 omzet, B1-B3 HPP, C1-C6 operasional, D aset, E1 modal/E2 prive, F1 transfer/F2 hutang/F3 DP, G media (kas_utama/kas_kecil/bank/qris). Validasi: F1 wajib transfer + beda media (bukan omzet), E1 masuk, E2 keluar, DP bukan omzet.
- **Model** (`models.py`): `LedgerEntry` (tanggal/jenis/kategori/nominal/media + ref dual-write), `CashClose` (sistem vs fisik per media + selisih), `CashConfig` (limit kas kecil, default Rp500rb). Auto-create via `create_all`, tanpa migrasi.
- **Endpoint** (`routers/finance.py`): `GET /finance/kategori` (dropdown frontend), `GET/POST/DELETE /finance/ledger` (manual; hapus auto ditolak), `GET /finance/ledger/ringkasan` (omzet−HPP=laba kotor−operasional=laba bersih + per-media), `GET/PUT /finance/cash/config`, `GET/POST /finance/cash/close` (selisih target Rp0, kasir boleh tutup).
- **Dual-write:** expense → B1/C1-C4 + income → E1/A4 otomatis masuk ledger (media dari metode bayar); hapus sumber ikut hapus baris ledger. Data lama tidak diubah.
- **Uji:** TestClient DB temp 26/26 LULUS (validasi, dual-write, hapus guard, ringkasan, config, tutup kas).
- **Berikutnya:** UI Transaksi Pusat + Tutup Kas (baca `/finance/kategori`), auto-posting service/sales ke ledger, limit kas kecil final owner.

## 5o. HUB KEUANGAN SATU ALUR MENTOR (4 Okt 2026, belum commit)
- Menu mencar (Pendapatan Sukses/Pembayaran/Pengeluaran/Buku Besar/Tutup Kas) disembunyikan → lebur ke **Keuangan** 6 sub-tab: 📊 Arus (5 angka via `ownArus` cache) • 💰 Pendapatan (service cair + refund) • 🧾 HPP & Komisi (kas teknisi + celaka) • 🏪 Operasional (pengeluaran + laba) • 💳 Kas (metode + tutup kas) • 📒 Buku Besar.
- Teknik: panel lama **dipindah DOM** (`ownHubMove`, class `view` dilepas) — tanpa duplikat kode/fungsi, loader lama dipakai ulang. `ownKeuTab` lama dihapus. `ownLoadAll` + `ownBuku/ownClose`.
- Uji: ID hub lengkap + inline `node --check` LULUS.

## 5p. HUB 7 TAB MENTOR + EXPENSE KODE MENTOR (4 Okt 2026, belum commit)
- Keuangan → 8 sub-tab: 💰 Pendapatan (union service cair + kasir barang/jasa + lain + refund, filter A1-A4) • 🧾 HPP & Komisi (panel kas teknisi + B1/B2/B3 buku besar + insiden) • 🏪 Operasional (C1-C6 + panel pengeluaran) • 🏗 Aset (sub Aset/Investasi) • 👑 Owner (E1/E2) • 🔁 Non-Biaya (F1/F2/F3) • 💳 Kas & Media (saldo per media + bayar + tutup kas) • 📒 Buku Besar. Tab Arus dihapus (indikator sehat jadi tab lain nanti).
- Backend: `ledger.subkategori` + migrasi ALTER, expense terima kode mentor (B1/B2/C1-C6/D, nama lama kompatibel), filter kategori ikut memetakan lama→kode, `POST /ledger` + expense D wajib subkategori, `GET /ledger?subkategori=`.
- Form Pengeluaran (owner + toko Kas Toko) ganti dropdown ke kode mentor + Jenis D; preview tulis tujuan HPP/Operasional/Aset; Kas Toko ikut nampil kode.
- Uji: backend 35/35 + inline `node --check` LULUS. Unit (A3/B3) + aset masih kosong jujur (modul menyusul, bisa Catat Manual).

## 5q. GRUP MENTOR JADI MENU UTAMA (4 Okt 2026, belum commit)
- Protes user benar: grup (HPP/operasional/aset/...) jangan jadi sub-tab. Sidebar KEUANGAN kini 8 menu utama: Pendapatan, HPP & Komisi, Operasional, Aset, Owner, Non-Biaya, Kas & Media, Buku Besar — via `ownShowKeu()` + judul per grup + highlight tepat. Baris sub-tab hub dihapus; sub-tab dalam grup (A1-A4, C1-C6, dll) tetap sebagai filter.
- Uji: 8 menu + 8 panel + nav OK, inline `node --check` LULUS.

## 5r. PRINSIP MENTOR DIKUNCI: BELI=PERSEDIAAN, JUAL/PAKAI=HPP (4 Okt 2026, belum commit)
- Audit menemukan 5 lubang: belanja langsung HPP + tanpa stok; jual tanpa posting buku; pakai part tanpa HPP di mana pun; sukses tanpa omzet/HPP jasa; refund hanya koreksi layar.
- Ledger +2 flag: `masuk_laba` (belanja B = persediaan, HPP saat terjual/terpakai) + `pengaruh_kas` (HPP tanpa gerak kas, media `stok`). Migrasi ALTER + backfill expense-B lama → persediaan.
- Auto-post (idempoten, anti-gagal): jual → omzet + HPP barang; Sukses → omzet jasa + komisi (HPP); pakai part → HPP modal; refund → pengurang omzet; void/batal hapus barisnya.
- Belanja B1/B2 opsional ➕ tambah stok (mutasi `beli`) — form owner + toko.
- UI: badge 📦 Persediaan di tab HPP + kartu HPP-only (persediaan di sub), Buku Besar tampil subkategori.
- Uji: TestClient 50/50 (stok 8−1+5=12, HPP=komisi+part+sale, kas tidak ganda).

## 5s. AUDIT + FIX ALIRAN UANG MENTOR (6 Okt 2026)
- Audit backend+frontend vs `ledger_meta.py`: 8 menu Owner + Kas Toko + Laba-Rugi dipetakan ke endpoint (lihat laporan sesi).
- **BUG HPP kasir (berat, SUDAH FIX):** `sales.py:190` HPP=(jual−beli)×qty = profit! Fix → `beli×qty` (modal). Terbukti TestClient: jual 145rb/beli 100rb → dulu HPP 45rb (laba kotor 100rb), sekarang HPP 100rb (laba 45rb). Catatan: uji 50/50 §5r ikut mengabadikan rumus salah — jangan pakai sebagai acuan.
- **Uang hadir → C1 (FIX):** `engine.py check-in` kini auto-post `C1 keluar/kas_utama` ref `(allowance, attendance.id)` idempoten. Dulu cuma buku teknisi → laba + saldo kas kegedean.
- **Beban toko celaka → B1 (FIX):** `finance.py create_accident` auto-post beban_toko ref `(accident, id)`; beli_luar=kas keluar, persediaan=media stok non-kas.
- **Backfill produksi (sekali, idempoten):** backup `b_gadget.backup-pre-ledger-backfill-20261006-*.db`; 2 sale (omzet A2 175rb; HPP Rp0 karena harga_beli tak tercatat) + 6 service Sukses (A1 1,23jt + komisi B1 514,5rb) + 1 expense + 1 income. Buku: 1 → 17 baris; ringkasan omzet 1.405.000 / HPP 654.500 / persediaan 135.000 / modal 125.000 / laba 750.500. Attendances & accidents produksi = 0 (tak ada yang perlu backfill).
- **Kas Toko vs refund (FIX minimal):** `engine.js?v=eng8` — refund yang servicenya sudah Failed (tutup klaim) kini dikompensasi baris penerimaan awalnya, net = porsi ditahan (biaya−refund).
- **Guard manual stok (FIX):** `POST /ledger` media=stok dipaksa `pengaruh_kas=False` (opsi 7).
- **Tidak diubah (keputusan):** komisi service refund tetap penuh di B1 (kas sudah keluar; baliknya via cicilan) — tanya mentor bila mau dibalik proporsional. Data lama harga_beli=0 semua (5 sparepart + 2 struk + 3 part terpakai) → HPP Rp0, wajib isi harga beli master ke depan.
- Tab Operasional: label sub-tab C1–C6 dibersihkan (Gaji/Tempat/Internet/Harian/Marketing/Maintenance), kode tetap di dalam.
- Uji: TestClient DB temp 16/16 LULUS (sale, allowance±idempoten, celaka kas+stok, manual stok, service penuh A1/komisi/part, ringkasan konsisten) + `node --check engine.js` OK.

## 6. NEXT (belum dikerjakan)
- **Uji browser BOS3→BOS6:** profil toko, metode bayar + tab Pembayaran, laporan Harian/Mingguan/Bulanan + export CSV, tema navy di semua halaman, nota digital WA (preview/kirim/cetak) + cetak Thermal 58/80 & A4 + keterangan/kondisi awal.
- Nanti: laporan gabungan owner, paket/billing, root `/` → landing (butuh edit `main.py`).
