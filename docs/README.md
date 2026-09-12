# 📚 Dokumentasi B_gadget — Index

> Semua file penting sudah dirapikan di `docs/` agar root project bersih.
> Untuk Revo (database login 3 role) langsung buka `REVO.md`.

---

## 📁 Struktur `docs/`

```
docs/
├── README.md        ← kamu di sini (index)
├── REVO.md          ← 🔐 Database Login Revo (superadmin, admin, teknisi) — UTAMA
├── ERD_REVO.md      ← 🗺️ ERD visual Revo
├── DOKUMENTASI.md   ← 📖 Dokumentasi API & Model FastAPI+SQLite (legacy lengkap)
├── AUDIT.md         ← 🛡️ Audit Revo (temuan & fix sebelum migrasi)
├── RECRUITMENT.md   ← 👥 Teks rekrutmen (IG, WA, poster)
└── REKRUTMEN.txt    ← 📄 Versi teks pendek rekrutmen
```

---

## 🚀 Mulai Cepat

| Kebutuhan | Buka File | Deskripsi |
|-----------|-----------|-----------|
| **Login Revo (3 role)** | [`REVO.md`](./REVO.md) | Skema `users`, RBAC, JWT, alur register→approve→login, 12 endpoint `/api/auth/*`, DDL, curl test |
| **ERD Visual** | [`ERD_REVO.md`](./ERD_REVO.md) | Diagram ASCII & contoh data seeded |
| **API Umum** | [`DOKUMENTASI.md`](./DOKUMENTASI.md) | Model `Service/Customer/Technician`, endpoint `/api/services`, `/api/customers`, `/api/stats`, cara seed |
| **Audit & Migrasi** | [`AUDIT.md`](./AUDIT.md) | Skor 5.5→8.5, bug localStorage, fix `escapeHtml`, `generate_invoice` |
| **Rekrutmen** | [`RECRUITMENT.md`](./RECRUITMENT.md) | 3 versi (pendek, lengkap, WA broadcast) + checklist internal |

---

## 🔐 Revo — Ringkas

**Role:** `superadmin` (owner), `admin` (operasional), `teknisi` (eksekusi service)

| File Kode | Line | Kegunaan |
|-----------|------|----------|
| `backend/app/models.py` | 67 | `User` model |
| `backend/app/auth.py` | 1 | hash `bcrypt`, `create_access_token`, `ensure_superadmin()` |
| `backend/app/routers/auth.py` | 1 | 12 endpoint auth + `require_superadmin` |
| `frontend/login.html` | 1 | Form login & register Revo |
| `frontend/index.html` | 90 | Menu `Persetujuan Akun` (superadmin only) |

Default login: `superadmin / bismillah` → `POST /api/auth/login` → `Authorization: Bearer <token>`

Detail penuh lihat [`REVO.md`](./REVO.md).

---

## 📖 Cara Baca Docs

1. **Baru clone?** Baca `../README.md` (root) untuk Quick Start & struktur project.
2. **Butuh auth?** Langsung `REVO.md` §3–§7.
3. **Butuh API service?** `DOKUMENTASI.md` §4.
4. **Mau rekrut tim?** `RECRUITMENT.md` siap copy-paste ke IG/WA.

---

## 🔗 Link Terkait

- Root README: [`../README.md`](../README.md)
- API Docs (Swagger): `http://localhost:8000/docs`
- Login Page: `frontend/login.html` atau `http://localhost:8000/frontend/login.html`
- Health Check: `http://localhost:8000/health`

---

*Docs dirapikan 6 September 2026 — Revo 3 role. Root project tetap bersih, semua markdown penting ada di `docs/`.*
