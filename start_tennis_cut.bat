@echo off
setlocal

cd /d "%~dp0"
uv --cache-dir .uv-cache run tennis-cut

echo.
pause
