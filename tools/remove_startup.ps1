# remove_startup.ps1 - Hapus semua autostart B_gadget POS (lokal & tunnel)
# Penggunaan: powershell -ExecutionPolicy Bypass -File tools\remove_startup.ps1
Write-Output "=== HAPUS AUTOSTART B_gadget POS ==="

$startupDir=Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$files=@("B_gadget POS.lnk","B_gadget POS.lnk.off","B_gadget POS Tunnel.lnk","B_gadget POS Tunnel.lnk.off")
foreach($f in $files){
  $p=Join-Path $startupDir $f
  if(Test-Path $p){ Remove-Item $p -Force; Write-Output "OK hapus $f" } else { Write-Output "SKIP $f tidak ada" }
}

# Registry
foreach($name in @("B_gadget_POS","B_gadget_POS_Tunnel")){
  try{ reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v $name /f 2>&1 | Out-Null; Write-Output "OK hapus Registry $name" }catch{ Write-Output "SKIP Registry $name tidak ada" }
  # cek lagi dengan powershell method
  try{ Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name $name -ErrorAction SilentlyContinue; }catch{}
}

# Task Scheduler
foreach($tn in @("B_gadget_POS_AutoStart","B_gadget_POS_Tunnel_AutoStart")){
  try{ schtasks /delete /tn $tn /f 2>&1 | Out-Null; Write-Output "OK hapus Task $tn" }catch{ Write-Output "SKIP Task $tn tidak ada" }
  try{ Unregister-ScheduledTask -TaskName $tn -Confirm:$false -ErrorAction SilentlyContinue; }catch{}
}

Write-Output ""
Write-Output "=== SELESAI ==="
Get-ChildItem $startupDir -Force | Format-Table Name
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" 2>&1 | Select-String "B_gadget" | Write-Output
schtasks /query /fo LIST /v 2>&1 | Select-String -Pattern "B_gadget" | Write-Output
if(-not (Select-String -Pattern "B_gadget" -InputObject (schtasks /query /fo LIST /v 2>&1 | Out-String))){ Write-Output "[OK] Tidak ada Task B_gadget tersisa" }
