#!/usr/bin/env bash
# B_gadget - Linux runner (pengganti run.bat)
# Jalankan: ./deploy/run.sh atau systemctl start b-gadget
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
PORT=8000

echo "========================================"
echo " B_gadget POS - Linux Runner"
echo " Root: $ROOT"
echo "========================================"

# 1. Python
if [ -x "$HOME/.local/bin/python3.12" ]; then PYTHON="$HOME/.local/bin/python3.12"
elif command -v python3 >/dev/null 2>&1; then PYTHON=python3
else echo "[ERROR] python3 tidak ditemukan"; exit 1; fi
echo "[INFO] Python: $PYTHON ($($PYTHON --version))"

# 2. Cek backend
[ -f "$BACKEND/app/main.py" ] || { echo "[ERROR] backend/app/main.py tidak ada"; exit 1; }

# 3. Deps
echo "[INFO] Cek deps..."
if ! $PYTHON -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "[WARN] install deps..."
  $PYTHON -m pip install -r "$BACKEND/requirements.txt"
fi
echo "[INFO] Deps OK"

# 4. Port busy
if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
  echo "[WARN] Port $PORT sudah LISTENING"
else
  echo "[INFO] Port $PORT free"
fi

# 5. Cloudflared
if command -v cloudflared >/dev/null 2>&1; then
  echo "[INFO] cloudflared: $(cloudflared --version)"
else
  echo "[WARN] cloudflared tidak ada - mode lokal saja"
fi

# 6. Jalankan backend (blocking)
cd "$BACKEND"
exec $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
