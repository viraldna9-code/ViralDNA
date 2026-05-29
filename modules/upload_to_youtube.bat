@echo off
REM THE VIRAL DNA — YouTube Uploader Launcher
REM Drag and drop an MP4 onto this file to upload it
REM Or double-click for menu

cd /d C:\Users\sudha\ViralDNA\modules

if "%~1"=="" (
    echo.
    echo THE VIRAL DNA — YouTube Uploader (Selenium)
    echo ============================================
    echo.
    echo Options:
    echo   1. Upload channel trailer
    echo   2. Upload a video file
    echo   3. Batch upload folder
    echo   4. Exit
    echo.
    set /p choice="Choose (1-4): "
    if "!choice!"=="1" python youtube_selenium_uploader.py trailer
    if "!choice!"=="2" set /p vpath="Video path: " && python youtube_selenium_uploader.py upload "!vpath!"
    if "!choice!"=="3" set /p fpath="Folder path: " && python youtube_selenium_uploader.py batch "!fpath!"
    if "!choice!"=="4" exit /b
) else (
    python youtube_selenium_uploader.py upload "%~1" --privacy private
)

pause
