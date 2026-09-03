# Cloudflare Tunnel - B_gadget

## File
- `config.yml` - konfigurasi named tunnel (domain sendiri)
- `../run-tunnel.bat` - runner 1-klik (pilih Quick atau Named)

## Cara Pakai

### Opsi A: Quick Tunnel (Tanpa Domain, 10 detik jadi) - Recommended buat coba
```bat
cloudflared tunnel --url http://localhost:8000
```
Output akan kasih URL `https://xxxx-xxxx.trycloudflare.com` -> langsung bisa akses dari internet (frontend + /api + /docs).

Atau double-klik `run-tunnel.bat` -> pilih `1`.

> Backend harus jalan dulu: `run.bat` (port 8000, host 0.0.0.0 - lihat backend/app/main.py:75 dan run.bat:75)

### Opsi B: Named Tunnel (Pakai Domain Sendiri, permanen)

1. Login:
```bat
cloudflared tunnel login
```

2. Buat tunnel:
```bat
cloudflared tunnel create b-gadget
```
Ini akan buat file `C:\Users\budirenee\.cloudflared\<TUNNEL_ID>.json` + tunjukkan TUNNEL_ID.

3. Edit `.cloudflared/config.yml`:
- ganti `tunnel: b-gadget` sesuai nama
- ganti `credentials-file: C:\Users\budirenee\.cloudflared\b-gadget.json` -> ganti `b-gadget.json` jadi `<TUNNEL_ID>.json` yang asli (atau `C:\Users\budirenee\.cloudflared\<TUNNEL_ID>.json`)
- ganti `hostname: bgadget.yourdomain.com` jadi domain kamu yang sudah di Cloudflare (misal `pos.bgadget.com`)

4. Route DNS:
```bat
cloudflared tunnel route dns b-gadget bgadget.yourdomain.com
```

5. Jalankan:
```bat
cloudflared tunnel --config .cloudflared/config.yml run b-gadget
```
Atau `run-tunnel.bat` -> pilih `2`.

Cek status: `cloudflared tunnel list` dan `cloudflared tunnel info b-gadget`

## Ingress untuk B_gadget
Backend FastAPI sudah serve:
- `/` -> API info
- `/health`, `/api/*` -> API
- `/frontend/*` -> frontend/index.html & login.html (main.py:54-56)
- `/assets/*` -> css/js/images
Jadi cukup 1 ingress `http://localhost:8000` sudah cover semua. Tidak perlu pisah frontend/backend port.

Jika mau split, tambah ingress:
```yaml
- hostname: api.bgadget.yourdomain.com
  service: http://localhost:8000
```

## Install cloudflared (Windows)
```bat
winget install --id Cloudflare.cloudflared -e
cloudflared --version
```
