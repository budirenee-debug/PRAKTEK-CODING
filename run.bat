@echo off
setlocal
chcp 65001 >nul
title B_gadget POS - FastAPI + Frontend

:: --- Lokasi project ---
set ROOT=%~dp0
set BACKEND=%ROOT%backend
set FRONTEND=%ROOT%frontend
set PYTHON_EXE=C:\Users\budirenee\AppData\Local\Programs\Python\Python312\python.exe

:: fallback jika path hardcode tidak ada, coba python di PATH
if not exist "%PYTHON_EXE%" (
  where python >nul 2>&1
  if %errorlevel%==0 (
    set PYTHON_EXE=python
  ) else (
    where py >nul 2>&1
    if %errorlevel%==0 (
      set PYTHON_EXE=py
    ) else (
      echo [ERROR] Python tidak ditemukan. Install Python 3.12 dulu.
      echo         winget install Python.Python.3.12 --silent
      pause
      exit /b 1
    )
  )
)

echo ========================================
echo  B_gadget POS Service HP - Runner
echo  Backend : FastAPI + SQLite
echo  Frontend: %FRONTEND%
echo  Python  : %PYTHON_EXE%
echo ========================================
echo.

:: 1. Cek backend folder
if not exist "%BACKEND%\requirements.txt" (
  echo [ERROR] File backend\requirements.txt tidak ditemukan
  pause
  exit /b 1
)

:: 2. Install deps (skip jika sudah ada fastapi)
"%PYTHON_EXE%" -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
  echo [INFO] Install dependencies...
  "%PYTHON_EXE%" -m pip install -r "%BACKEND%\requirements.txt"
  if %errorlevel% neq 0 (
    echo [ERROR] pip install gagal
    pause
    exit /b 1
  )
) else (
  echo [INFO] Dependencies sudah terinstall, skip pip install
)

:: 3. Seed check - superadmin otomatis dibuat saat startup
echo [INFO] Menjalankan FastAPI di http://localhost:8000
echo        Docs     : http://localhost:8000/docs
echo        Login    : http://localhost:8000/frontend/login.html  (superadmin / bismillah)
echo        Dashboard: http://localhost:8000/frontend/index.html
echo        Health   : http://localhost:8000/health
echo.
echo [INFO] Tunnel   : https://service.reneepsl.my.id  (via Cloudflare Tunnel b-gadget)
echo        Web      : https://service.reneepsl.my.id/frontend/login.html
echo        Web Dash : https://service.reneepsl.my.id/frontend/index.html
echo.
echo [TIPS] Biarkan window ini terbuka. Tutup window untuk stop server.
echo        Atau Ctrl+C untuk stop.
echo.

:: 4. Cek & jalankan Cloudflare Tunnel otomatis (b-gadget) di window terpisah
set "CLOUDFLARED_EXE=C:\Program Files (x86)\cloudflared\cloudflared.exe"
if exist "%CLOUDFLARED_EXE%" (
  echo [INFO] Menjalankan Cloudflare Tunnel b-gadget di window baru...
  start "B_gadget Tunnel" "%CLOUDFLARED_EXE%" tunnel --config "%ROOT%.cloudflared\config.yml" run b-gadget
) else (
  where cloudflared >nul 2>&1
  if %errorlevel%==0 (
    echo [INFO] Menjalankan Tunnel via PATH...
    start "B_gadget Tunnel" cloudflared tunnel --config "%ROOT%.cloudflared\config.yml" run b-gadget
  ) else (
    echo [WARN] cloudflared tidak ditemukan, skip tunnel. Jalankan run-tunnel.bat manual.
  )
)

:: 5. Buka browser otomatis ke B_gadget (lokal + online login)
start /b cmd /c "timeout /t 4 >nul & start http://localhost:8000/frontend/login.html & timeout /t 1 >nul & start https://service.reneepsl.my.id/frontend/login.html"

:: 6. Jalankan uvicorn (blocking, reload aktif)
cd /d "%BACKEND%"
"%PYTHON_EXE%" -m uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

:: jika uvicorn exit
echo.
echo [INFO] Server berhenti.
pause
