@echo off
setlocal
chcp 65001 >nul
title B_gadget - Cloudflare Tunnel

echo ========================================
echo  B_gadget - Cloudflare Tunnel Runner
echo ========================================
echo.

:: Cek cloudflared terinstall (winget install di C:\Program Files (x86)\cloudflared\cloudflared.exe)
set CLOUDFLARED_EXE=C:\Program Files (x86)\cloudflared\cloudflared.exe
if not exist "%CLOUDFLARED_EXE%" (
  :: fallback cek di PATH
  where cloudflared >nul 2>&1
  if %errorlevel% neq 0 (
    echo [ERROR] cloudflared tidak ditemukan.
    echo Cek: "%CLOUDFLARED_EXE%"
    echo Install dulu:
    echo   winget install --id Cloudflare.cloudflared -e
    echo   atau download: https://developers.cloudflare.com/cloudflare-one/connections/connect/install/
    echo   Jika sudah install tapi tetap error, restart terminal / cek PATH
    echo.
    pause
    exit /b 1
  ) else (
    set CLOUDFLARED_EXE=cloudflared
  )
)

:: Cek backend jalan di 8000
echo [INFO] Cek backend http://localhost:8000/health ...
powershell -Command "try { Invoke-WebRequest http://localhost:8000/health -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
  echo [WARN] Backend belum jalan di port 8000!
  echo        Jalankan dulu run.bat di window lain, baru jalankan tunnel ini.
  echo.
)

echo [INFO] Pilih mode tunnel:
echo   1. Quick Tunnel (tanpa domain, URL random *.trycloudflare.com) - paling gampang
echo   2. Named Tunnel (pakai domain sendiri + config.yml)
echo.
choice /c 12 /m "Pilih 1 atau 2"
if %errorlevel%==2 goto NAMED

:QUICK
echo.
echo [INFO] Menjalankan Quick Tunnel ke http://localhost:8000 ...
echo       Tekan Ctrl+C untuk stop.
echo.
"%CLOUDFLARED_EXE%" tunnel --url http://localhost:8000
goto END

:NAMED
echo.
echo [INFO] Menjalankan Named Tunnel: b-gadget
echo       Config: .cloudflared/config.yml
echo       Domain: service.reneepsl.my.id (utama) + reneepsl.my.id + www.reneepsl.my.id
echo       Pastikan sudah: cloudflared tunnel create b-gadget ^&^& cloudflared tunnel route dns b-gadget service.reneepsl.my.id
echo.
:: Jika config di project, pakai --config eksplisit (relative path aman untuk folder dengan spasi "CODING MJPRO")
"%CLOUDFLARED_EXE%" tunnel --config .cloudflared/config.yml run b-gadget
goto END

:END
pause


