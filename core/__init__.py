"""
Core package for DownloadHub.

Provides centralized access to all core components:
- config: Application settings
- event_bus: Event routing
- download_manager: Unified download facade
- container: Dependency injection
- torrent_client: Torrent operations
- youtube_client: YouTube operations
"""

# Config and event bus are always available (no external dependencies)
from core.config import Settings, load_settings
from core.event_bus import EventBus, EventType, get_event_bus
from core.download_manager import DownloadManager
from core.container import AppContainer, create_container

# Lazy imports for modules with heavy external dependencies (libtorrent, yt_dlp)
# These are imported on-demand to avoid import errors when dependencies aren't installed


def get_torrent_client():
    """Lazy import for TorrentClient (requires libtorrent)."""
    from core.torrent_client import TorrentClient, TorrentInfo, TorrentState
    return TorrentClient, TorrentInfo, TorrentState


def get_youtube_client():
    """Lazy import for YouTubeClient (requires yt_dlp)."""
    from core.youtube_client import YouTubeClient, YTDownloadInfo, YTDownloadState
    return YouTubeClient, YTDownloadInfo, YTDownloadState


__all__ = [
    # Config
    "Settings",
    "load_settings",
    # Event Bus
    "EventBus",
    "EventType",
    "get_event_bus",
    # Download Manager
    "DownloadManager",
    # Container
    "AppContainer",
    "create_container",
    # Lazy imports
    "get_torrent_client",
    "get_youtube_client",
]
