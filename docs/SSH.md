# SSH Ubuntu Server (LAN)

> Password TIDAK disimpan di repo ini — repo di-push ke GitHub.
> Lihat `deploy/SECURITY-TODO.md`: password auth rencananya dimatikan.
> Pakai SSH key / ssh-agent di PC masing-masing.

- Host: `192.168.0.10` (LAN, DHCP — bisa berubah, cek router jika putus)
- User: `budirn`
- Path app: `/home/budirn/PRAKTEK`
- Contoh: `ssh budirn@192.168.0.10`

## Cek cepat (tanpa sqlite3 CLI — pakai python3)

```bash
cd /home/budirn/PRAKTEK
git log --oneline -3
python3 -c "import sqlite3; con=sqlite3.connect('backend/b_gadget.db'); cur=con.cursor(); print('--- spareparts ---'); [print(r) for r in cur.execute('SELECT id,nama,harga,harga_beli,stok FROM spareparts ORDER BY id DESC LIMIT 5')]; print('--- ledger ---'); [print(r) for r in cur.execute('SELECT id,tanggal,jenis,kategori,nominal,ref_type FROM ledger_entries ORDER BY id DESC LIMIT 5')]; print('--- expenses ---'); [print(r) for r in cur.execute('SELECT id,tanggal,kategori,keperluan,nominal FROM expenses ORDER BY id DESC LIMIT 5')]"
```

## Sync kode + restart

```bash
cd /home/budirn/PRAKTEK && git pull origin main && sudo systemctl restart b-gadget
curl -s http://127.0.0.1:8000/health
```

> Restart butuh **±10 detik** siap (2 worker uvicorn, migrasi jalan di tiap worker).
> Cek dengan loop, jangan langsung curl:
> ```bash
> for i in $(seq 1 20); do curl -fsS --max-time 3 http://127.0.0.1:8000/health && break; sleep 2; done
> ```

---

## Backup DB terjadwal (cron)

Installer: `22 Okt 2026`. Cron milik user `budirn` (tanpa sudo):

```
15 2,14 * * * bash /home/budirn/PRAKTEK/deploy/backup-db.sh >> /home/budirn/.backups/b-gadget/cron/backup.log 2>&1
```

- **02:15** (rehat malam) + **14:15** (siang, aman dari jam sibuk)
- Lokasi backup: `/home/budirn/.backups/b-gadget/cron/` — 14 file terakhir, tiap file ~136 KB (gzip)
- Online backup (SQLite backup API, aman saat app jalan) + `PRAGMA quick_check` + checkpoint WAL

### Perintah

```bash
bash deploy/backup-db.sh                  # backup sekali (dipakai cron)
bash deploy/backup-db.sh --list           # daftar backup
bash deploy/backup-db.sh --restore <file> # pulihkan DB (app di-stop otomatis)
tail -30 /home/budirn/.backups/b-gadget/cron/backup.log
```

> Backup saat deploy juga jalan (`deploy/sync-ubuntu.sh`) tapi HANYA saat ada deploy —
> itu sebabnya cron harian ini penting.
