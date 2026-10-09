@echo off
cd /d "%~dp0"
title Auto ZIP - GameBanana
python auto_zip.py %*
pause
