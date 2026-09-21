$src="F:\VIBE CODING\CODING MJPRO\PRAKTEK\run.bat"
$lnkDesktop=Join-Path $env:USERPROFILE "Desktop\B_gadget POS.lnk"
$startupDir=Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$lnkStartup=Join-Path $startupDir "B_gadget POS.lnk"
if(!(Test-Path $startupDir)){ New-Item -ItemType Directory -Path $startupDir -Force | Out-Null }
if(Test-Path $lnkDesktop){ Copy-Item $lnkDesktop $lnkStartup -Force; Write-Output "OK Startup copied from Desktop" }
else{
  $sh=New-Object -COM WScript.Shell; $sc=$sh.CreateShortcut($lnkStartup)
  $sc.TargetPath=$src; $sc.WorkingDirectory="F:\VIBE CODING\CODING MJPRO\PRAKTEK"; $sc.WindowStyle=1; $sc.Description="B_gadget POS AutoStart"; $sc.Save()
  Write-Output "OK Startup created"
}
try{ Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "B_gadget_POS" -Value "`"$src`"" -Force; Write-Output "OK Registry Run" }catch{ Write-Output "reg fail $_" }
Get-ChildItem $startupDir | Format-Table Name
