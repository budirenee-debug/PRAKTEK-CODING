#!/usr/bin/env bash
# ==========================================================
#  B_gadget POS - Localhost Runner (LOKAL SAJA) - Ubuntu
#  - Backend : FastAPI http://127.0.0.1:8000
#  - Tanpa Tunnel / Cloudflare
#  - Usage: chmod +x run.sh && ./run.sh
#  - Butuh tunnel? pakai ./run-tunnel.sh
# ==========================================================
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
PORT=8000
LOGIN_PATH="/frontend/login.html"

echo "========================================"
echo " B_gadget POS - Localhost Only (Ubuntu)"
echo " Root : $ROOT"
echo " Mode : LOKAL (tanpa tunnel)"
echo "========================================"
echo ""

# ---------- 1. Cari Python ----------
PYTHON_EXE=""
if command -v python3 &>/dev/null; then PYTHON_EXE="python3"
elif command -v python &>/dev/null; then PYTHON_EXE="python"
else
  echo "[ERROR] Python tidak ditemukan. Install: sudo apt update && sudo apt install python3 python3-pip -y"
  exit 1
fi
echo "[INFO] Python : $PYTHON_EXE ($($PYTHON_EXE --version))"

# ---------- 2. Cek backend ----------
if [[ ! -f "$BACKEND/app/main.py" ]]; then
  echo "[ERROR] backend/app/main.py tidak ditemukan di $BACKEND"
  exit 1
fi

# ---------- 3. Dependencies ----------
echo "[INFO] Cek dependencies fastapi+uvicorn ..."
if ! $PYTHON_EXE -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "[ERROR] fastapi/uvicorn belum terinstall."
  echo "        Jalankan: $PYTHON_EXE -m pip install -r backend/requirements.txt"
  exit 1
else
  echo "[INFO] Dependencies OK."
fi

# ---------- 4. Cek port ----------
if ss -tlnp 2>/dev/null | grep -q ":$PORT " || netstat -tlnp 2>/dev/null | grep -q ":$PORT "; then
  echo "[WARN] Port $PORT sudah LISTENING (server mungkin sudah jalan)."
  echo "       Cek: curl http://127.0.0.1:$PORT/health"
  echo "       Membuka browser tidak otomatis di server."
  echo ""
  curl -s http://127.0.0.1:$PORT/health || true
  echo ""
  echo "[INFO] Backend sudah berjalan - tidak start ulang."
  exit 0
fi

# ---------- 5. Info ----------
echo "[INFO] Mode: LOKAL ONLY - tanpa cloudflared/tunnel"
echo "[INFO] Akses lokal: http://127.0.0.1:$PORT$LOGIN_PATH"
echo "[INFO] Butuh akses publik? Jalankan ./run-tunnel.sh"
echo ""
echo "[INFO] Menjalankan backend di http://127.0.0.1:$PORT"
echo "       Docs  : http://127.0.0.1:$PORT/docs"
echo "       Health: http://127.0.0.1:$PORT/health"
echo ""

# ---------- 6. Jalankan backend ----------
cd "$BACKEND"
if [[ "$ENV" == "production" ]]; then
  exec $PYTHON_EXE -m uvicorn app.main:app --host 127.0.0.1 --port $PORT
else
  exec $PYTHON_EXE -m uvicorn app.main:app --host 127.0.0.1 --port $PORT --reload
fi
