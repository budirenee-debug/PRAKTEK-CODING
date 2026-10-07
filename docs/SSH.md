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
