#!/usr/bin/env bash
# ==============================================================================
#  deploy/print-log.sh — Histori print DETAIL (nama file + jam) di server Ubuntu
#
#  Sumber data: CUPS page_log (pencatatan detail aktif sejak 2026-10-14):
#    PageLogFormat %p %u %j %T %P %C %{job-billing} %{job-originating-host-name}
#                  %{job-name} %{media} %{sides}
#  Lihat docs/PRINT-LOG.md untuk config server & format kolom.
#
#  Pakai:
#    DI SERVER :  cd ~/PRAKTEK && bash deploy/print-log.sh [-n 20] [--json]
#    DARI PC   :  ssh brserver-luar "bash ~/PRAKTEK/deploy/print-log.sh"
#                 (atau double-click tools/cek-print-log.ps1 di Windows)
#
#  Read-only, tanpa sudo. Job lama (sebelum 2026-10-14) tidak punya nama file
#  karena page logging dulu mati — tampil dari `lpstat` dengan nama "-".
# ==============================================================================
set -Eeuo pipefail

LIMIT=20
JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    -n) LIMIT="${2:-20}"; shift 2 ;;
    --json) JSON=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "argumen tidak dikenal: $1 (pakai -h)" >&2; exit 1 ;;
  esac
done

# Lokasi log CUPS (bisa di-override untuk testing: CUPS_LOGDIR=/tmp/x bash deploy/print-log.sh)
LOGDIR="${CUPS_LOGDIR:-/var/log/cups}"
PAGELOG="$LOGDIR/page_log"
PAGELOG1="$LOGDIR/page_log.1"

# --- Jalur utama: page_log ada (sudah ada print sejak fitur aktif) -------------
if [ -s "$PAGELOG" ] || [ -s "$PAGELOG1" ]; then
  # Gabung log putar (.1 = lebih lama) + log aktif, lalu kelompokkan per job.
  # Kolom: printer user job [tgl jam] hal copy billing host NAMA-FILE... media sides
  { [ -f "$PAGELOG1" ] && cat "$PAGELOG1"; [ -f "$PAGELOG" ] && cat "$PAGELOG"; } 2>/dev/null \
  | awk -v limit="$LIMIT" -v json="$JSON" '
    {
      t = $4" "$5; gsub(/\[/, "", t); gsub(/\]/, "", t);
      j = $3;
      name = "";
      for (i = 10; i <= NF - 2; i++) name = name ((i > 10) ? " " : "") $i;
      if (name == "") name = "-";
      if (!(j in seen)) { seen[j] = 1; ord[++n] = j; P[j] = $1; U[j] = $2; T[j] = t; C[j] = $7; N[j] = name; G[j] = 0; }
      G[j]++;
    }
    END {
      start = (n > limit) ? n - limit + 1 : 1;
      if (json == 1) {
        printf "[";
        for (k = start; k <= n; k++) {
          j = ord[k]; nm = N[j];
          gsub(/\\/, "\\\\", nm); gsub(/"/, "\\\"", nm);
          printf "%s{\"job\":%s,\"waktu\":\"%s\",\"printer\":\"%s\",\"user\":\"%s\",\"file\":\"%s\",\"halaman\":%d,\"copies\":%s}",
            (k > start ? "," : ""), j, T[j], P[j], U[j], nm, G[j], C[j];
        }
        printf "]\n";
      } else {
        printf "%-6s | %-24s | %-24s | %-4s | %-4s | %s\n", "JOB", "WAKTU", "PRINTER / USER", "HAL", "COPY", "NAMA FILE";
        for (k = start; k <= n; k++) {
          j = ord[k];
          printf "%-6s | %-24s | %s / %s | %-4d | %-4s | %s\n", j, T[j], P[j], U[j], G[j], C[j], N[j];
        }
      }
    }'
  exit 0
fi

# --- Fallback: page_log belum ada (belum ada print sejak fitur aktif) ---------
msg="(!) page_log belum ada - belum ada print sejak pencatatan detail aktif (2026-10-14)."
if [ "$JSON" -eq 1 ]; then
  echo "$msg" >&2
else
  echo "$msg"
  echo "    Histori lama di bawah ini TANPA nama file (logging dulu mati)."
  echo ""
fi

lpstat -W completed -o 2>/dev/null | awk -v json="$JSON" '
  {
    n = split($1, a, "-"); job = a[n]; printer = a[1];
    for (i = 2; i < n; i++) printer = printer"-"a[i];
    t = ""; for (i = 4; i <= NF; i++) t = t ((i > 4) ? " " : "") $i;
    R[++m] = sprintf("%s|%s|%s|%s|%s|%s", job, t, printer, $2, $3, "-");
  }
  END {
    if (json == 1) {
      printf "[";
      for (k = 1; k <= m; k++) {
        split(R[k], f, "|");
        printf "%s{\"job\":%s,\"waktu\":\"%s\",\"printer\":\"%s\",\"user\":\"%s\",\"ukuran_bytes\":%s,\"file\":\"-\"}",
          (k > 1 ? "," : ""), f[1], f[2], f[3], f[4], f[5];
      }
      printf "]\n";
    } else {
      printf "%-6s | %-30s | %-24s | %-10s | %s\n", "JOB", "WAKTU", "PRINTER / USER", "UKURAN", "NAMA FILE";
      for (k = 1; k <= m; k++) {
        split(R[k], f, "|");
        printf "%-6s | %-30s | %s / %s | %-10s | %s\n", f[1], f[2], f[3], f[4], f[5], f[6];
      }
    }
  }'
