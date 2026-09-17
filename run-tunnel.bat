@echo off
chcp 65001 >nul
echo ========================================
echo  B_gadget Tunnel - Sudah Digabung
echo  Sekarang cukup double-click run.bat
echo  (localhost + tunnel otomatis dalam 1 file)
echo ========================================
echo.
echo run-tunnel.bat sekarang hanya wrapper ke run.bat
echo Menjalankan run.bat ...
echo.
call "%~dp0run.bat"
