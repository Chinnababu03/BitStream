@echo off
setlocal
title BitStream - Torrent and YouTube Downloader

echo ====================================================
echo   BitStream - Torrent and YouTube Downloader
echo ====================================================
echo.

REM Set default download path (can be overridden by environment variable)
if not defined DOWNLOAD_PATH (
    set "DOWNLOAD_PATH=C:\Users\chinn\Downloads\TorrentDownloaders"
)

REM Check and activate virtual environment if it exists
if exist ".\venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment venv...
    call .\venv\Scripts\activate.bat
) else if exist ".\env\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment env...
    call .\env\Scripts\activate.bat
) else (
    echo [INFO] No virtual environment found.
    echo [INFO] Running with system Python...
)

echo Access the web UI at: http://localhost:8080
echo Downloads folder: %DOWNLOAD_PATH%
echo.
python main.py
pause
endlocal
