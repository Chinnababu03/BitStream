#!/usr/bin/env python3
"""
Torrent + YouTube Downloader - Self-hosted download manager with web UI
Run: python main.py
Access: http://localhost:8080
"""

import os
import sys
import logging

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import app using the new container-based architecture
# (no more sys.path.insert hacks)
# ---------------------------------------------------------------------------
from web.app import create_app


if __name__ == '__main__':
    app, socketio, container = create_app()
    settings = container.settings

    print("=" * 55)
    print("  BitStream - Torrent & YouTube Downloader")
    print("  Self-hosted download manager")
    print("=" * 55)
    print(f"  Server : http://localhost:{settings.web_port}")
    print(f"  Downloads : {settings.download_path}")
    print(f"  Stop   : Ctrl+C")
    print("=" * 55)

    # Start the download manager
    container.start()

    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=settings.web_port,
            debug=False,
            allow_unsafe_werkzeug=True
        )
    finally:
        container.stop()
