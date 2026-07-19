"""
Unified Download Manager facade.

Wraps TorrentClient and YouTubeClient behind a single interface so the web layer
calls one API instead of two separate code paths.
"""

import logging
from typing import List, Optional, Dict, Any

from core.config import Settings
from core.event_bus import EventBus, EventType
from core.torrent_client import TorrentClient, TorrentInfo
from core.youtube_client import YouTubeClient

logger = logging.getLogger(__name__)


class DownloadManager:
    """Unified facade over torrent and YouTube download clients.

    Provides a single interface for the web layer to interact with all download
    types, eliminating duplicate validation, error handling, and code paths.
    """

    def __init__(self, settings: Settings, event_bus: EventBus):
        self.settings = settings
        self.event_bus = event_bus

        # Initialize underlying clients
        self.torrent_client = TorrentClient(
            save_path=settings.download_path,
            listen_port=settings.listen_port
        )
        self.youtube_client = YouTubeClient(
            save_path=settings.download_path
        )

        # Wire up events from clients to the event bus
        self.torrent_client.add_callback(self._forward_event)
        self.youtube_client.add_callback(self._forward_event)

    def _forward_event(self, event: str, data: dict) -> None:
        """Forward events from clients to the centralized event bus."""
        self.event_bus.publish(event, data)

    def start(self) -> None:
        """Start the download manager and all underlying clients."""
        self.torrent_client.start()
        self.event_bus.publish(EventType.STARTED.value, {})
        logger.info("DownloadManager started")

    def stop(self) -> None:
        """Stop the download manager and all underlying clients."""
        self.torrent_client.stop()
        self.event_bus.publish(EventType.STOPPED.value, {})
        logger.info("DownloadManager stopped")

    # ── Torrent operations ──────────────────────────────────────────────

    def add_torrent(self, magnet_or_path: str, save_path: Optional[str] = None) -> Optional[str]:
        """Add a torrent from a magnet link or .torrent file path.

        Args:
            magnet_or_path: Magnet link string or path to .torrent file.
            save_path: Custom save directory (uses default if None).

        Returns:
            Torrent hash string on success, None on failure.
        """
        return self.torrent_client.add_torrent(magnet_or_path, save_path)

    def remove_torrent(self, torrent_hash: str, delete_files: bool = False) -> None:
        """Remove a torrent by hash.

        Args:
            torrent_hash: The torrent hash to remove.
            delete_files: If True, also delete downloaded files from disk.
        """
        self.torrent_client.remove_torrent(torrent_hash, delete_files)

    def pause_torrent(self, torrent_hash: str) -> None:
        """Pause a single torrent."""
        self.torrent_client.pause_torrent(torrent_hash)

    def resume_torrent(self, torrent_hash: str) -> None:
        """Resume a single torrent."""
        self.torrent_client.resume_torrent(torrent_hash)

    def pause_all_torrents(self) -> None:
        """Pause all torrents."""
        self.torrent_client.pause_all()

    def resume_all_torrents(self) -> None:
        """Resume all torrents."""
        self.torrent_client.resume_all()

    def get_torrent_info(self, torrent_hash: str) -> Optional[TorrentInfo]:
        """Get info for a single torrent."""
        return self.torrent_client.get_torrent_info(torrent_hash)

    def get_all_torrents(self) -> List[TorrentInfo]:
        """Get info for all torrents."""
        return self.torrent_client.get_all_torrents()

    def get_torrent_files(self, torrent_hash: str) -> Optional[List[dict]]:
        """Get file list for a torrent, or None if not found."""
        info = self.torrent_client.get_torrent_info(torrent_hash)
        return info.files if info else None

    def set_file_priority(self, torrent_hash: str, file_index: int, priority: int) -> None:
        """Set download priority for a specific file in a torrent."""
        self.torrent_client.set_file_priority(torrent_hash, file_index, priority)

    def set_download_limit(self, limit_kbps: int) -> None:
        """Set global download speed limit in KB/s."""
        self.torrent_client.set_download_limit(limit_kbps)

    def set_upload_limit(self, limit_kbps: int) -> None:
        """Set global upload speed limit in KB/s."""
        self.torrent_client.set_upload_limit(limit_kbps)

    def get_torrent_stats(self) -> dict:
        """Get aggregate torrent statistics."""
        return self.torrent_client.get_stats()

    # ── YouTube operations ──────────────────────────────────────────────

    def add_youtube_download(self, url: str, fmt: str = "best",
                             save_path: Optional[str] = None,
                             reencode: bool = False) -> str:
        """Start a YouTube/web video download.

        Args:
            url: Video URL to download.
            fmt: Format specification (e.g. 'mp4_best', 'mp3_192').
            save_path: Custom save directory (uses default if None).
            reencode: If True, re-encode video to mp4 for better compatibility.

        Returns:
            Download ID string.
        """
        return self.youtube_client.add_download(url, fmt=fmt, save_path=save_path, reencode=reencode)

    def remove_youtube_download(self, download_id: str) -> None:
        """Cancel and remove a YouTube download."""
        self.youtube_client.remove_download(download_id)

    def get_all_youtube_downloads(self) -> list:
        """Get all YouTube download info as dicts."""
        return self.youtube_client.get_all_downloads()

    def get_youtube_download(self, download_id: str) -> Optional[dict]:
        """Get info for a single YouTube download."""
        return self.youtube_client.get_download(download_id)

    # ── Unified operations ──────────────────────────────────────────────

    def get_all_downloads(self) -> Dict[str, list]:
        """Get all downloads grouped by type.

        Returns:
            Dict with 'torrents' and 'youtube' keys.
        """
        return {
            'torrents': [t.to_dict() for t in self.torrent_client.get_all_torrents()],
            'youtube': self.youtube_client.get_all_downloads()
        }

    def set_download_path(self, new_path: str) -> None:
        """Update the default download path and apply it to active download clients."""
        import os
        abs_path = os.path.abspath(new_path)
        os.makedirs(abs_path, exist_ok=True)
        
        self.settings.update_download_path(abs_path)
        self.torrent_client.save_path = abs_path
        self.youtube_client.save_path = abs_path
        logger.info("Default download path updated to: %s", abs_path)

    def is_safe_path(self, path: str) -> bool:
        """Validate a save path is within allowed directory.

        Delegates to Settings for the actual check.
        """
        return self.settings.is_safe_path(path)
