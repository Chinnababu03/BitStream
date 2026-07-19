"""
Centralized configuration for DownloadHub.

All settings are loaded from environment variables with sensible cross-platform defaults.
Use this module instead of scattering configuration across multiple files.
"""

import os
import platform
from dataclasses import dataclass, field
from typing import Optional


def _default_download_path() -> str:
    """Determine a cross-platform default download directory."""
    if platform.system() == "Windows":
        # Use standard Windows Downloads folder
        return os.path.join(os.path.expanduser("~"), "Downloads", "TorrentDownloaders")
    elif platform.system() == "Darwin":
        # macOS
        return os.path.join(os.path.expanduser("~"), "Downloads", "TorrentDownloaders")
    else:
        # Linux and other Unix-like systems
        return os.path.join(os.path.expanduser("~"), "Downloads", "TorrentDownloaders")


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables.

    Attributes:
        download_path: Root directory for all downloads.
        listen_port: Port for libtorrent peer connections.
        web_port: Port for the Flask web server.
        secret_key: Flask secret key for sessions.
        max_upload_size: Maximum file upload size in bytes (default 50 MB).
    """
    download_path: str = field(default_factory=lambda: os.path.abspath(
        os.environ.get("DOWNLOAD_PATH", _default_download_path())
    ))
    listen_port: int = field(default_factory=lambda: int(
        os.environ.get("LISTEN_PORT", "6881")
    ))
    web_port: int = field(default_factory=lambda: int(
        os.environ.get("WEB_PORT", "8080")
    ))
    secret_key: str = field(default_factory=lambda: os.environ.get(
        "SECRET_KEY", os.urandom(24).hex()
    ))
    max_upload_size: int = field(default_factory=lambda: int(
        os.environ.get("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024))
    ))

    def __post_init__(self):
        """Validate settings after initialization."""
        # Ensure download path exists
        os.makedirs(self.download_path, exist_ok=True)

    def is_safe_path(self, path: str) -> bool:
        """Check if a path is within the allowed download directory.

        Args:
            path: The path to validate.

        Returns:
            True if the path is safe (within download_path), False otherwise.
        """
        abs_path = os.path.abspath(path)
        return abs_path.startswith(self.download_path)


def load_settings() -> Settings:
    """Load settings from environment variables.

    Returns:
        A Settings instance with values from environment or defaults.
    """
    return Settings()
