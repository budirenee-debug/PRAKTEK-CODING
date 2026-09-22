#!/usr/bin/env bash
# ==========================================================
#  B_gadget POS - Tunnel Runner (LOKAL + PUBLIK) - Ubuntu
#  - Backend  : FastAPI http://127.0.0.1:8000
#  - Tunnel   : otomatis Named (service.reneepsl.my.id) jika
#               kredensial ada, else Quick (*.trycloudflare.com)
#  - Untuk Ubuntu Server
#  - Usage: chmod +x run-tunnel.sh && ./run-tunnel.sh
#  - Lokal saja? pakai ./run.sh
# ==========================================================
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
CFDIR="$ROOT/.cloudflared"
PORT=8000
LOGIN_PATH="/frontend/login.html"

echo "========================================"
echo " B_gadget POS - Tunnel Runner (Ubuntu)"
echo " Root : $ROOT"
echo " Mode : LOKAL + TUNNEL"
echo "========================================"
echo ""

# ---------- 1. Cari Python ----------
PYTHON_EXE=""
if command -v python3 &>/dev/null; then PYTHON_EXE="python3"
elif command -v python &>/dev/null; then PYTHON_EXE="python"
else
  echo "[ERROR] Python tidak ditemukan."
  exit 1
fi
echo "[INFO] Python : $PYTHON_EXE ($($PYTHON_EXE --version))"

# ---------- 2. Cek backend ----------
if [[ ! -f "$BACKEND/app/main.py" ]]; then
  echo "[ERROR] backend/app/main.py tidak ditemukan"
  exit 1
fi

# ---------- 3. Dependencies ----------
echo "[INFO] Cek dependencies ..."
if ! $PYTHON_EXE -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "[ERROR] fastapi/uvicorn belum terinstall. Jalankan: $PYTHON_EXE -m pip install -r backend/requirements.txt"
  exit 1
else
  echo "[INFO] Dependencies OK."
fi

# ---------- 4. Cek port ----------
PORT_BUSY=0
if ss -tlnp 2>/dev/null | grep -q ":$PORT " || netstat -tlnp 2>/dev/null | grep -q ":$PORT "; then
  PORT_BUSY=1
  echo "[WARN] Port $PORT sudah LISTENING."
fi

# ---------- 5. Cari cloudflared ----------
CLOUDFLARED_EXE=""
if command -v cloudflared &>/dev/null; then CLOUDFLARED_EXE="cloudflared"
elif [[ -x "$CFDIR/bin/cloudflared" ]]; then CLOUDFLARED_EXE="$CFDIR/bin/cloudflared"
elif [[ -x "/usr/local/bin/cloudflared" ]]; then CLOUDFLARED_EXE="/usr/local/bin/cloudflared"
fi

if [[ -n "$CLOUDFLARED_EXE" ]]; then
  echo "[INFO] cloudflared : $CLOUDFLARED_EXE"
else
  echo "[WARN] cloudflared tidak ditemukan. Lanjut mode LOCALHOST saja."
  echo "       Install: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared && sudo mv /tmp/cloudflared /usr/local/bin/cloudflared && sudo chmod +x /usr/local/bin/cloudflared"
fi

# ---------- 6. Tentukan mode tunnel ----------
MODE="none"
if [[ -n "$CLOUDFLARED_EXE" ]]; then MODE="quick"; fi
if [[ -n "$CLOUDFLARED_EXE" && -f "$CFDIR/config.yml" && -n "$(ls -1 ~/.cloudflared/*.json 2>/dev/null)" ]]; then
  MODE="named"
fi
echo "[INFO] Mode tunnel: $MODE - named=service.reneepsl.my.id, quick=*.trycloudflare.com, none=lokal"
echo ""

# ---------- 7. Jalankan tunnel di background ----------
if [[ "$PORT_BUSY" == "1" && "$MODE" != "none" ]]; then
  echo "[INFO] Port busy - restart tunnel lama..."
  pkill -f cloudflared || true
  sleep 2
fi

if [[ "$MODE" == "named" ]]; then
  echo "[INFO] Menjalankan Named Tunnel - service.reneepsl.my.id ..."
  nohup "$CLOUDFLARED_EXE" tunnel --config "$CFDIR/config.yml" run b-gadget > /tmp/b-gadget-tunnel.log 2>&1 &
  echo "[INFO] Publik : https://service.reneepsl.my.id$LOGIN_PATH"
  echo "[INFO] Log    : tail -f /tmp/b-gadget-tunnel.log"
elif [[ "$MODE" == "quick" ]]; then
  echo "[INFO] Menjalankan Quick Tunnel - trycloudflare.com ..."
  nohup "$CLOUDFLARED_EXE" tunnel --url http://127.0.0.1:$PORT > /tmp/b-gadget-tunnel.log 2>&1 &
  echo "[INFO] Tunggu 5-10 detik, lalu cek log: cat /tmp/b-gadget-tunnel.log | grep trycloudflare"
  echo "[INFO] Lokal tetap: http://127.0.0.1:$PORT$LOGIN_PATH"
else
  echo "[INFO] Tunnel dilewati. Akses lokal: http://127.0.0.1:$PORT$LOGIN_PATH"
fi
echo ""

# Jika port sudah busy, cukup tampilkan status tunnel
if [[ "$PORT_BUSY" == "1" ]]; then
  echo "[INFO] Backend sudah berjalan di port $PORT - tidak start ulang."
  curl -s http://127.0.0.1:$PORT/health || true
  echo ""
  if [[ "$MODE" != "none" ]]; then
    echo "[INFO] Tunnel berjalan di background. Cek: ps aux | grep cloudflared"
    echo "       Log: cat /tmp/b-gadget-tunnel.log"
  fi
  exit 0
fi

# ---------- 8. Jalankan backend ----------
echo "[INFO] Menjalankan backend di http://127.0.0.1:$PORT"
echo "       Docs  : http://127.0.0.1:$PORT/docs"
echo "       Health: http://127.0.0.1:$PORT/health"
if [[ "$MODE" == "named" ]]; then echo "       Publik: https://service.reneepsl.my.id$LOGIN_PATH"; fi
echo ""
echo "[TIPS] Biarkan terminal ini terbuka. Ctrl+C untuk stop backend. Tunnel tetap jalan di background (kill dengan pkill cloudflared)."
echo ""

cd "$BACKEND"
if [[ "$ENV" == "production" ]]; then
  exec $PYTHON_EXE -m uvicorn app.main:app --host 127.0.0.1 --port $PORT
else
  exec $PYTHON_EXE -m uvicorn app.main:app --host 127.0.0.1 --port $PORT --reload
fi
