<# : 2>nul
@echo off
:: ==========================================================
::  B_gadget - Cek Koneksi PC Admin (sekali double-click)
::  - Tes HEALTH publik (tunnel) + HEALTH via LAN
::  - Tes LOGIN + token + /me + /stores + /services
::  - Password diketik aman (tidak tampil di layar)
::  - Hasil mentah tersimpan di %TEMP%\b_gadget_cek
::  - Foto seluruh layar ini lalu kirim ke saya
:: ==========================================================
chcp 65001 >nul
title B_gadget - Cek Koneksi PC Admin
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=[IO.File]::ReadAllText('%~f0'); Invoke-Expression $c"
pause
exit /b %errorlevel%
#>
# ================= PowerShell diagnostic =================
# (bagian ini dibaca PowerShell saja; batch berhenti di exit di atas)
$BASE = 'https://service.reneepsl.my.id'
$LAN  = 'http://192.168.0.10:8000'
$D = Join-Path $env:TEMP 'b_gadget_cek'
if (-not (Test-Path $D)) { New-Item -ItemType Directory -Path $D | Out-Null }

Write-Output '========================================'
Write-Output (' B_gadget - Cek Koneksi PC Admin   ' + (Get-Date -Format 'dd/MM/yyyy HH:mm'))
Write-Output '========================================'
Write-Output (" Hasil mentah: " + $D)
Write-Output ' Jawab Username + Password, lalu FOTO layar ini.'
Write-Output '========================================'
Write-Output ''

function Get-Api($url, $token, $timeoutSec) {
  $h = @{}
  if ($token) { $h['Authorization'] = 'Bearer ' + $token }
  try {
    $r = Invoke-RestMethod -Uri $url -Headers $h -TimeoutSec $timeoutSec
    return @{ ok = $true; code = 200; body = ($r | ConvertTo-Json -Depth 5 -Compress); json = $r }
  } catch {
    $code = 0
    try { $code = [int]$_.Exception.Response.StatusCode } catch {}
    $msg = ''
    try { $msg = $_.ErrorDetails.Message } catch {}
    if (-not $msg) { $msg = $_.Exception.Message }
    return @{ ok = $false; code = $code; body = [string]$msg; json = $null }
  }
}
function Short($s, $n) {
  $s = [string]$s
  if ($s.Length -gt $n) { return $s.Substring(0, $n) + '...' }
  return $s
}

Write-Output ("[1/5] HEALTH publik: " + $BASE + "/health")
$h1 = Get-Api ($BASE + '/health') '' 12
Write-Output ("  HTTP " + $h1.code + "  " + (Short $h1.body 120))
$h1.body | Out-File (Join-Path $D 'health.txt') -Encoding ascii
Write-Output ''
Write-Output ("[2/5] HEALTH via LAN: " + $LAN + "/health (info tambahan)")
$h2 = Get-Api ($LAN + '/health') '' 5
Write-Output ("  HTTP " + $h2.code + "  " + (Short $h2.body 120))
$h2.body | Out-File (Join-Path $D 'lan.txt') -Encoding ascii
Write-Output ''

Write-Output '[3/5] LOGIN - pakai user yang dipakai di PC admin'
$u = Read-Host 'Username (mis. admin)'
$sec = Read-Host -AsSecureString 'Password'
$pw = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
$loginBody = @{ username = $u; password = $pw } | ConvertTo-Json
$login = $null
try {
  $login = Invoke-RestMethod -Uri ($BASE + '/api/auth/login') -Method Post -ContentType 'application/json' -Body $loginBody -TimeoutSec 15
  'LOGIN_OK' | Out-File (Join-Path $D 'login.status') -Encoding ascii
  ($login | ConvertTo-Json -Depth 5) | Out-File (Join-Path $D 'login.json') -Encoding ascii
  Write-Output '  Hasil: LOGIN_OK'
} catch {
  $code = 0
  try { $code = [int]$_.Exception.Response.StatusCode } catch {}
  $msg = ''
  try { $msg = $_.ErrorDetails.Message } catch {}
  if (-not $msg) { $msg = $_.Exception.Message }
  ('LOGIN_GAGAL_HTTP_' + $code) | Out-File (Join-Path $D 'login.status') -Encoding ascii
  [string]$msg | Out-File (Join-Path $D 'login.err') -Encoding ascii
  Write-Output ("  Hasil: LOGIN_GAGAL_HTTP_" + $code)
  Write-Output ("  Pesan server: " + (Short $msg 300))
}
Write-Output ''
$LOGIN_OK = ($login -ne $null)

