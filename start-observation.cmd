@echo off
cd /d "%~dp0"
echo PickGo Lab observation validation - camera stays off until you click Open.
echo Select Objects or Manual segmentation, then Assess selected target.
python -B app.py --vision-only %*
pause
