# 🖨️ Log Print Detail — Nama File + Jam (Server Ubuntu)

> Aktif: **14 Okt 2026**. Setiap print yang masuk ke printer server sekarang tercatat
> **nama file + jam + user + jumlah halaman**. Cara lihat: `tools/cek-print-log.ps1`
> dari PC, atau `bash deploy/print-log.sh` di server.

## 1. Masalah awal

Histori CUPS cuma nyimpen ID job, user, ukuran, jam — **tanpa nama file**.
Penyebab di `/etc/cups/cupsd.conf`: `LogLevel warn` + `PageLogFormat` kosong
(page logging mati), `page_log` tidak pernah dibuat.

## 2. Yang diubah di server (2026-10-14)

Backup: `/etc/cups/cupsd.conf.bak-printlog-20261014` (di server).

| Direktif | Nilai | Efek |
|----------|-------|------|
| `LogLevel` | `debug` | `error_log` nyatet detail tiap job termasuk nama dokumen |
| `PageLogFormat` | `%p %u %j %T %P %C %{job-billing} %{job-originating-host-name} %{job-name} %{media} %{sides}` | `page_log` dibuat per halaman, ada kolom `%{job-name}` |
| `PreserveJobHistory` | `Yes` | histori job disimpan sampai batas `MaxJobs` |
| `MaxJobs` | `500` | 500 job terakhir bisa di-`lpstat` |

Verifikasi saat itu: `cupsd -t` OK → `systemctl restart cups` → `active`.
`cupsctl` biasa (`cupsctl` / baca `cupsd.conf`) butuh sudo — pola yang dipakai
sama seperti script server lain: `sudo -S ... < /home/budirn/.sudopass`.

## 3. Format `page_log` (satu baris = satu halaman)

```
printer user job-id [tgl:jam +zona] hal copy billing host NAMA-FILE media sides
```

Contoh format (ilustrasi, bukan data asli):

```
BrotherUSB budirn 8 [15/Oct/2026:09:12:03 +0700] 1 1 - localhost Nota-Servis.pdf A4 one-sided
BrotherUSB budirn 8 [15/Oct/2026:09:12:03 +0700] 2 1 - localhost Nota-Servis.pdf A4 one-sided
```

`deploy/print-log.sh` mengelompokkan per job-id jadi satu baris:
`JOB | WAKTU (halaman pertama) | PRINTER / USER | HAL (jumlah halaman) | COPY | NAMA FILE`.

## 4. Cara pakai

```powershell
# Dari PC Windows (via Tailscale):
powershell -File tools\cek-print-log.ps1
powershell -File tools\cek-print-log.ps1 -Limit 50
powershell -File tools\cek-print-log.ps1 -Json      # output JSON (untuk arsip/skrip)
powershell -File tools\cek-print-log.ps1 -Lan       # via LAN 192.168.0.10
```

```bash
# Langsung di server (via SSH):
cd ~/PRAKTEK && bash deploy/print-log.sh -n 20
bash deploy/print-log.sh --json -n 50
```

Kedua script **read-only, tanpa sudo** (user `budirn` grup `adm` bisa baca
`/var/log/cups/*`). Kalau `deploy/print-log.sh` belum ada di server
(belum `git pull`), script PC otomatis fallback ke `lpstat` kasar.

## 5. Catatan penting

- **Job lama (sebelum 14 Okt 2026) tetap tanpa nama file** — datanya memang
  tidak pernah ditulis CUPS. Contoh: job 4/6 (10 Okt, PDF 3 hal, ~992 KB)
  dan job 7 (14 Okt 14:42, ~994 KB) hanya ketahuan jam + ukurannya.
- **Berlaku untuk print berikutnya**: `page_log` baru muncul setelah ada
  halaman tercetak pasca-aktivasi.
- **Disk**: `page_log` hanya teks satu baris per halaman (kecil). File dokumen
  job tetap ikut default CUPS (`PreserveJobFiles` 1 hari) lalu dibersihkan
  otomatis — tidak menumpuk.
- `error_log` sekarang lebih verbose (level debug) tapi tetap dirotasi
  logrotate seperti biasa.

## 6. Rollback (kalau mau matikan lagi)

```bash
sudo -S cp /etc/cups/cupsd.conf.bak-printlog-20261014 /etc/cups/cupsd.conf < /home/budirn/.sudopass
sudo -S systemctl restart cups < /home/budirn/.sudopass
```

## 7. Pengembangan lanjutan (belum dikerjakan)

- Endpoint API `/api/print-logs` (baca `page_log` dari backend, khusus
  superadmin) + tab di `frontend/owner.html` — bilang aja kalau mau ditarik
  sampai ke dashboard.
