@echo off
setlocal
chcp 65001 >nul
title B_gadget POS - LAN Review (satu jaringan)

:: ==========================================================
::  B_gadget POS - LAN Review Runner (SATU JARINGAN)
::  - Backend : FastAPI http://0.0.0.0:8000 (bisa diakses HP/
::              laptop lain yang konek WiFi/LAN yang SAMA)
::  - Tanpa Tunnel / Cloudflare (tidak publik ke internet)
::  - Tanpa Deploy ke Ubuntu (server tidak tersentuh, DB lokal)
::  - Untuk coding review sebelum deploy
::  - Ngoding sendiri? pakai run.bat (localhost only)
::  - Butuh publik? pakai run-tunnel.bat / run-tunnel.sh
:: ==========================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "PORT=8000"
set "LOGIN_PATH=/frontend/login.html"

echo ========================================
echo  B_gadget POS - LAN Review
echo  Root   : %ROOT%
echo  Mode   : LAN (satu jaringan, tanpa tunnel)
echo ========================================
echo.

:: ---------- 1. Cari Python ----------
set "PYTHON_EXE="
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYTHON_EXE (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=py"
)
if not defined PYTHON_EXE (
  echo [ERROR] Python tidak ditemukan. Install dulu:
  echo         winget install Python.Python.3.12 --silent
  pause
  exit /b 1
)
echo [INFO] Python : %PYTHON_EXE%
"%PYTHON_EXE%" --version
if errorlevel 1 (
  echo [ERROR] Python tidak bisa dijalankan: %PYTHON_EXE%
  pause
  exit /b 1
)

:: ---------- 2. Cek backend ----------
if not exist "%BACKEND%\app\main.py" (
  echo [ERROR] backend\app\main.py tidak ditemukan di %BACKEND%
  pause
  exit /b 1
)
if not exist "%BACKEND%\requirements.txt" (
  echo [ERROR] backend\requirements.txt tidak ditemukan.
  pause
  exit /b 1
)

:: ---------- 3. Dependencies ----------
echo [INFO] Cek dependencies fastapi+uvicorn ...
"%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] fastapi/uvicorn belum terinstall.
  echo         Jalankan manual: %PYTHON_EXE% -m pip install -r backend\requirements.txt
  pause
  exit /b 1
) else (
  echo [INFO] Dependencies OK.
)

:: ---------- 4. Cek port ----------
set "PORT_BUSY=0"
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  set "PORT_BUSY=1"
  echo [WARN] Port %PORT% sudah LISTENING ^(server mungkin sudah jalan^).
  echo        Cek: http://127.0.0.1:%PORT%/health
  echo        -^> Browser akan tetap dibuka, backend tidak di-start ulang.
  echo.
)

:: ---------- 5. Deteksi IP LAN (murni ipconfig, tanpa PowerShell) ----------
echo [INFO] Deteksi IP LAN PC ini (untuk dibuka dari HP/laptop lain):
echo ----------------------------------------------------------------
ipconfig | findstr /c:"IPv4"
echo ----------------------------------------------------------------
set "LAN_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=* delims= " %%b in ("%%a") do (
    echo %%b | findstr /b /c:"192.168." /c:"10." >nul 2>nul
    if not errorlevel 1 if not defined LAN_IP set "LAN_IP=%%b"
    echo %%b | findstr /r /b /c:"172\.1[6-9]\." /c:"172\.2[0-9]\." /c:"172\.3[0-1]\." >nul 2>nul
    if not errorlevel 1 if not defined LAN_IP set "LAN_IP=%%b"
  )
)
if defined LAN_IP (
  echo.
  echo  ==================================================
  echo   REVIEW DARI HP/LAPTOP LAIN ^(WiFi yang SAMA^):
  echo   http://%LAN_IP%:%PORT%%LOGIN_PATH%
  echo  ==================================================
  echo   Docs  : http://%LAN_IP%:%PORT%/docs
  echo   Health: http://%LAN_IP%:%PORT%/health
) else (
  echo.
  echo [WARN] IP LAN 192.168.x.x / 10.x.x.x tidak ketemu.
  echo        - Pastikan WiFi/LAN konek, lalu jalankan lagi.
  echo        - Atau pakai salah satu IP di daftar atas:
  echo          http://IP-TADI:%PORT%%LOGIN_PATH%
)
echo.
echo [INFO] Akses dari PC ini tetap: http://127.0.0.1:%PORT%%LOGIN_PATH%
echo [INFO] Server Ubuntu TIDAK tersentuh (tanpa tunnel, tanpa deploy).
echo.

:: ---------- 6. Cek firewall ----------
netsh advfirewall firewall show rule name="B_gadget POS 8000" 2>nul | findstr /i "Allow" >nul 2>nul
if errorlevel 1 (
  echo [WARN] Rule firewall "B_gadget POS 8000" belum ada.
  echo        Kalau HP lain tidak bisa buka, jalankan CMD Admin sekali:
  echo        netsh advfirewall firewall add rule name="B_gadget POS 8000" dir=in action=allow protocol=TCP localport=%PORT% profile=private
  echo        Lalu pastikan pilih Network Private, bukan Public.
  echo.
) else (
  echo [INFO] Firewall rule port %PORT% OK.
  echo.
)

:: ---------- 7. Auto-buka browser lokal ----------
echo [INFO] Menjalankan backend di http://0.0.0.0:%PORT% (semua interface, satu jaringan^)
echo        Docs  : http://127.0.0.1:%PORT%/docs
echo        Health: http://127.0.0.1:%PORT%/health
echo.
echo [TIPS] Biarkan window ini terbuka. Ctrl+C untuk stop.
echo        Syarat review: HP/laptop lain konek WiFi yang SAMA dengan PC ini.
echo.

if "%PORT_BUSY%"=="1" goto BROWSER_BUSY
echo [INFO] Browser akan dibuka otomatis (poll 0.3s x 40 = 12 detik)...
start "" powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%tools\open-browser.ps1" -Port %PORT% -LoginPath "%LOGIN_PATH%" -Mode local
goto BROWSER_DONE

:BROWSER_BUSY
echo [INFO] Port %PORT% sudah LISTENING - buka browser cepat...
start "" "http://127.0.0.1:%PORT%%LOGIN_PATH%"
echo [INFO] Browser lokal dibuka: http://127.0.0.1:%PORT%%LOGIN_PATH%
goto BROWSER_DONE

:BROWSER_DONE

:: ---------- 8. Jalankan backend ----------
if not "%PORT_BUSY%"=="1" goto SKIP_BUSY_CHECK
echo.
echo [INFO] Backend sudah berjalan di port %PORT% - tidak start ulang.
curl.exe -s http://127.0.0.1:%PORT%/health
if errorlevel 1 powershell -NoProfile -Command "Invoke-WebRequest http://127.0.0.1:%PORT%/health -UseBasicParsing -TimeoutSec 2"
echo.
echo [INFO] Tekan tombol apa saja untuk tutup window ini.
pause
exit /b 0
:SKIP_BUSY_CHECK
cd /d "%BACKEND%"
if "%ENV%"=="production" (
  "%PYTHON_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
) else (
  "%PYTHON_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload
)

echo.
echo [INFO] Server berhenti.
pause
