@echo off
setlocal

cd /d "%~dp0"

echo FantasyBaby Tennis Cut
echo.
echo Select cut engine:
echo   1. Legacy audio/visual rules
echo   2. New model-assisted ball tracking
echo.
echo Tip: for the curated singles full-rally recipe on Windows,
echo run .\test_single_match_model_balanced_v2.bat
echo.
set "CUT_ENGINE="
:choose_engine
set /p "CUT_ENGINE=Enter 1 or 2: "
if "%CUT_ENGINE%"=="1" goto run_legacy
if "%CUT_ENGINE%"=="2" goto run_model
echo Invalid selection. Please enter 1 or 2.
echo.
goto choose_engine

:run_model
echo.
echo New model-assisted mode selected.
echo If this is the first run, install dependencies with:
echo uv sync --extra model
echo.
uv --cache-dir .uv-cache run tennis-cut --model-assist ball
goto done

:run_legacy
echo.
echo Legacy audio/visual mode selected.
echo.
uv --cache-dir .uv-cache run tennis-cut

:done

echo.
pause
