#!/usr/bin/env bash
# ==============================================================================
#  deploy/sync-ubuntu.sh  -  Deploy aman ke server Ubuntu (B_gadget POS)
#
#  Jalankan DARI SERVER (via SSH):
#      cd /home/budirn/PRAKTEK && bash deploy/sync-ubuntu.sh
#
#  Prinsip:
#    - DB selalu di-backup (online backup, WAL aman) SEBELUM kode berubah
#    - Deploy yang gagal = rollback otomatis (kode + DB)
#    - File config tunnel (.cloudflared/config.yml) TIDAK pernah di-overwrite git
#    - Secret (.env) tidak pernah dicetak ke log
#    - Cuma 1 deploy boleh jalan pada saat bersamaan (flock)
# ==============================================================================
set -Eeuo pipefail

# --------------------------------------------------------------------------- #
#  KONFIGURASI                                                                #
# --------------------------------------------------------------------------- #
APP_NAME="b-gadget"
SERVICE="${APP_NAME}.service"
TUNNEL_SERVICE="cloudflared.service"

HEALTH_URL="http://127.0.0.1:8000/health"
HEALTH_WAIT_SEC=40
PUBLIC_URL="https://service.reneepsl.my.id/"

BACKUP_DIR="${HOME}/.backups/${APP_NAME}"
KEEP_BACKUPS=7
VENV_PY="${HOME}/PRAKTEK/venv/bin/python3"

# File yang JANGAN pernah ditimpa oleh git (config tunnel yang sedang hidup)
PROTECTED_PATHS=(
  ".cloudflared/config.yml"
  "backend/.env"
)

SUDO="sudo"   # ganti jadi "" + sudoers NOPASSWD kalau dipakai CI

# --------------------------------------------------------------------------- #
#  HELPER                                                                     #
# --------------------------------------------------------------------------- #
log()  { printf '[%s] %s\n' "$(date -u '+%H:%M:%S')" "$*"; }
warn() { printf '[%s] ⚠  %s\n' "$(date -u '+%H:%M:%S')" "$*" >&2; }
die()  { printf '[%s] ✖ FATAL: %s\n' "$(date -u '+%H:%M:%S')" "$*" >&2; exit 1; }

find_root() {
  for d in "${HOME}/PRAKTEK" /opt/PRAKTEK; do
    [ -d "$d/.git" ] && { printf '%s' "$d"; return 0; }
  done
  return 1
}

# sqlite3 CLI tidak dipakai - server tidak punya binary-nya.
# Semua operasi DB lewat modul sqlite3 di Python.
db_checkpoint() {
  [ -f "$DB_FILE" ] || return 0
  python3 - "$DB_FILE" <<'PY' 2>/dev/null || warn "checkpoint DB dilewati"
import sqlite3, sys
con = sqlite3.connect(sys.argv[1], timeout=30)
con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
con.close()
PY
}

db_backup() {  # $1 = file tujuan
  local dest="$1"
  python3 - "$DB_FILE" "$dest" <<'PY'
import sqlite3, sys, os
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(src, timeout=30)
try:
    s.execute("PRAGMA wal_checkpoint(TRUNCATE)")
except sqlite3.Error:
    pass
d = sqlite3.connect(dst)
with d:
    s.backup(d)                      # online backup, aman saat app jalan
chk = d.execute("PRAGMA quick_check").fetchone()[0]
d.close(); s.close()
if chk != "ok":
    raise SystemExit("backup corrupt: %s" % chk)
print("    backup ok: %s" % dst)
PY
}

db_restore() {  # $1 = file backup
  local src="$1"
  [ -f "$src" ] || die "file backup DB tidak ditemukan: $src"
  log "  restore DB dari: $src"
  "${SUDO}" systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  sleep 1
  rm -f "${DB_FILE}" "${DB_FILE}-wal" "${DB_FILE}-shm"
  cp "$src" "$DB_FILE"
  chown "$(id -un):$(id -gn)" "$DB_FILE" 2>/dev/null || true
  log "  DB dipulihkan dari backup"
}

health_check() {  # $1 = timeout detik
  local timeout_s="$1" waited=0
  while [ "$waited" -lt "$timeout_s" ]; do
    if curl -fsS --max-time 4 "$HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1; waited=$((waited + 1))
  done
  return 1
}

service_running() { systemctl is-active --quiet "$SERVICE"; }

# --------------------------------------------------------------------------- #
#  ROLLBACK                                                                   #
# --------------------------------------------------------------------------- #
ROLLBACK_DONE=0
do_rollback() {
  local prev_sha="$1" backup="$2"
  [ "$ROLLBACK_DONE" -eq 1 ] && return 0
  ROLLBACK_DONE=1
  warn "Deploy GAGAL - mulai rollback otomatis"
  cd "$ROOT"

  log "  [1/3] kembalikan kode ke $prev_sha"
  git reset --hard "$prev_sha" >/dev/null 2>&1 || warn "git reset --hard gagal"

  log "  [2/3] pulihkan DB"
  db_restore "$backup"

  log "  [3/3] restart service"
  "${SUDO}" systemctl daemon-reload >/dev/null 2>&1 || true
  "${SUDO}" systemctl restart "$SERVICE" >/dev/null 2>&1 || true
  if ! systemctl is-active --quiet "$TUNNEL_SERVICE"; then
    "${SUDO}" systemctl restart "$TUNNEL_SERVICE" >/dev/null 2>&1 || true
  fi

  if health_check 40; then
    warn "Rollback BERHASIL - server kembali ke versi sebelumnya & sehat"
  else
    warn "Rollback TIDAK sehat - perlu intervene manual:"
    warn "  journalctl -u $SERVICE -n 50 --no-pager"
  fi
}