if ($LOGIN_OK) {
  $token = [string]$login.access_token
  $store = [string]$login.primary_store_id
  Write-Output '[4/5] Token ADA'
  Write-Output ('  user: ' + $login.username + '  role: ' + $login.role + '  primary_store_id: ' + $store)
  try {
    $names = ($login.stores | ForEach-Object { "$($_.id)=$($_.nama)($($_.kode))" }) -join ', '
    Write-Output ('  toko: ' + (Short $names 250))
  } catch {}
  Write-Output ''
  Write-Output '[5/5] Tes API pakai token fresh (me, stores, services)...'
  $me = Get-Api ($BASE + '/api/auth/me') $token 12
  Write-Output ("  /me: HTTP " + $me.code + "  " + (Short $me.body 200))
  $me.body | Out-File (Join-Path $D 'me.txt') -Encoding ascii
  $st = Get-Api ($BASE + '/api/stores') $token 12
  $stInfo = Short $st.body 200
  try { if ($st.json) { $stInfo = 'jumlah toko: ' + @($st.json).Count + '  ' + $stInfo } } catch {}
  Write-Output ("  /stores: HTTP " + $st.code + "  " + $stInfo)
  $st.body | Out-File (Join-Path $D 'stores.txt') -Encoding ascii
  $sv = Get-Api ($BASE + '/api/services?limit=1&store_id=' + $store) $token 12
  $svInfo = Short $sv.body 200
  try { if ($sv.json) { $svInfo = 'baris: ' + @($sv.json).Count + '  ' + $svInfo } } catch {}
  Write-Output ("  /services: HTTP " + $sv.code + "  " + $svInfo)
  $sv.body | Out-File (Join-Path $D 'svc.txt') -Encoding ascii
  Write-Output ''
}

Write-Output '========================================'
Write-Output ' KESIMPULAN (baca yang cocok)'
Write-Output '========================================'
if ($h1.code -ne 200) {
  Write-Output ' [A] PUTUS TOTAL - PC ini tidak sampai ke server publik.'
  Write-Output '     - Cek kabel/wifi PC admin, coba buka google.com'
  if ($h2.code -eq 200) {
    Write-Output '     - LAN ke server OK tapi publik gagal = tunnel Cloudflare putus.'
    Write-Output '       Kabari saya + operator server.'
    Write-Output ("     - Sementara bisa buka via LAN: " + $LAN + "/frontend/login.html")
  } else {
    Write-Output '     - LAN juga gagal = jaringan lokal PC/server bermasalah.'
  }
} elseif (-not $LOGIN_OK) {
  Write-Output ' [B] LOGIN DITOLAK - server bisa dihubungi, tapi user/password ditolak.'
  Write-Output '     - "Username atau password salah" = salah ketik / beda user.'
  Write-Output '     - "Akun nonaktif / belum disetujui" = minta owner approve.'
  Write-Output '     - Kirim foto ini ke saya.'
} elseif ($sv.code -eq 200) {
  Write-Output ' [C] SERVER OK 100% - login + data lolos pakai token fresh.'
  Write-Output '     Berarti masalahnya di BROWSER PC admin (token lama 2 jam'
  Write-Output '     habis / cache lama), bukan di server Ubuntu.'
  Write-Output '     Lakukan di browser dashboard:'
  Write-Output '       1. Logout, 2. Login lagi, 3. Ctrl+Shift+R, 4. klik Sync.'
} elseif ($sv.code -eq 403 -or $sv.code -eq 404) {
  Write-Output ' [D] TOKO BERMASALAH - login ok tapi data toko ditolak.'
  Write-Output '     Kemungkinan store_id basi / bukan anggota / toko nonaktif.'
  Write-Output '     Kirim foto ini + username ke saya, saya benerin dari server.'
} else {
  Write-Output ' [E] HASIL CAMPURAN - kirim foto ini ke saya, saya analisa.'
}
Write-Output '========================================'
Write-Output (" File mentah: " + $D + " (health.txt, me.txt, stores.txt, svc.txt)")
Write-Output ' SELESAI. Foto seluruh layar ini, kirim ke saya.'
Write-Output '========================================'
