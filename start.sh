#!/bin/bash

# Set default download path (can be overridden by environment variable)
# Note: Windows users should use start.bat instead
export DOWNLOAD_PATH="${DOWNLOAD_PATH:-$HOME/Downloads/TorrentDownloaders}"

echo "===================================================="
echo "  BitStream — Torrent & YouTube Downloader"
echo "===================================================="
echo ""

# Check for virtual environment
if [ ! -d "venv" ] && [ ! -d "env" ]; then
    echo "[INFO] No virtual environment found (venv/ or env/)."
    echo "[INFO] Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    echo ""
fi

echo "Access the web UI at: http://localhost:8080"
echo "Downloads folder: $DOWNLOAD_PATH"
echo ""
python3 main.py
