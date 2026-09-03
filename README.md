# B_gadget — POS Service HP Dashboard

POS & tracking service HP untuk konter B_gadget. Frontend elegan + Backend FastAPI + SQLite (real database).

![Version](https://img.shields.io/badge/version-1.1_Rapih-black) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688) ![SQLite](https://img.shields.io/badge/SQLite-3-003B57)

---

## 📁 Struktur Project (Rapih)

```
PRAKTEK/
├── frontend/                 # ← Asset code & image terpisah rapi
│   ├── index.html            # Dashboard utama (canonical)
│   ├── login.html            # Login superadmin
│   └── assets/
│       ├── css/style.css     # Styling elegan
│       ├── js/script.js      # Hybrid API + localStorage
│       ├── js/script.legacy.js
│       └── images/           # Logo, foto kondisi, avatar
│           ├── logo.svg
│           └── .gitkeep
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI + mount frontend
│   │   ├── database.py       # SQLite engine
│   │   ├── models.py         # Service, Customer, Technician, User
│   │   ├── schemas.py
│   │   ├── auth.py           # Hash bismillah, JWT
│   │   ├── crud.py
│   │   ├── seed.py
│   │   └── routers/
│   │       ├── auth.py       # /api/auth/login (superadmin/bismillah)
│   │       ├── services.py
│   │       ├── customers.py
│   │       ├── technicians.py
│   │       └── stats.py
│   ├── requirements.txt
│   ├── run.py
│   └── b_gadget.db
├── .vscode/
│   ├── tasks.json            # Task: Run FastAPI, Seed, Test Login
│   └── launch.json           # Debug FastAPI
├── index.html                # (legacy root, tetap jalan - redirect ke frontend)
├── style.css / script.js     # (legacy root, mirror frontend/assets)
├── DOKUMENTASI.md
├── RECRUITMENT.md
└── AUDIT.md
```

**Aturan:**
- **Code** → `frontend/assets/css/`, `frontend/assets/js/`, `backend/app/`
- **Image** → `frontend/assets/images/` (jangan campur dengan code)
- **Root** `index.html` tetap ada untuk kompatibilitas GitHub Pages, tapi canonical ada di `frontend/index.html`

---

## 🚀 Quick Start

### 1. Backend (FastAPI + SQLite)

**Via VS Code Task (disarankan):**
`Ctrl+Shift+P` → `Tasks: Run Task` → `FastAPI: Run (dev)`  
Atau `F5` → `FastAPI: Debug`

**Manual:**
```bash
cd backend
"C:\Users\budirenee\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
"C:\Users\budirenee\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --reload --port 8000
```

Buka:
- API: http://localhost:8000/
- Docs: http://localhost:8000/docs
- Frontend via API: http://localhost:8000/frontend/index.html
- Login: http://localhost:8000/frontend/login.html

**Seed:**
```bash
curl -X POST http://localhost:8000/api/seed
# superadmin otomatis terbuat saat startup, tapi bisa paksa:
curl -X POST http://localhost:8000/api/auth/seed-superadmin
```

### 2. Frontend

Buka `frontend/index.html` via Live Server, atau via FastAPI static di atas.
- Jika backend online → pakai API
- Jika offline → fallback localStorage, indikator `Offline`

### 3. Login Superadmin

Default:
```
username: superadmin
password: bismillah
```
Test:
```bash
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"superadmin\",\"password\":\"bismillah\"}"
```
Response ada `access_token` (JWT 24 jam). Pakai untuk `Authorization: Bearer <token>` ke `GET /api/auth/me` atau `GET /api/auth/users` (butuh superadmin).

Login page: `frontend/login.html` sudah ada form siap pakai, token disimpan di `localStorage`.

---

## 🔌 API Root List

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/api/auth/login` | Login JSON `{username,password}` → JWT |
| POST | `/api/auth/login-form` | Login OAuth2 form |
| GET | `/api/auth/me` | Info user (Bearer) |
| GET | `/api/auth/users` | List users (superadmin only) |
| POST | `/api/auth/seed-superadmin` | Buat superadmin bismillah |
| GET | `/` | Root info |
| GET | `/health` | Cek DB |
| POST | `/api/seed` | Seed teknisi + service + superadmin |
| GET | `/api/services` | List service |
| POST | `/api/services` | Buat service |
| PUT | `/api/services/{invoice}/status` | Ubah status |
| GET | `/api/customers` | List pelanggan |
| GET | `/api/technicians` | List teknisi |
| GET | `/api/stats` | Stats dashboard |
| GET | `/api/stats/dashboard` | Recent + perf |

---

## 💾 Database

`backend/b_gadget.db` auto-create. ERD: `User`, `Technician 1—* Service *—1 Customer`.

---

## 🛡️ Audit

Dulu localStorage → sekarang SQLite + JWT + superadmin. Lihat `AUDIT.md:line 1`.

---

## 📄 Docs

- `DOKUMENTASI.md:line 1` — model, endpoint, cara seed
- `RECRUITMENT.md:line 1` — teks rekrutmen
- `.vscode/tasks.json:line 1` — task VS Code

---

B_gadget • v1.1 Rapih • superadmin: `superadmin / bismillah`
