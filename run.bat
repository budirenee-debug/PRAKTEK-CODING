@echo off
setlocal
chcp 65001 >nul
title B_gadget POS - Localhost + Tunnel Unified

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

:: ---------- 3. Dependencies (fast check, tanpa upgrade pip tiap run) ----------
echo [INFO] Cek dependencies fastapi+uvicorn ...
"%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo [WARN] fastapi/uvicorn belum terimport — coba install butuh internet...
  echo        Jika gagal, akan tetap coba jalan, cek manual: %PYTHON_EXE% -m pip install -r %BACKEND%\requirements.txt
  "%PYTHON_EXE%" -m pip install -r "%BACKEND%\requirements.txt" --quiet
  if errorlevel 1 (
    echo [WARN] pip install gagal — cek internet / proxy. Coba manual:
    echo        %PYTHON_EXE% -m pip install -r %BACKEND%\requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
    echo        Atau jika sudah pernah install, lanjut coba jalan...
  )
  "%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] fastapi/uvicorn masih belum bisa diimport setelah install.
    echo        Coba manual: %PYTHON_EXE% -m pip install fastapi uvicorn sqlalchemy pydantic python-multipart passlib bcrypt python-jose httpx
    pause
    exit /b 1
  ) else (
    echo [INFO] Dependencies OK setelah install.
  )
) else (
  echo [INFO] Dependencies OK.
)

:: ---------- 4. Cek port ----------
set "PORT_BUSY=0"
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  set "PORT_BUSY=1"
  echo [WARN] Port %PORT% sudah LISTENING ^(server mungkin sudah jalan^).
  echo        Cek: http://localhost:%PORT%/health
  echo        -> Browser akan tetap dibuka, backend tidak di-start ulang untuk hindari Address already in use.
  echo(
)

:: ---------- 5. Cari cloudflared ----------
set "CLOUDFLARED_EXE="
where cloudflared >nul 2>nul
if not errorlevel 1 set "CLOUDFLARED_EXE=cloudflared"
if not defined CLOUDFLARED_EXE (
  if exist "%CFDIR%\bin\cloudflared.exe" set "CLOUDFLARED_EXE=%CFDIR%\bin\cloudflared.exe"
)
if not defined CLOUDFLARED_EXE if exist "C:\Program Files\cloudflared\cloudflared.exe" set "CLOUDFLARED_EXE=C:\Program Files\cloudflared\cloudflared.exe"
if not defined CLOUDFLARED_EXE if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" set "CLOUDFLARED_EXE=C:\Program Files (x86)\cloudflared\cloudflared.exe"

if defined CLOUDFLARED_EXE (
  echo [INFO] cloudflared : %CLOUDFLARED_EXE%
) else (
  echo [WARN] cloudflared tidak ditemukan. Lanjut mode LOCALHOST saja.
  echo        Install: winget install --id Cloudflare.cloudflared -e
)

:: ---------- 6. Tentukan mode tunnel (fix wildcard *.json) ----------
set "MODE=none"
if defined CLOUDFLARED_EXE set "MODE=quick"
:: Jika kredensial + config ada, upgrade ke named
if defined CLOUDFLARED_EXE (
  if exist "%CFDIR%\config.yml" (
    dir /b "%USERPROFILE%\.cloudflared\*.json" >nul 2>nul
    if not errorlevel 1 set "MODE=named"
  )
)

echo [INFO] Mode tunnel: %MODE%  - named=service.reneepsl.my.id, quick=*.trycloudflare.com, none=lokal
if "%MODE%"=="named" (
  for %%F in ("%USERPROFILE%\.cloudflared\*.json") do echo        Kredensial: %%F
)
echo.

:: ---------- 7. Jalankan tunnel di window baru (auto-restart jika pindah jaringan) ----------
:: Jika port busy (pindah jaringan), tunnel lama kemungkinan putus — kill & restart agar publik kembali online
if "%PORT_BUSY%"=="1" if not "%MODE%"=="none" (
  echo [INFO] Port busy + pindah jaringan terdeteksi — restart tunnel lama...
  taskkill /IM cloudflared.exe /F >nul 2>nul
  timeout /t 2 >nul
)
if "%MODE%"=="named" goto TUNNEL_NAMED
if "%MODE%"=="quick" goto TUNNEL_QUICK
if "%MODE%"=="none" goto TUNNEL_NONE

