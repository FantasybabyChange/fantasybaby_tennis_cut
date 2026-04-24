@echo off
setlocal

cd /d "%~dp0"

set "INPUT_VIDEO=D:\videomarker\aiVideoWorkspace\single1.mp4"
set "OUTPUT_DIR=D:\videomarker\aiVideoWorkspace\output"
set "OUTPUT_VIDEO=%OUTPUT_DIR%\single1_cut_model_balanced_v2.mp4"
set "TIMELINE_FILE=%OUTPUT_DIR%\single1_cut_model_balanced_v2.timeline.json"
set "MATCH_END_SECONDS=1869"
set "EXTRA_ARGS=%*"

if not exist "%INPUT_VIDEO%" (
    echo Input video not found:
    echo %INPUT_VIDEO%
    exit /b 1
)

if not exist "%OUTPUT_DIR%" (
    mkdir "%OUTPUT_DIR%"
)

echo FantasyBaby singles match model-assisted balanced v2 cut
echo Input: %INPUT_VIDEO%
echo Output: %OUTPUT_VIDEO%
echo Timeline: %TIMELINE_FILE%
echo Match end clip: %MATCH_END_SECONDS%s
echo.
echo This recipe keeps rallies more complete and removes post-match chat footage.
echo If model dependencies are missing, run:
echo uv sync --extra model
echo.

call uv --cache-dir .uv-cache run tennis-cut ^
    "%INPUT_VIDEO%" ^
    -o "%OUTPUT_VIDEO%" ^
    --timeline "%TIMELINE_FILE%" ^
    --video-type 3 ^
    --model-assist ball ^
    --pre-roll-seconds 1.1 ^
    --post-roll-seconds 1.4 ^
    --serve-pre-roll-seconds 2.0 ^
    --audio-soft-bridge-gap-seconds 12.5 ^
    --visual-audio-soft-bridge-gap-seconds 20.0 ^
    --audio-gap-rescue-gap-seconds 16.0 ^
    --visual-audio-gap-rescue-max-gap-seconds 60.0 ^
    --final-continuity-merge-gap-seconds 8.0 ^
    --audio-tail-trim-min-segment-seconds 0 ^
    --audio-silent-gap-trim-min-segment-seconds 0 ^
    --no-model-ball-trim-silent-gaps ^
    --clip-end-seconds %MATCH_END_SECONDS% ^
    %EXTRA_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Balanced v2 singles match test command completed.
    echo Output video path:
    echo %OUTPUT_VIDEO%
    echo Timeline path:
    echo %TIMELINE_FILE%
) else (
    echo Generation failed. Exit code: %EXIT_CODE%
)

echo.
exit /b %EXIT_CODE%
