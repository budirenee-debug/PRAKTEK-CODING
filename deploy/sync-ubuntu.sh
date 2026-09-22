#!/usr/bin/env bash
# Sync Ubuntu server /home/budirn/PRAKTEK - jalankan di server via SSH
# Langkah 4+5+6 dari audit 6 langkah
set -e
SERVER_ROOT="/home/budirn/PRAKTEK"
ALT_ROOT="/opt/PRAKTEK"
if [ -d "$SERVER_ROOT/.git" ]; then ROOT=$SERVER_ROOT; elif [ -d "$ALT_ROOT/.git" ]; then ROOT=$ALT_ROOT; else echo "[ERROR] PRAKTEK repo tidak ditemukan di $SERVER_ROOT atau $ALT_ROOT"; exit 1; fi
echo "[INFO] ROOT: $ROOT"
cd "$ROOT"
echo "[1/6] git pull origin/main"
git fetch origin
echo "--- origin/main log ---"
git log --oneline origin/main -5
git pull origin main
echo "[2/6] venv deps"
if [ -f venv/bin/pip ]; then venv/bin/pip install -r backend/requirements.txt; else python3 -m pip install -r backend/requirements.txt; fi
echo "[3/6] .env check"
if [ ! -f backend/.env ]; then cp backend/.env.example backend/.env; echo "[WARN] backend/.env dibuat dari example - EDIT SECRET_KEY!"; fi
cat backend/.env
echo "[4/6] DB checkpoint"
if [ -f backend/b_gadget.db ]; then sqlite3 backend/b_gadget.db "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || python3 -c "import sqlite3; c=sqlite3.connect('backend/b_gadget.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.commit()"; echo "checkpoint done"; ls -lh backend/*.db* 2>/dev/null || true; fi
echo "[5/6] systemctl restart"
if systemctl list-unit-files 2>/dev/null | grep -q b-gadget; then sudo systemctl daemon-reload; sudo systemctl restart b-gadget; sleep 2; systemctl status b-gadget --no-pager -l 2>&1 | head -n 30; curl -s http://127.0.0.1:8000/health || true; echo; fi
if systemctl list-unit-files 2>/dev/null | grep -q cloudflared; then sudo systemctl restart cloudflared; sleep 2; systemctl status cloudflared --no-pager -l 2>&1 | head -n 20; fi
echo "[6/6] health check public"
curl -s http://127.0.0.1:8000/health; echo
curl -s http://127.0.0.1:8000/api/stats; echo
echo "[DONE] Untuk overwrite DB dari lokal (master= lokal 108 records):"
echo "  Di PC lokal PowerShell:"
echo '  scp \"backend/b_gadget.db\" budirn@SERVER:/home/budirn/PRAKTEK/backend/b_gadget.db'
echo '  ssh budirn@SERVER \"sudo systemctl restart b-gadget && curl -s http://127.0.0.1:8000/api/stats\"'