# --------------------------------------------------------------------------- #
#  LOCK                                                                       #
# --------------------------------------------------------------------------- #
LOCK_FILE="/var/lock/${APP_NAME}-deploy.lock"
# PENTING: jangan `exec 9>"$LOCK_FILE" 2>/dev/null`.
# `exec` tanpa command = redirect Permanen untuk SELURUH sisa script,
# jadi stderr (pesan die/warn) ikut hilang. Untuk fallback cukup cek "-r".
if ! { exec 9>"$LOCK_FILE"; } 2>/dev/null; then
  if ! { exec 9>"${HOME}/.${APP_NAME}-deploy.lock"; } 2>/dev/null; then
    die "Tidak bisa membuat lock file untuk deploy."
  fi
fi
if ! flock -n 9; then
  die "Ada deploy lain yang sedang jalan. Tunggu selesai."
fi

# --------------------------------------------------------------------------- #
#  0. PREFLIGHT                                                               #
# --------------------------------------------------------------------------- #
ROOT="$(find_root)" || die "Repo PRAKTEK tidak ditemukan di ${HOME}/PRAKTEK atau /opt/PRAKTEK"
cd "$ROOT"

DB_FILE="${ROOT}/backend/b_gadget.db"
ENV_FILE="${ROOT}/backend/.env"
TS="$(date -u '+%Y%m%d-%H%M%S')"
BACKUP_FILE="${BACKUP_DIR}/b_gadget-${TS}.db"

log "=== DEPLOY ${APP_NAME} ==="
log "root     : $ROOT"
log "waktu    : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# .env WAJIB ada. Kalau hilang = STOP, jangan bikin dari .example diam-diam
# (dulu script lama menyalin .example yg isinya SECRET_KEY dummy ke produksi)
if [ ! -s "$ENV_FILE" ]; then
  die "$ENV_FILE tidak ada/kosong. Isi secret dulu sebelum deploy (JANGAN pakai .example untuk produksi)."
fi
if ! grep -qE '^[[:space:]]*SECRET_KEY=' "$ENV_FILE"; then
  die "$ENV_FILE tidak punya SECRET_KEY. Deploy dibatalkan."
fi
log "env      : OK (secret tidak ditampilkan)"

# Repo harus ada perubahan? kalau iya bebas deploy
if [ -n "$(git status --porcelain --untracked-files=no -- "${PROTECTED_PATHS[@]}" 2>/dev/null)" ]; then
  warn "File config lokal punya perubahan (masih aman, tidak akan di-overwrite):"
  git status --porcelain -- "${PROTECTED_PATHS[@]}" | sed 's/^/         /' >&2
  warn "Supaya aman dari git pull, jalankan sekali:"
  warn "  git update-index --skip-worktree ${PROTECTED_PATHS[*]}" >&2
fi

# unit service harus terinstall.
# JANGAN `systemctl list-unit-files | grep -q ...` -> grep -q keluar duluan
# bikin systemctl kena SIGPIPE, dan pipefail bikin script exit.
systemctl cat "$SERVICE" >/dev/null 2>&1 || die "Unit ${SERVICE} tidak terinstall."

PREV_SHA="$(git rev-parse HEAD)"
log "commit   : sebelum = ${PREV_SHA:0:8}"

