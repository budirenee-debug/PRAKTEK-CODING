# Dokumentasi B_gadget POS Service HP — FastAPI + SQLite

> Versi 1.0 Elegant — 2 September 2026

---

## 1. Tujuan
Migrasi dari **frontend-only localStorage** ke **database sesungguhnya (SQLite)** dengan **FastAPI server**, dengan root & model yang proper, siap untuk scale ke multi-cabang & multi-user.

---

## 2. Arsitektur

```
Browser (index.html + script.js)
   │ fetch /api/*  (JSON)
   ▼
FastAPI (app/main.py) ──► Routers (/api/services, /api/customers, /api/technicians, /api/stats)
   │                     ──► CRUD (app/crud.py)
   ▼
SQLAlchemy ORM (app/models.py)
   │
SQLite (backend/b_gadget.db)
```

- **Frontend** hybrid: coba `API_BASE` dulu, jika gagal fallback `localStorage`. Indikator di sidebar: `● Sistem Online (API)` / `● Offline (localStorage)`.
- **Backend** stateless, CORS open dev.

---

## 3. Model & Schema

### 3.1 `models.py:line 1`

#### Technician
| Field | Type | Ket |
|-------|------|-----|
| id | Integer PK | auto |
| nama | String(100) unique | Andi, Sinta, Budi |
| foto | String(255) | URL pravatar |
| is_active | Integer | 1 aktif |
| created_at | DateTime | auto |

#### Customer
| Field | Type | Ket |
|-------|------|-----|
| id | Integer PK | auto |
| nama | String(120) | index |
| wa | String(20) unique | validasi numeric |
| created_at | DateTime | |
| updated_at | DateTime | on update |

#### Service
| Field | Type | Ket |
|-------|------|-----|
| invoice | String(20) PK | `INV-YYYY-XXXX`, generate atomic |
| customer_id | FK customers.id | upsert by WA |
| technician_id | FK technicians.id | nullable |
| nama | String(120) | denormalized (cepat) |
| wa | String(20) | index |
| device | String(120) | ex: iPhone 11 64GB |
| imei | String(30) nullable | opsional |
| keluhan | Text | wajib min 5 char |
| kelengkapan | Text (JSON string) | `["HP Saja","+ Charger"]` |
| biaya | Integer | default 0, ge 0 |
| teknisi | String(100) | denormalized nama teknisi |
| status | String(30) index | `Antri|Dikerjakan|Menunggu Sparepart|Selesai|Dibatalkan` |
| date | Date | default today |
| estimasi_selesai | Date nullable | dari form |
| created_at/updated_at | DateTime | |

**Relasi:** `Customer 1—* Service`, `Technician 1—* Service`.

### 3.2 `schemas.py:line 1` (Pydantic)

- Validasi `wa` harus numeric, `status` whitelist, `biaya >=0`, `kelengkapan` list → disimpan JSON.
- `ServiceOut` punya validator `kelengkapan` yang parse JSON string ke list untuk response.

---

## 4. Root / Endpoint Detail

Base URL: `http://localhost:8000`

### Root & Health
- `GET /` → info versi & list endpoints (`app/main.py:line 30`)
- `GET /health` → cek DB engine
- `POST /api/seed` → seed 3 teknisi + 5 service (`app/seed.py:line 1`)

### Services (`app/routers/services.py:line 1`)
| Method | Path | Query/Body | Response |
|--------|------|------------|----------|
| GET | `/api/services` | `?status=&search=&device=&skip=&limit=` | `List[ServiceOut]` |
| GET | `/api/services/{invoice}` | | `ServiceOut` |
| POST | `/api/services` | `ServiceCreate` JSON | `ServiceOut` 201 |
| PATCH | `/api/services/{invoice}` | `ServiceUpdate` | `ServiceOut` |
| PUT | `/api/services/{invoice}/status?status=` | | `ServiceOut` |
| DELETE | `/api/services/{invoice}` | | `{message}` |

**Contoh POST:**
```json
{
  "nama": "Renee Budiman",
  "wa": "081234567890",
  "device": "iPhone 11 64GB",
  "imei": "35xxxxxxxxxxxx",
  "keluhan": "LCD pecah & baterai drop",
  "kelengkapan": ["HP Saja", "+ Charger"],
  "biaya": 850000,
  "teknisi": "Andi",
  "estimasi_selesai": "2026-09-05"
}
```
Invoice auto: `INV-2026-0123`.

