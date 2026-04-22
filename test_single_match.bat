@echo off
setlocal

cd /d "%~dp0"

set "INPUT_VIDEO=D:\videomarker\aiVideoWorkspace\single1.mp4"
set "OUTPUT_DIR=D:\videomarker\aiVideoWorkspace\output"
set "OUTPUT_VIDEO=%OUTPUT_DIR%\single1_cut.mp4"
set "TIMELINE=%OUTPUT_DIR%\single1_timeline.json"

if not exist "%INPUT_VIDEO%" (
    echo 找不到输入视频:
    echo %INPUT_VIDEO%
    echo.
    pause
    exit /b 1
)

if not exist "%OUTPUT_DIR%" (
    mkdir "%OUTPUT_DIR%"
)

echo FantasyBaby 单打比赛测试剪辑
echo 输入: %INPUT_VIDEO%
echo 输出: %OUTPUT_VIDEO%
echo 时间线: %TIMELINE%
echo.

uv --cache-dir .uv-cache run tennis-cut "%INPUT_VIDEO%" -o "%OUTPUT_VIDEO%" --timeline "%TIMELINE%" --video-type 3
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo 单打比赛测试视频生成完成:
    echo %OUTPUT_VIDEO%
    echo.
    echo 时间线已写入:
    echo %TIMELINE%
) else (
    echo 生成失败，退出码: %EXIT_CODE%
)

echo.
pause
exit /b %EXIT_CODE%
