#!/usr/bin/env bash
# ==============================================================================
#  deploy/backup-db.sh — Backup terjadwal DB B_gadget (SQLite online-safe)
#
#  Kenapa perlu: DB produção cuma di-backup saat deploy (deploy/sync-ubuntu.sh).
#  Kalau tidak ada job harian, data hilang/rusak = dataVG ngawur 1-2 minggu
#  sebelum sadar. Backup ini jalan DARI CRON, tidak ganggu app yang sedang hidup.
#
#  Cara pasang (DI SERVER, sebagai user budirn):
#      crontab -e
#      # backup tiap hari 02:15 WIB + sekali lagi 14:15 WIB (siang, aman dari jam sibuk)
#      15 2,14 * * * /home/budirn/PRAKTEK/deploy/backup-db.sh >> /home/budirn/.backups/b_gadget/cron/backup.log 2>&1
#
#  Perintah:
#      bash deploy/backup-db.sh              # backup sekali (dipakai cron)
#      bash deploy/backup-db.sh --list       # daftar backup yang ada
#      bash deploy/backup-db.sh --restore <file>   # pulihkan DB dari backup (BERHENTIKAN APP DULU)
#
#  Aman saat app jalan: pakai SQLite online backup API (bukan copy file mentah),
#  lalu di-check quick_check. WAL ikut ter-backup.
# ==============================================================================
set -Eeuo pipefail

APP_NAME="b-gadget"
DB_FILE="${HOME}/PRAKTEK/backend/b_gadget.db"
BACKUP_DIR="${HOME}/.backups/${APP_NAME}/cron"
KEEP=14                      # simpan 14 backup terakhir (~2 minggu)
SERVICE="${APP_NAME}.service"
SUDO="sudo"

log()  { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { printf '[%s] ⚠  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
die()  { printf '[%s] ✖ FATAL: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; exit 1; }

list_backups() {
  ls -1t "${BACKUP_DIR}"/b_gadget-*.db.gz 2>/dev/null || true
}

do_backup() {
  [ -f "$DB_FILE" ] || die "DB tidak ditemukan: $DB_FILE"
  mkdir -p "$BACKUP_DIR"
  local stamp dest tmp
  stamp="$(date '+%Y%m%d-%H%M%S')"
  dest="${BACKUP_DIR}/${APP_NAME}-${stamp}.db.gz"
  tmp="${dest}.tmp"

  # 1) online backup (aman saat app jalan) + verifikasi
  python3 - "$DB_FILE" "$tmp" <<'PY'
import sqlite3, sys, os
src_path, dst_path = sys.argv[1], sys.argv[2]
s = sqlite3.connect(src_path, timeout=30)
try:
    s.execute("PRAGMA wal_checkpoint(TRUNCATE)")
except sqlite3.Error:
    pass
d = sqlite3.connect(dst_path)
with d:
    s.backup(d)
chk = d.execute("PRAGMA quick_check").fetchone()[0]
n = d.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
d.close(); s.close()
if chk != "ok":
    raise SystemExit("backup corrupt: %s" % chk)
print("    quick_check=ok, objek=%d" % n)
PY

  # 2) kompres
  gzip -9 "$tmp" && mv "$tmp.gz" "$dest"

  # 3) rotasi: sisakan KEEP terakhir
  local keep
  keep=$(list_backups | tail -n +$((KEEP + 1)))
  if [ -n "$keep" ]; then
    while IFS= read -r old; do
      [ -n "$old" ] && rm -f "$old" && log "  hapus backup lama: $(basename "$old")"
    done <<< "$keep"
  fi

  local size
  size=$(du -h "$dest" | cut -f1)
  log "backup OK: $(basename "$dest") (${size})"
  log "total backup: $(list_backups | wc -l) file"
}

do_restore() {
  local src="${1:-}"
  [ -n "$src" ] || die "pakai: --restore <file>"
  [ -f "$src" ] || die "file backup tidak ditemukan: $src"
  case "$src" in
    *.gz) log "dekompres $src" ; local plain="${BACKUP_DIR}/restore-tmp.db"
           gzip -dc "$src" > "$plain" ;;
    *)    local plain="$src" ;;
  esac
  log "cek integritas backup..."
  python3 - "$plain" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
chk = con.execute("PRAGMA quick_check").fetchone()[0]
n = con.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]
con.close()
if chk != "ok":
    raise SystemExit("backup corrupt: %s" % chk)
print("    quick_check=ok, ledger_entries=%d" % n)
PY
  log "stop app..."
  ${SUDO} systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  sleep 2
  local stamp
  stamp="$(date '+%Y%m%d-%H%M%S')"
  cp "$DB_FILE" "${DB_FILE}.sebelum-restore-${stamp}" 2>/dev/null || true
  rm -f "${DB_FILE}" "${DB_FILE}-wal" "${DB_FILE}-shm"
  cp "$plain" "$DB_FILE"
  chown "$(id -un):$(id -gn)" "$DB_FILE" 2>/dev/null || true
  log "DB dipulihkan. start app..."
  ${SUDO} systemctl start "$SERVICE" >/dev/null 2>&1 || true
  sleep 3
  curl -fsS --max-time 5 http://127.0.0.1:8000/health && echo "" || warn "health check gagal, cek journalctl -u $SERVICE"
  [ -f "$plain" ] && [ "$plain" != "$src" ] && rm -f "$plain"
  log "restore selesai"
}

case "${1:-}" in
  --list)
    n=$(list_backups | wc -l)
    echo "Total $n backup di $BACKUP_DIR"
    list_backups | while read -r f; do
      printf '  %-42s %8s  %s\n' "$(basename "$f")" "$(du -h "$f" | cut -f1)" "$(date -r "$f" '+%Y-%m-%d %H:%M')"
    done
    ;;
  --restore) shift; do_restore "${1:-}" ;;
  -h|--help) sed -n '2,28p' "$0" ;;
  *)          do_backup ;;
esac