### Customers (`app/routers/customers.py:line 1`)
- `GET /api/customers?search=&device=` → list agregat: `id, nama, wa, total_service, terakhir_service, last_device`
- `GET /api/customers/{id}` → detail + `services[]`
- `POST /api/customers` → buat manual (WA unique)

### Technicians (`app/routers/technicians.py:line 1`)
- `GET /api/technicians` → list aktif
- `POST /api/technicians` → `{"nama":"Joko","foto":"https://..."}` 
- `GET /api/technicians/{id}/stats` → `{"total":5,"selesai":3,"persen":60}`

### Stats (`app/routers/stats.py:line 1`)
- `GET /api/stats` → `StatsOut`: `total_masuk, dalam_proses, selesai_hari_ini, estimasi_pendapatan, antri, dikerjakan, menunggu_sparepart, selesai`
- `GET /api/stats/dashboard` → gabungan `stats + recent[4] + technicians perf`
- `GET /api/search?q=` → global search 20 row

Semua response JSON, error pakai `HTTPException` dengan `detail` jelas.

---

## 5. CRUD & Logic Penting

`app/crud.py:line 1`
- `generate_invoice()` → cari `MAX(invoice)` tahun ini, increment, zero-pad 4 digit. Fallback `100+count+1`. Aman dari collision frontend.
- `create_service()` → upsert Customer by WA, resolve `technician_id` by nama, serialize `kelengkapan` ke JSON.
- `get_stats()` → real query `COUNT` & `SUM(biaya)` per hari, bukan `Math.random`.
- Customer list → agregasi via join + count.

---

## 6. Database Setup

`app/database.py:line 1`
```python
SQLALCHEMY_DATABASE_URL = "sqlite:///./b_gadget.db"
engine = create_engine(..., connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
```
File DB di `backend/b_gadget.db`, auto-create saat import `main.py`.

**Migrasi manual (hapus & reseed):**
```bash
rm backend/b_gadget.db
curl -X POST http://localhost:8000/api/seed
```

---

## 7. Frontend Integrasi

`script.js:line 1`
- `API_BASE = localStorage.API_BASE || http://localhost:8000/api`
- `normalize()` mapping `invoice ↔ id` + parse kelengkapan.
- `loadData()` → `GET /api/services`, fallback localStorage, update indikator.
- `apiCreateService()` → `POST /api/services`
- `apiUpdateStatus()` → `PUT /api/services/{invoice}/status`
- `updateStats()` → `GET /api/stats` untuk pendapatan real.
- `escapeHtml()` → cegah XSS (sebelumnya innerHTML raw).
- `updateInvoicePreview()` → hitung next invoice dari `stats.total_masuk`.

Jika ingin pakai frontend murni offline, set: `localStorage.setItem('API_BASE','')` lalu set `USE_API=false` di script.

---

## 8. Cara Jalankan (Ulang)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# seed
curl -X POST http://localhost:8000/api/seed
# buka http://localhost:8000/docs
```

Frontend: buka `index.html` dengan Live Server.

---

## 9. Pengujian Manual (curl)

```bash
# list
curl http://localhost:8000/api/services
# buat
curl -X POST http://localhost:8000/api/services -H "Content-Type: application/json" -d '{"nama":"Test","wa":"081111111111","device":"Samsung A54","keluhan":"Tes keluhan panjang","biaya":100000,"teknisi":"Andi"}'
# ubah status
curl -X PUT "http://localhost:8000/api/services/INV-2026-0123/status?status=Selesai"
# stats
curl http://localhost:8000/api/stats
# search
curl "http://localhost:8000/api/search?q=Renee"
```

---

## 10. Next Improvement (Rekomendasi)

- Auth JWT (kasir vs admin), pagination server-side + sorting, upload foto kondisi HP, export CSV real, notifikasi WA (Fonnte), QR tracking nota, backup DB harian.

---

*Dokumen ini auto-generate saat migrasi ke FastAPI+SQLite. Untuk audit historis lihat `AUDIT.md`.*