# --------------------------------------------------------------------------- #
#  1. BACKUP DATABASE                                                          #
# --------------------------------------------------------------------------- #
mkdir -p "$BACKUP_DIR"
if [ -f "$DB_FILE" ]; then
  db_checkpoint
  if db_backup "$BACKUP_FILE" 2>/dev/null; then
    log "backup   : $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
  else
    die "Backup DB GAGAL - deploy dibatalkan (tidak mau jalan tanpa backup)."
  fi
  # pangkas backup lama, sisakan N terakhir
  # set -e + pipefail: pastikan pipeline di bawah tidak menggagalkan script
  shopt -s nullglob
  for old in $(ls -1t "${BACKUP_DIR}"/*.db 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))"); do
    if rm -f "$old"; then log "  prunes  : $(basename "$old")"; fi
  done
  shopt -u nullglob
else
  warn "DB belum ada, lewati backup"
fi

# --------------------------------------------------------------------------- #
#  2. PULL KODE                                                               #
# --------------------------------------------------------------------------- #
# GIT_TERMINAL_PROMPT=0 -> kalau butuh auth, gagal CEPAT, jangan nge-hang
# (penting kalau nanti dijalankan dari CI yang non-interaktif)
export GIT_TERMINAL_PROMPT=0

log "fetch    : git fetch origin"
if ! git fetch --quiet origin; then
  die "git fetch GAGAL (repo private? token expired?). Deploy dibatalkan."
fi

REMOTE_SHA="$(git rev-parse origin/main 2>/dev/null || echo '')"
if [ -z "$REMOTE_SHA" ]; then
  warn "Branch origin/main tidak ada, deploy dibatalkan"
  exit 1
fi
log "commit   : remote  = ${REMOTE_SHA:0:8}"

if [ "$REMOTE_SHA" = "$PREV_SHA" ]; then
  log "kode     : sudah paling baru, tidak ada yang di-deploy"
  exit 0
fi

log "  changelog:"
git log --oneline --no-decorate "${PREV_SHA}..${REMOTE_SHA}" | sed 's/^/           /'

if ! git merge-base --is-ancestor "$PREV_SHA" "$REMOTE_SHA"; then
  die "Ada force-push / branch divergen di remote. Deploy manual, jangan script."
fi

log "pull     : git merge --ff-only origin/main"
if ! git merge --ff-only "origin/main"; then
  die "git merge --ff-only gagal (kemungkinan bentrok). Tree lu bermasalah - deploy dibatalkan."
fi
NEW_SHA="$(git rev-parse HEAD)"

# --------------------------------------------------------------------------- #
#  3. DEPENDENCI (hanya kalau requirements.txt berubah)                       #
# --------------------------------------------------------------------------- #
if git diff --quiet "$PREV_SHA" "$NEW_SHA" -- backend/requirements.txt; then
  log "deps     : requirements.txt tidak berubah, lewati pip"
else
  log "deps     : requirements.txt berubah -> pip install"
  PIP="$VENV_PY"
  [ -x "$PIP" ] || PIP="python3"
  if ! "$PIP" -m pip install --quiet --disable-pip-version-check -r backend/requirements.txt; then
    warn "pip install GAGAL -> rollback"
    do_rollback "$PREV_SHA" "$BACKUP_FILE"
    exit 1
  fi
  log "deps     : selesai"
fi

# --------------------------------------------------------------------------- #
#  4. RESTART SERVICE                                                          #
# --------------------------------------------------------------------------- #
if [ -f "$ROOT/deploy/${APP_NAME}.service" ]; then
  if ! diff -q "$ROOT/deploy/${APP_NAME}.service" "/etc/systemd/system/${APP_NAME}.service" >/dev/null 2>&1; then
    warn "Unit ${APP_NAME}.service di repo BERUBAH dari yang terinstall."
    warn "Review manual dulu:  diff $ROOT/deploy/${APP_NAME}.service /etc/systemd/system/${APP_NAME}.service"
  fi
fi

log "restart  : systemctl restart ${SERVICE}"
"${SUDO}" systemctl restart "$SERVICE"

# tunnel harus tetap hidup. cloudflared.service sengaja dibuat Wants=
# (bukan Requires=) supaya restart app TIDAK mematikan tunnel publik.
if ! systemctl is-active --quiet "$TUNNEL_SERVICE"; then
  warn "Tunnel mati, nyalakan ulang ${TUNNEL_SERVICE}"
  "${SUDO}" systemctl restart "$TUNNEL_SERVICE"
fi

# --------------------------------------------------------------------------- #
#  5. HEALTH CHECK + ROLLBACK OTOMATIS                                       #
# --------------------------------------------------------------------------- #
log "health   : tunggu ${HEALTH_WAIT_SEC}s sampai /health OK ..."
if health_check "$HEALTH_WAIT_SEC"; then
  log "health   : $(curl -fsS --max-time 4 "$HEALTH_URL")"
else
  warn "HEALTH CHECK GAGAL setelah ${HEALTH_WAIT_SEC}s"
  warn "log error terakhir:"
  { journalctl -u "$SERVICE" -n 25 --no-pager 2>/dev/null || journalctl --user -u "$SERVICE" -n 25 --no-pager 2>/dev/null || echo "(tidak bisa baca journal)"; } | sed 's/^/           /' >&2
  do_rollback "$PREV_SHA" "$BACKUP_FILE"
  exit 1
fi

# cek juga sisi publik (tunnel Cloudflare), ini cuma warning
if code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "$PUBLIC_URL" 2>/dev/null)" \
   && [ "$code" = "200" ]; then
  log "publik   : ${PUBLIC_URL} -> HTTP 200"
else
  warn "Publik ${PUBLIC_URL} -> HTTP ${code:-timeout} (cek tunnel; app lokal sehat)"
fi

# --------------------------------------------------------------------------- #
#  SELESAI                                                                     #
# --------------------------------------------------------------------------- #
log "db       : $(du -h "$DB_FILE" 2>/dev/null | cut -f1 || echo '-')  |  backup: $(basename "${BACKUP_FILE:-none}")"
log ""
log "✅ DEPLOY SUKSES  ${PREV_SHA:0:8} -> ${NEW_SHA:0:8}"
log ""
log "Rollback manual:"
log "  git reset --hard ${PREV_SHA}"
log "  cp ${BACKUP_FILE} ${DB_FILE} && sudo systemctl restart ${APP_NAME}"
exit 0