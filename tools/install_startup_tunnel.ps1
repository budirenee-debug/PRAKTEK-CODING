# install_startup_tunnel.ps1 - Install Autostart LOKAL+TUNNEL (untuk server/publik)
# Penggunaan: powershell -ExecutionPolicy Bypass -File tools\install_startup_tunnel.ps1
# Akan membuat Startup LNK + Registry + Task Scheduler untuk run-tunnel.bat
$src="F:\VIBE CODING\CODING MJPRO\PRAKTEK\run-tunnel.bat"
$desc="B_gadget POS AutoStart - LOKAL+TUNNEL (publik service.reneepsl.my.id)"
$startupDir=Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$lnkStartup=Join-Path $startupDir "B_gadget POS Tunnel.lnk"
if(!(Test-Path $startupDir)){ New-Item -ItemType Directory -Path $startupDir -Force | Out-Null }

$sh=New-Object -COM WScript.Shell; $sc=$sh.CreateShortcut($lnkStartup)
$sc.TargetPath=$src; $sc.WorkingDirectory="F:\VIBE CODING\CODING MJPRO\PRAKTEK"; $sc.WindowStyle=1; $sc.Description=$desc; $sc.Save()
Write-Output "OK Startup LNK created -> $lnkStartup (TUNNEL)"

try{ Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "B_gadget_POS_Tunnel" -Value "`"$src`"" -Force; Write-Output "OK Registry Run Tunnel -> $src" }catch{ Write-Output "reg fail $_" }

try{
  $action=New-ScheduledTaskAction -Execute $src -WorkingDirectory "F:\VIBE CODING\CODING MJPRO\PRAKTEK"
  $trigger=New-ScheduledTaskTrigger -AtLogOn
  $settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
  Register-ScheduledTask -TaskName "B_gadget_POS_Tunnel_AutoStart" -Action $action -Trigger $trigger -Settings $settings -Description $desc -Force | Out-Null
  Write-Output "OK Task Scheduler B_gadget_POS_Tunnel_AutoStart"
}catch{ Write-Output "task fail $_" }

Get-ChildItem $startupDir | Format-Table Name