:TUNNEL_NAMED
echo [INFO] Menjalankan Named Tunnel - service.reneepsl.my.id - di window baru...
start "B_gadget Tunnel - NAMED" "%CLOUDFLARED_EXE%" tunnel --config "%CFDIR%\config.yml" run b-gadget
echo [INFO] Publik : https://service.reneepsl.my.id%LOGIN_PATH%
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

:: ---------- 8b. Buka browser FAST (poll 0.2s, max 6 detik, tidak blok backend) ----------
if "%PORT_BUSY%"=="1" goto BROWSER_BUSY

:: Port belum busy -> backend akan start di bawah (blocking). Buka browser via background poll cepat
echo [INFO] Browser akan dibuka otomatis (fast poll ~3 detik, buka begitu health 200)...
if "%MODE%"=="named" goto BROWSER_NAMED_FAST
goto BROWSER_QUICK_FAST

:BROWSER_NAMED_FAST
start "" powershell -NoProfile -Command "$t=0; while($t -lt 20){ try{ $r=Invoke-WebRequest -Uri 'http://localhost:%PORT%/health' -TimeoutSec 1 -UseBasicParsing; if($r.StatusCode -eq 200){ Start-Process 'http://localhost:%PORT%%LOGIN_PATH%'; Start-Process 'https://service.reneepsl.my.id%LOGIN_PATH%'; exit 0 } }catch{}; Start-Sleep -Milliseconds 200; $t++; } Start-Process 'http://localhost:%PORT%%LOGIN_PATH%'; Start-Process 'https://service.reneepsl.my.id%LOGIN_PATH%'"
goto BROWSER_DONE

:BROWSER_QUICK_FAST
start "" powershell -NoProfile -Command "$t=0; while($t -lt 20){ try{ $r=Invoke-WebRequest -Uri 'http://localhost:%PORT%/health' -TimeoutSec 1 -UseBasicParsing; if($r.StatusCode -eq 200){ Start-Process 'http://localhost:%PORT%%LOGIN_PATH%'; exit 0 } }catch{}; Start-Sleep -Milliseconds 200; $t++; } Start-Process 'http://localhost:%PORT%%LOGIN_PATH%'"
goto BROWSER_DONE

:BROWSER_BUSY
echo [INFO] Port %PORT% sudah LISTENING - buka browser cepat (tanpa tunggu lama)...
start "" "http://localhost:%PORT%%LOGIN_PATH%"
echo [INFO] Browser lokal dibuka: http://localhost:%PORT%%LOGIN_PATH%
if "%MODE%"=="named" (
  start "" "https://service.reneepsl.my.id%LOGIN_PATH%"
  echo [INFO] Browser publik dibuka: https://service.reneepsl.my.id%LOGIN_PATH%
)
goto BROWSER_DONE

:BROWSER_DONE

:: ---------- 9. Jalankan backend (blocking) ----------
if "%PORT_BUSY%"=="1" (
  echo.
  echo [INFO] Backend sudah berjalan di port %PORT% - tidak start ulang.
  echo        Untuk restart: tutup window backend lama lalu jalankan run.bat lagi.
  echo        Membuka health check...
  curl.exe -s http://localhost:%PORT%/health 2>nul || powershell -Command "try{ (Invoke-WebRequest http://localhost:%PORT%/health -UseBasicParsing).Content }catch{ 'health fetch gagal' }"
  echo.
  echo [INFO] Tekan tombol apa saja untuk tutup window ini (tunnel tetap jalan).
  pause
  exit /b 0
)
cd /d "%BACKEND%"
:: Host 127.0.0.1 lebih cepat untuk localhost (hindari 0.0.0.0 scan firewall); tunnel tetap bisa via 127.0.0.1:8000
:: --reload hanya untuk dev, tanpa reload lebih cepat 1-2 detik. Gunakan ENV=production untuk tanpa reload.
if "%ENV%"=="production" (
  "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
) else (
  "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload
)

echo.
echo [INFO] Server berhenti.
pause
