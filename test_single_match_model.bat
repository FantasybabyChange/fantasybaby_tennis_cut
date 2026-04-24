@echo off
setlocal

cd /d "%~dp0"

set "INPUT_VIDEO=D:\videomarker\aiVideoWorkspace\single1.mp4"
set "OUTPUT_DIR=D:\videomarker\aiVideoWorkspace\output"
set "OUTPUT_VIDEO=%OUTPUT_DIR%\single1_cut_model.mp4"
set "EXTRA_ARGS=%*"

if not exist "%INPUT_VIDEO%" (
    echo Input video not found:
    echo %INPUT_VIDEO%
    exit /b 1
)

if not exist "%OUTPUT_DIR%" (
    mkdir "%OUTPUT_DIR%"
)

echo FantasyBaby singles match model-assisted test cut
echo Input: %INPUT_VIDEO%
echo Output: %OUTPUT_VIDEO%
echo.
echo For the curated rally-complete recipe, run:
echo .\test_single_match_model_balanced_v2.bat
echo.
echo If model dependencies are missing, run:
echo uv sync --extra model
echo.

call uv --cache-dir .uv-cache run tennis-cut "%INPUT_VIDEO%" -o "%OUTPUT_VIDEO%" --video-type 3 --model-assist ball %EXTRA_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Model-assisted singles match test command completed.
    echo Output video path:
    echo %OUTPUT_VIDEO%
) else (
    echo Generation failed. Exit code: %EXIT_CODE%
)

echo.
exit /b %EXIT_CODE%
