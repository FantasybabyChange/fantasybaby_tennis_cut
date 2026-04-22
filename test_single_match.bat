@echo off
setlocal

cd /d "%~dp0"

set "INPUT_VIDEO=D:\videomarker\aiVideoWorkspace\single1.mp4"
set "OUTPUT_DIR=D:\videomarker\aiVideoWorkspace\output"
set "OUTPUT_VIDEO=%OUTPUT_DIR%\single1_cut.mp4"
set "EXTRA_ARGS=%*"

if not exist "%INPUT_VIDEO%" (
    echo Input video not found:
    echo %INPUT_VIDEO%
    echo.
    exit /b 1
)

if not exist "%OUTPUT_DIR%" (
    mkdir "%OUTPUT_DIR%"
)

echo FantasyBaby singles match test cut
echo Input: %INPUT_VIDEO%
echo Output: %OUTPUT_VIDEO%
echo.

call uv --cache-dir .uv-cache run tennis-cut "%INPUT_VIDEO%" -o "%OUTPUT_VIDEO%" --video-type 3 %EXTRA_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Singles match test command completed.
    echo Output video path:
    echo %OUTPUT_VIDEO%
) else (
    echo Generation failed. Exit code: %EXIT_CODE%
)

echo.
exit /b %EXIT_CODE%
