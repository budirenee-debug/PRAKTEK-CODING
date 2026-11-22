@echo off
setlocal
chcp 65001 >nul
title B_gadget POS - Localhost Only

:: ==========================================================
::  B_gadget POS - Localhost Runner (LOKAL SAJA)
::  - Backend : FastAPI http://127.0.0.1:8000
::  - Tanpa Tunnel / Cloudflare
::  - Untuk dev lokal Windows
::  - Butuh tunnel? pakai run-tunnel.bat (Windows)
::    atau run-tunnel.sh (Ubuntu Server)
:: ==========================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "PORT=8000"
set "LOGIN_PATH=/frontend/dev.html"

echo ========================================
echo  B_gadget POS - Localhost Only
echo  Root   : %ROOT%
echo  Mode   : LOKAL (tanpa tunnel)
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
:: PENTING: port LISTENING belum tentu server kita. Dulu script ini langsung
:: menganggap "server sudah jalan" lalu membuka browser - padahal yang occupying
:: port bisa aplikasi lain, sehingga browsernya kebuka halaman 404.
:: Sekarang dicek 2 penanda milik B_gadget POS:
::   1) /health membalas {"status":"ok","db":"sqlite"}   (backend/app/main.py)
::   2) /frontend/... membalas HTTP 200  (hanya app ini yang mount /frontend)
set "PORT_BUSY=0"
set "PORT_PID="
set "HEALTH_OK=0"
set "FRONT_OK=0"

netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>nul
if errorlevel 1 goto PORT_FREE

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do set "PORT_PID=%%p"

curl.exe -s --max-time 3 http://127.0.0.1:%PORT%/health 2>nul | findstr /i "sqlite" >nul 2>nul
if not errorlevel 1 set "HEALTH_OK=1"

curl.exe -s -o nul -w "%%{http_code}" --max-time 3 "http://127.0.0.1:%PORT%%LOGIN_PATH%" 2>nul | findstr /b "200" >nul 2>nul
if not errorlevel 1 set "FRONT_OK=1"

if "%HEALTH_OK%"=="1" if "%FRONT_OK%"=="1" goto PORT_OURS
goto PORT_FOREIGN

:PORT_FREE
echo [OK] Port %PORT% bebas.
goto PORT_DONE

:PORT_OURS
set "PORT_BUSY=1"
echo [OK] Port %PORT% memang dipakai B_gadget POS - server sudah jalan.
echo        Backend tidak di-start ulang, browser tetap dibuka.
goto PORT_DONE

:PORT_FOREIGN
echo.
echo [ERROR] Port %PORT% sudah dipakai proses LAIN - bukan B_gadget POS.
echo.
echo         PID pelakunya   : %PORT_PID%
for /f "usebackq delims=" %%h in (`curl.exe -s --max-time 3 http://127.0.0.1:%PORT%/health`) do echo         Isi /health    : %%h
echo         Seharusnya      : {"status":"ok","db":"sqlite"}
echo         Halaman frontend: http://127.0.0.1:%PORT%%LOGIN_PATH%
echo.
echo         Server kita TIDAK dijalankan dan browser TIDAK dibuka, supaya ga
echo         membuka halaman 404 lalu disalahartikan sebagai "web rusak".
echo.
echo         >> Bunuh pelakunya dulu, lalu jalankan run.bat lagi:
echo              taskkill /PID %PORT_PID% /F
echo.
echo         >> Kalau proses itu aplikasi lain yang SEDANG DIPAKAI, jalankan
echo            aplikasinya di port berbeda. Jangan bunuh tanpa dicek.
echo.
pause
exit /b 1

:PORT_DONE
echo.

:: ---------- 5. Info ----------
echo [INFO] Mode: LOKAL ONLY - tanpa cloudflared/tunnel
echo [INFO] Akses lokal: http://127.0.0.1:%PORT%%LOGIN_PATH%
echo [INFO] Butuh akses publik? Jalankan run-tunnel.bat
echo.

:: ---------- 6. Auto-buka browser ----------
echo [INFO] Menjalankan backend di http://127.0.0.1:%PORT%
echo        Docs  : http://127.0.0.1:%PORT%/docs
echo        Health: http://127.0.0.1:%PORT%/health
echo.
echo [TIPS] Biarkan window ini terbuka. Ctrl+C untuk stop.
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

:: ---------- 7. Jalankan backend ----------
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
  "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
) else (
  "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload
)

echo.
echo [INFO] Server berhenti.
pause
