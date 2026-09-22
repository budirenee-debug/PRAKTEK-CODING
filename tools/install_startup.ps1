# install_startup.ps1 - Install Autostart LOKAL ONLY (tanpa tunnel)
# Penggunaan: powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1
# Akan membuat Startup LNK + Registry + Task Scheduler untuk run.bat (lokal)
$src="F:\VIBE CODING\CODING MJPRO\PRAKTEK\run.bat"
$desc="B_gadget POS AutoStart - LOKAL ONLY (tanpa tunnel). Untuk tunnel pakai run-tunnel.bat manual"
$startupDir=Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$lnkStartup=Join-Path $startupDir "B_gadget POS.lnk"
if(!(Test-Path $startupDir)){ New-Item -ItemType Directory -Path $startupDir -Force | Out-Null }

# Buat shortcut startup -> run.bat (LOKAL)
$sh=New-Object -COM WScript.Shell; $sc=$sh.CreateShortcut($lnkStartup)
$sc.TargetPath=$src; $sc.WorkingDirectory="F:\VIBE CODING\CODING MJPRO\PRAKTEK"; $sc.WindowStyle=1; $sc.Description=$desc; $sc.Save()
Write-Output "OK Startup LNK created -> $lnkStartup (LOKAL ONLY)"

# Registry Run (optional, untuk autostart juga)
try{ Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "B_gadget_POS" -Value "`"$src`"" -Force; Write-Output "OK Registry Run -> $src" }catch{ Write-Output "reg fail $_" }

# Task Scheduler (agar auto start setelah shutdown)
try{
  $action=New-ScheduledTaskAction -Execute $src -WorkingDirectory "F:\VIBE CODING\CODING MJPRO\PRAKTEK"
  $trigger=New-ScheduledTaskTrigger -AtLogOn
  $settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
  Register-ScheduledTask -TaskName "B_gadget_POS_AutoStart" -Action $action -Trigger $trigger -Settings $settings -Description $desc -Force | Out-Null
  Write-Output "OK Task Scheduler B_gadget_POS_AutoStart (LOKAL)"
}catch{ Write-Output "task fail $_" }

Get-ChildItem $startupDir | Format-Table Name
Write-Output ""
Write-Output "[INFO] Startup sekarang LOKAL ONLY. Tunnel tidak akan auto-jalan."
Write-Output "       Butuh tunnel? Jalankan manual: run-tunnel.bat atau tools\install_startup_tunnel.ps1"
