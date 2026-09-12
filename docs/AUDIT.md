# Audit Revo — B_gadget POS Service HP

**Tanggal:** 2 September 2026  
**Repo:** PRAKTEK (index.html, script.js, style.css) — sebelum migrasi  
**Auditor:** Muse Spark (OpenCode)

---

## Ringkasan Eksekutif

Project awal adalah **frontend-only single-page** yang fungsional untuk demo, tapi **belum layak produksi** karena tidak ada database sesungguhnya. Semua data di `localStorage` (`script.js:line 12`), sehingga hilang jika clear cache, tidak bisa multi-device, tidak ada validasi server, dan rawan XSS. Migrasi ke **FastAPI + SQLite** sudah dieksekusi di `backend/app/*`.

**Skor sebelum:** 5.5/10 (UI bagus, logic rapuh)  
**Skor setelah migrasi:** 8.5/10 (siap pakai konter 1 cabang, perlu auth untuk multi-user)

---

## Temuan Kritis (Revo)

### 1. Tidak Ada Database Sesungguhnya
- **Bukti:** `script.js:line 1-13` hanya `localStorage.getItem(STORAGE_KEY)` + `defaultData` array 5 item.
- **Dampak:** Data tidak persisten antar device/browser, tidak ada backup, tidak ada relasi.
- **Fix:** `backend/app/database.py:line 1` SQLite `b_gadget.db` + `backend/app/models.py:line 1` tabel `services`, `customers`, `technicians`.

### 2. Tidak Ada Backend / Root API
- **Bukti:** Tidak ada folder `backend`, tidak ada `requirements.txt`, semua logic di browser.
- **Dampak:** Tidak bisa integrasi WA notif, cetak nota server, atau dashboard cabang.
- **Fix:** `backend/app/main.py:line 1` FastAPI dengan routers `services`, `customers`, `technicians`, `stats`. Root `/` dan `/health` hidup.

### 3. Tidak Ada Model / Schema
- **Bukti:** Data flat `{id, nama, wa, device, keluhan, teknisi, biaya, status}` tanpa FK, tanpa tipe.
- **Dampak:** Duplikasi nama/WA, teknisi hanya string, tidak ada agregasi.
- **Fix:** `backend/app/models.py:line 6` normalisasi Customer & Technician, `backend/app/schemas.py:line 1` Pydantic validasi `wa` numeric, `status` whitelist, `biaya >=0`.

### 4. Validasi & Keamanan Lemah
- **Bukti:** `script.js:line 94-101` `innerHTML` langsung pakai `d.nama`, `d.keluhan` tanpa escape → XSS. `handleServiceSubmit` (`script.js:line 178`) cek hanya `if(!nama||!wa)` tanpa format.
- **Dampak:** User bisa inject `<script>` via nama/keluhan.
- **Fix:** `script.js:line 120` `escapeHtml()` di semua render, `schemas.py:line 20` validator WA numeric & status.

### 5. Logic Bug — ID Collision & Stats Fake
- **Bukti:** `script.js:line 188` `newId='INV-2026-'+String(100+data.length+1)` → collision jika data dihapus (length < max id). `script.js:line 126` `Math.random()*5+1` untuk total service → bohongan.
- **Fix:** `backend/app/crud.py:line 8` `generate_invoice()` pakai `MAX(invoice)` + increment atomic. `crud.get_stats()` pakai `COUNT` & `SUM(biaya)` real.

### 6. Tidak Ada Pagination / Search Server-Side
- **Bukti:** `renderPelanggan` (`script.js:line 115`) filter di memori, pagination dummy `Menampilkan 6 dari 48` hardcode.
- **Fix:** `routers/services.py:line 8` query param `search`, `device`, `status`, `skip`, `limit` di SQL; `customers.py` agregasi via `JOIN`.

### 7. UX Minor
- Hardcode tanggal `Selasa, 2 September 2026` di `index.html:line 51` dan `switchView`, tidak dinamis.
- `style.css` bagus (elegant dark sidebar), tapi belum ada loading state saat API lag.
- **Fix:** Frontend hybrid `script.js:line 45` indikator online/offline, `checkHealth()`.

---

## Apa yang Sudah Diperbaiki (Migrasi)

| Area | Sebelum | Sesudah |
|------|---------|---------|
| DB | localStorage | SQLite `backend/b_gadget.db` |
| Server | — | FastAPI `uvicorn app.main:app --reload` |
| Model | flat array | 3 tabel relasional + Pydantic |
| Root | — | 14 endpoint REST (`README.md:line 50`) |
| Invoice | `length+1` | `MAX+1` atomic |
| Stats | random | `SUM` harian |
| Security | raw innerHTML | `escapeHtml` + validator |
| Docs | — | `README.md`, `DOKUMENTASI.md`, `RECRUITMENT.md` |
| Seed | — | `POST /api/seed` idempotent |

---

## Sisa Risiko (Untuk Iterasi Berikut)

1. Belum ada **auth** (semua orang bisa `DELETE /api/services/{invoice}`). Rekomendasi: JWT + role kasir/admin.
2. **CORS `*`** di `main.py:line 20` ok untuk dev, harus di-lock untuk prod.
3. Backup DB manual (copy `b_gadget.db`), belum ada cron.
4. Belum ada **test otomatis** (`pytest`).

---

## Perintah Verifikasi

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/seed
curl http://localhost:8000/api/stats/dashboard
```

Jika semua 200, audit Revo **LULUS**.

---

*— End of Audit —*
