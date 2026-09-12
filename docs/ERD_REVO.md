# ERD Revo — Visual Database Login

> Diagram ERD untuk Revo (superadmin, admin, teknisi)

## ERD ASCII

```
[users] 1 ──∞ [services] ∞ ── 1 [customers]
  │                │
  │                └──── 1 [technicians] (legacy)
  │
  └── is_active gate untuk login
```

## Detail Tabel `users`

```sql
users
-----
* id              INTEGER PK
  username        VARCHAR(50) UNIQUE NOT NULL
  password_hash   VARCHAR(255) NOT NULL
  role            VARCHAR(20) CHECK ('superadmin','admin','teknisi')
  is_active       BOOLEAN DEFAULT TRUE
  created_at      DATETIME
  last_login      DATETIME NULL
```

## Contoh Data Seeded

| id | username | role | is_active | password |
|----|----------|------|-----------|----------|
| 1 | superadmin | superadmin | true | bismillah (hash) |
| 2 | admin_revo | admin | false → true (after approve) | admin123 |
| 3 | teknisi_andi | teknisi | false → true | teknisi123 |

## Relasi Kode

- `backend/app/models.py:67` — User
- `backend/app/models.py:10` — Technician
- `backend/app/models.py:22` — Customer
- `backend/app/models.py:34` — Service
