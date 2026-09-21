@echo off
chcp 65001 >nul
echo ========================================
echo  B_gadget POS - Cek Status Cepat
echo ========================================
echo.
echo [1] Backend 127.0.0.1:8000/health
curl.exe -s http://127.0.0.1:8000/health
echo.
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul && echo [OK] LISTENING || echo [FAIL] NOT LISTENING
echo.
tasklist | findstr /i cloudflared >nul && echo [OK] cloudflared JALAN || echo [FAIL] cloudflared TIDAK JALAN
echo.
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\B_gadget POS.lnk" (echo [OK] Startup ada) else (echo [FAIL] Startup TIDAK ada)
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "B_gadget_POS" >nul 2>nul && echo [OK] Registry Run ada || echo [INFO] Registry Run tidak ada
echo.
pause
