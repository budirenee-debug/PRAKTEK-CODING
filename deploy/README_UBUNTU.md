# Deploy B_gadget ke Ubuntu Server

Repo sudah di-push `3e00a46` + folder `deploy/` (b-gadget.service, cloudflared.service). Ikuti ini di Ubuntu:

## 1. Clone & Python
```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv git
# Catatan: server saat ini di /home/budirn/PRAKTEK (cek: curl https://service.reneepsl.my.id/health -> engine sqlite:////home/budirn/...)
# Jika sudah ada di /home/budirn/PRAKTEK, jangan clone ke /opt lagi. Pakai salah satu:
# Opsi aktual (server existing):
cd /home/budirn/PRAKTEK
# Opsi fresh /opt (butuh migrasi service):
sudo mkdir -p /opt && sudo chown $USER:$USER /opt
git clone https://github.com/budirenee-debug/PRAKTEK-CODING.git /opt/PRAKTEK
cd /opt/PRAKTEK
python3.12 -m venv venv
venv/bin/pip install -r backend/requirements.txt
```

## 2. Env & DB
```bash
cp backend/.env.example backend/.env
# edit SECRET_KEY random
nano backend/.env
# DB sqlite auto-create, kalau mau bawa data lokal:
# scp "F:\VIBE CODING\CODING MJPRO\PRAKTEK\backend\b_gadget.db" user@server:/opt/PRAKTEK/backend/b_gadget.db
```

## 3. Cloudflared
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
sudo mv cloudflared /usr/local/bin/cloudflared && sudo chmod +x /usr/local/bin/cloudflared
# Portable: config.yml sekarang pakai credentials-file: .cloudflared/debc4532...json (relatif)
# Di server tinggal copy JSON ke .cloudflared/ :
mkdir -p /home/budirn/PRAKTEK/.cloudflared  # atau /opt/PRAKTEK/.cloudflared jika pakai /opt
# copy dari lokal (PC Br) - jalankan di PowerShell lokal:
# scp ".cloudflared/debc4532-0e35-4364-967d-9d8f50344e3e.json" budirn@server:/home/budirn/PRAKTEK/.cloudflared/
# scp ".cloudflared/cert.pem" budirn@server:/home/budirn/PRAKTEK/.cloudflared/  # opsional
# Override absolute jika perlu (Ubuntu tidak support path Windows):
sudo nano /home/budirn/PRAKTEK/.cloudflared/config.yml
# pastikan: tunnel: b-gadget
# credentials-file: /home/budirn/PRAKTEK/.cloudflared/debc4532-0e35-4364-967d-9d8f50344e3e.json
```

## 4. Systemd (auto-start habis reboot)
```bash
sudo cp deploy/b-gadget.service /etc/systemd/system/
sudo cp deploy/cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now b-gadget
sudo systemctl enable --now cloudflared
systemctl status b-gadget --no-pager
systemctl status cloudflared --no-pager
curl http://127.0.0.1:8000/health
cloudflared tunnel list
```

## 5. DNS (atasi 0.0.0.0)
```bash
sudo nano /etc/netplan/01-netcfg.yaml
# tambahkan nameservers: [1.1.1.1,8.8.8.8] di bawah dhcp4:true
sudo netplan apply
resolvectl status
```

## 6. Dev lokal tetap efektif
- Dev di `F:\VIBE CODING\...` Windows pakai `run.bat` `--reload`
- `git add && git commit && git push`
- Di server: `cd /opt/PRAKTEK && git pull && sudo systemctl restart b-gadget`

## 7. Nginx opsional (jika mau tanpa tunnel)
```nginx
server { listen 80; server_name service.reneepsl.my.id;
  location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
}
```
