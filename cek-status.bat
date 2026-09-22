@echo off
chcp 65001 >nul
echo ========================================
echo  B_gadget POS - Cek Status Cepat
echo  run.bat       = LOKAL ONLY
echo  run-tunnel.bat= LOKAL+TUNNEL
echo ========================================
echo.
echo [1] Backend 127.0.0.1:8000/health
curl.exe -s http://127.0.0.1:8000/health
echo.
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul && echo [OK] Port 8000 LISTENING || echo [FAIL] Port 8000 NOT LISTENING
echo.
tasklist | findstr /i cloudflared >nul && echo [OK] cloudflared JALAN || echo [INFO] cloudflared TIDAK JALAN (normal jika pakai run.bat lokal)
echo.
echo [2] Startup (LOKAL)
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\B_gadget POS.lnk" (echo [OK] Startup LOKAL ada - B_gadget POS.lnk) else (echo [INFO] Startup LOKAL TIDAK ada)
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\B_gadget POS Tunnel.lnk" (echo [WARN] Startup TUNNEL ada - B_gadget POS Tunnel.lnk) else (echo [INFO] Startup TUNNEL TIDAK ada - OK untuk lokal)
echo.
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "B_gadget_POS" >nul 2>nul && echo [OK] Registry Run LOKAL ada || echo [INFO] Registry Run LOKAL tidak ada
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "B_gadget_POS_Tunnel" >nul 2>nul && echo [WARN] Registry Run TUNNEL ada || echo [INFO] Registry Run TUNNEL tidak ada
echo.
schtasks /query /tn "B_gadget_POS_AutoStart" >nul 2>nul && echo [OK] Task LOKAL ada || echo [INFO] Task LOKAL tidak ada
schtasks /query /tn "B_gadget_POS_Tunnel_AutoStart" >nul 2>nul && echo [WARN] Task TUNNEL ada || echo [INFO] Task TUNNEL tidak ada
echo.
echo [3] File runner
if exist "%~dp0run.bat" echo [OK] run.bat (lokal) ada
if exist "%~dp0run-tunnel.bat" echo [OK] run-tunnel.bat (tunnel) ada
if exist "%~dp0run.sh" echo [OK] run.sh (ubuntu lokal) ada
if exist "%~dp0run-tunnel.sh" echo [OK] run-tunnel.sh (ubuntu tunnel) ada
echo.
pause
