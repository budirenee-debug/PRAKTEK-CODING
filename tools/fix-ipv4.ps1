# Fix IPv4 only untuk B_gadget POS - paksa localhost -> 127.0.0.1
# Jalankan sebagai Administrator
param([switch]$Silent)
function Test-Admin {
  $id=[Security.Principal.WindowsIdentity]::GetCurrent()
  $p=New-Object Security.Principal.WindowsPrincipal $id
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
if(-not (Test-Admin)){
  Write-Warning "Butuh Administrator untuk fix hosts. Jalankan: powershell -Verb RunAs -File tools/fix-ipv4.ps1"
  if(-not $Silent){ pause }
  exit 1
}
$hosts="C:\Windows\System32\drivers\etc\hosts"
$bak="$hosts.bak.$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $hosts $bak -Force
Write-Output "Backup hosts -> $bak"
$content=Get-Content $hosts -Raw
# Hapus baris localhost lama yg masih aktif, ganti dengan IPv4 only
# Uncomment 127.0.0.1 localhost, comment ::1
$content = $content -replace "(?m)^\s*#\s*127\.0\.0\.1\s+localhost.*","127.0.0.1       localhost"
if($content -notmatch "(?m)^127\.0\.0\.1\s+localhost"){
  $content += "`r`n127.0.0.1       localhost`r`n"
}
$content = $content -replace "(?m)^\s*::1\s+localhost.*","#::1             localhost  # disabled IPv6 untuk B_gadget"
$content = $content -replace "(?m)^\s*#\s*::1\s+localhost.*","#::1             localhost  # disabled IPv6 untuk B_gadget"
Set-Content $hosts $content -Encoding ASCII -Force
Write-Output "Hosts fixed:"
Get-Content $hosts | Select-String "localhost" | Write-Output
# Prefer IPv4 via prefix policy (tanpa disable IPv6 total)
try{
  netsh interface ipv6 set prefixpolicy ::ffff:0:0/96 50 0 >$null 2>&1
  Write-Output "PrefixPolicy IPv4 prefer OK"
}catch{ Write-Output "PrefixPolicy skip: $_" }
# Flush DNS
ipconfig /flushdns | Out-Null
Write-Output "FlushDNS OK"
# Test
Write-Output "Test ping localhost (harus 127.0.0.1):"
ping -n 1 localhost | Write-Output
try{ $r=Resolve-DnsName localhost -ErrorAction Stop | Format-Table Name, IPAddress | Out-String; Write-Output $r }catch{ Write-Output "resolve fail $_" }
try{ $h=Invoke-WebRequest http://127.0.0.1:8000/health -TimeoutSec 2 -UseBasicParsing; Write-Output "Health 127.0.0.1 OK $($h.Content)" }catch{ Write-Output "Health 127 fail - start backend dulu: run.bat" }
Write-Output "Done - sekarang lokal pakai IPv4 only"
if(-not $Silent){ pause }
