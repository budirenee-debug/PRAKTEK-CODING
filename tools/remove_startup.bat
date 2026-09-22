@echo off
chcp 65001 >nul
echo === HAPUS AUTOSTART B_gadget POS ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0remove_startup.ps1"
pause
