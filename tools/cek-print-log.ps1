# tools/cek-print-log.ps1 — Lihat histori print DETAIL server dari PC Windows
#
#  Pakai:
#    powershell -File tools\cek-print-log.ps1            (20 job terakhir, via Tailscale)
#    powershell -File tools\cek-print-log.ps1 -Limit 50
#    powershell -File tools\cek-print-log.ps1 -Json
#    powershell -File tools\cek-print-log.ps1 -Lan       (via LAN 192.168.0.10)
#
#  Prasyarat: script deploy/print-log.sh sudah ter-pull di server
#  (di server: cd ~/PRAKTEK && git pull). Kalau belum ada, script ini
#  otomatis fallback ke `lpstat` + kasih hint deploy.
param([int]$Limit=20,[switch]$Json,[switch]$Lan,[string]$SshHost="")
if($SshHost -eq ""){ $SshHost = if($Lan){ "bgadget-srv" } else { "brserver-luar" } }
$arg = "-n $Limit"; if($Json){ $arg += " --json" }
$probe = ssh -o BatchMode=yes -o ConnectTimeout=8 $SshHost "test -f ~/PRAKTEK/deploy/print-log.sh && echo ADA || echo BELUM" 2>&1
if($probe -match "ADA"){
  ssh -o BatchMode=yes -o ConnectTimeout=8 $SshHost "bash ~/PRAKTEK/deploy/print-log.sh $arg" 2>&1
} else {
  Write-Output "[!] deploy/print-log.sh belum ada di server ($SshHost)."
  Write-Output "    Deploy dulu di server: cd ~/PRAKTEK && git pull origin main"
  Write-Output "    Fallback histori kasar (tanpa nama file):"
  ssh -o BatchMode=yes -o ConnectTimeout=8 $SshHost "lpstat -W completed -o 2>&1 | head -n $Limit" 2>&1
}
