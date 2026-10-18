@echo off
cd /d "%~dp0"
python -B app.py --vision-only %*
pause
