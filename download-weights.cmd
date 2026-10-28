@echo off
cd /d "%~dp0"
echo Download optional 3.8 MB NanoDet weights and verify SHA256.
echo Manual segmentation and observation assessment do not need weights.
python -B setup_objects.py
pause
