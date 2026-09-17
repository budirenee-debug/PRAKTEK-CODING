@echo off
setlocal
chcp 65001 >nul
title B_gadget POS - Localhost + Tunnel (Unified)

:: ==========================================================
::  B_gadget POS - Unified Runner
::  Gabungan run.bat + run-tunnel.bat
::  - Backend  : FastAPI http://localhost:8000
::  - Tunnel   : otomatis Named (service.reneepsl.my.id) jika
::               kredensial ada, else Quick (*.trycloudflare.com)
::  - Browser  : auto buka localhost + URL publik
::  Single file, double-click langsung jalan.
:: ==========================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "CFDIR=%ROOT%.cloudflared"
set "PORT=8000"
set "LOGIN_PATH=/frontend/login.html"

echo ========================================
echo  B_gadget POS - Unified Runner
echo  Root   : %ROOT%
echo ========================================
echo.

:: ---------- 1. Cari Python ----------
set "PYTHON_EXE="
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYTHON_EXE (
  where python >nul 2>&1
  if %errorlevel%==0 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  where py >nul 2>&1
  if %errorlevel%==0 set "PYTHON_EXE=py"
)
if not defined PYTHON_EXE (
  echo [ERROR] Python tidak ditemukan. Install dulu:
  echo         winget install Python.Python.3.12 --silent
  pause
  exit /b 1
)
echo [INFO] Python : %PYTHON_EXE%
"%PYTHON_EXE%" --version
if %errorlevel% neq 0 (
  echo [ERROR] Python tidak bisa dijalankan: %PYTHON_EXE%
  pause
  exit /b 1
)

:: ---------- 2. Cek backend ----------
if not exist "%BACKEND%\app\main.py" (
  echo [ERROR] backend\app\main.py tidak ditemukan di "%BACKEND%"
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
"%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
  echo [INFO] Install dependencies, tunggu sebentar...
  "%PYTHON_EXE%" -m pip install --upgrade pip
  "%PYTHON_EXE%" -m pip install -r "%BACKEND%\requirements.txt"
  if %errorlevel% neq 0 (
    echo [ERROR] pip install gagal. Cek internet lalu ulangi.
    pause
    exit /b 1
  )
  "%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>&1
  if %errorlevel% neq 0 (
    echo [ERROR] fastapi/uvicorn masih belum bisa diimport.
    pause
    exit /b 1
  )
) else (
  echo [INFO] Dependencies OK.
)

:: ---------- 4. Cek port ----------
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo [WARN] Port %PORT% sudah LISTENING ^(server mungkin sudah jalan^).
  echo        Cek: http://localhost:%PORT%/health
  echo(
)

:: ---------- 5. Cari cloudflared ----------
set "CLOUDFLARED_EXE="
where cloudflared >nul 2>&1
if %errorlevel%==0 set "CLOUDFLARED_EXE=cloudflared"
if not defined CLOUDFLARED_EXE (
  if exist "%CFDIR%\bin\cloudflared.exe" set "CLOUDFLARED_EXE=%CFDIR%\bin\cloudflared.exe"
)
if not defined CLOUDFLARED_EXE (
  if exist "C:\Program Files\cloudflared\cloudflared.exe" set "CLOUDFLARED_EXE=C:\Program Files\cloudflared\cloudflared.exe"
)
if not defined CLOUDFLARED_EXE (
  if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" set "CLOUDFLARED_EXE=C:\Program Files (x86)\cloudflared\cloudflared.exe"
)

if defined CLOUDFLARED_EXE (
  echo [INFO] cloudflared : %CLOUDFLARED_EXE%
) else (
  echo [WARN] cloudflared tidak ditemukan. Lanjut mode LOCALHOST saja.
  echo        Install: winget install --id Cloudflare.cloudflared -e
)

:: ---------- 6. Tentukan mode tunnel ----------
set "MODE=none"
if defined CLOUDFLARED_EXE set "MODE=quick"
:: Jika kredensial + config ada, upgrade ke named
if defined CLOUDFLARED_EXE (
  if exist "%CFDIR%\config.yml" (
    if exist "%USERPROFILE%\.cloudflared\*.json" set "MODE=named"
  )
)

echo [INFO] Mode tunnel: %MODE%  - named=service.reneepsl.my.id, quick=*.trycloudflare.com, none=lokal
echo.

:: ---------- 7. Jalankan tunnel di window baru ----------
if "%MODE%"=="named" goto TUNNEL_NAMED
if "%MODE%"=="quick" goto TUNNEL_QUICK
if "%MODE%"=="none" goto TUNNEL_NONE

:TUNNEL_NAMED
echo [INFO] Menjalankan Named Tunnel - service.reneepsl.my.id - di window baru...
start "B_gadget Tunnel - NAMED" "%CLOUDFLARED_EXE%" tunnel --config "%CFDIR%\config.yml" run b-gadget
echo [INFO] Publik : https://service.reneepsl.my.id%LOGIN_PATH%
:: tanpa delay lama
timeout /t 1 >nul
goto TUNNEL_DONE

:TUNNEL_QUICK
echo [INFO] Menjalankan Quick Tunnel - trycloudflare.com - di window baru...
echo        URL akan muncul di window tunnel, tunggu 5-10 detik.
start "B_gadget Tunnel - QUICK" "%CLOUDFLARED_EXE%" tunnel --url http://localhost:%PORT%
echo [INFO] Lokal tetap: http://localhost:%PORT%%LOGIN_PATH%
timeout /t 1 >nul
goto TUNNEL_DONE

:TUNNEL_NONE
echo [INFO] Tunnel dilewati. Akses lokal: http://localhost:%PORT%%LOGIN_PATH%

:TUNNEL_DONE
echo.

:: ---------- 8. Auto-buka browser (tunggu backend siap) ----------
echo [INFO] Menjalankan backend di http://localhost:%PORT%
echo        Docs  : http://localhost:%PORT%/docs
echo        Health: http://localhost:%PORT%/health
if "%MODE%"=="named" echo        Publik: https://service.reneepsl.my.id%LOGIN_PATH%
echo.
echo [TIPS] Biarkan window ini + window Tunnel terbuka. Ctrl+C untuk stop.
echo.

:: Buka browser CEPAT: lokal langsung, publik tunggu health singkat
set "BROWSER_PS1=%TEMP%\bgadget_browser_%PORT%.ps1"
if "%MODE%"=="named" goto BROWSER_NAMED
goto BROWSER_LOCAL

:BROWSER_NAMED
:: buka dua-duanya langsung tanpa tunggu health (paling cepat)
start "" "http://localhost:%PORT%%LOGIN_PATH%"
echo [INFO] Browser lokal dibuka: http://localhost:%PORT%%LOGIN_PATH%
start "" "https://service.reneepsl.my.id%LOGIN_PATH%"
echo [INFO] Browser publik dibuka: https://service.reneepsl.my.id%LOGIN_PATH%
goto BROWSER_DONE

:BROWSER_LOCAL
start "" "http://localhost:%PORT%%LOGIN_PATH%"
echo [INFO] Browser lokal dibuka: http://localhost:%PORT%%LOGIN_PATH%
goto BROWSER_DONE

:BROWSER_DONE

:: ---------- 9. Jalankan backend (blocking) ----------
cd /d "%BACKEND%"
"%PYTHON_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload

echo.
echo [INFO] Server berhenti.
pause
