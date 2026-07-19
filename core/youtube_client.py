import yt_dlp
import threading
import uuid
import os
import logging
from typing import Dict, List, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    """Raised when a download is cancelled by the user."""
    pass


class YTDownloadState(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class YTDownloadInfo:
    id: str
    url: str
    title: str
    state: YTDownloadState
    progress: float
    speed: float
    total_size: int
    downloaded: int
    save_path: str
    format: str
    error: str = ""
    thumbnail: str = ""
    reencode: bool = False

    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'state': self.state.value,
            'progress': self.progress,
            'speed': self.speed,
            'total_size': self.total_size,
            'downloaded': self.downloaded,
            'save_path': self.save_path,
            'format': self.format,
            'error': self.error,
            'thumbnail': self.thumbnail,
            'reencode': self.reencode,
        }


class YouTubeClient:
    def __init__(self, save_path: str = "./downloads"):
        self.save_path = os.path.abspath(save_path)
        os.makedirs(self.save_path, exist_ok=True)
        self.downloads: Dict[str, YTDownloadInfo] = {}
        self.callbacks: List[Callable] = []
        self._lock = threading.Lock()
        self._cancel_events: Dict[str, threading.Event] = {}

    def add_callback(self, callback: Callable):
        self.callbacks.append(callback)

    def _notify(self, event: str, data: dict):
        """Emit event to all callbacks. Must be called OUTSIDE _lock."""
        for cb in self.callbacks:
            try:
                cb(event, data)
            except Exception as e:
                logger.warning("Callback error for event '%s': %s", event, e)

    def add_download(self, url: str, fmt: str = "best", save_path: str = None, reencode: bool = False) -> str:
        """Start a YouTube/web video download. Returns a unique download ID.

        Args:
            url: Video URL to download.
            fmt: Format specification (e.g. 'mp4_best', 'mp3_192').
            save_path: Custom save directory (uses default if None).
            reencode: If True, re-encode video to mp4 for better compatibility.
        """
        download_id = str(uuid.uuid4())
        save_path = os.path.abspath(save_path) if save_path else self.save_path

        info = YTDownloadInfo(
            id=download_id,
            url=url,
            title="Fetching info...",
            state=YTDownloadState.QUEUED,
            progress=0.0,
            speed=0.0,
            total_size=0,
            downloaded=0,
            save_path=save_path,
            format=fmt,
            reencode=reencode,
        )

        with self._lock:
            self.downloads[download_id] = info

        self._notify('yt_added', {'id': download_id})

        thread = threading.Thread(
            target=self._download_worker,
            args=(download_id, url, fmt, save_path, reencode),
            daemon=True
        )
        thread.start()
        return download_id

    def _build_ydl_opts(self, fmt: str, save_path: str, progress_hook) -> dict:
        opts = {
            'outtmpl': os.path.join(save_path, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }

        if fmt.startswith('mp3_'):
            quality = fmt.split('_')[1]
            opts['format'] = 'bestaudio/best'
            preferred_quality = '192' if quality == 'best' else quality
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': preferred_quality,
            }]
        elif fmt.startswith('mp4_'):
            quality = fmt.split('_')[1]
            if quality == 'best':
                # Prefer H.264 (avc) for best compatibility, fallback to any video+audio
                opts['format'] = 'bv*[vcodec^=avc1]+ba/bv*+ba/b'
            else:
                try:
                    height = int(quality)
                except ValueError:
                    height = 720
                # Prefer H.264 (avc) at specified height, fallback to any codec
                opts['format'] = (
                    f'bv*[vcodec^=avc1][height<={height}]+ba'
                    f'/bv*[height<={height}]+ba'
                    f'/b[height<={height}]'
                    f'/b'
                )
            opts['merge_output_format'] = 'mp4'
        else:
            # Fallback for backward compatibility
            if fmt == 'audio_mp3':
                opts['format'] = 'ba/b'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            elif fmt == 'video_720':
                opts['format'] = 'bv*[vcodec^=avc1][height<=720]+ba/bv*[height<=720]+ba/b'
                opts['merge_output_format'] = 'mp4'
            elif fmt == 'video_1080':
                opts['format'] = 'bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b'
                opts['merge_output_format'] = 'mp4'
            elif fmt == 'video_480':
                opts['format'] = 'bv*[vcodec^=avc1][height<=480]+ba/bv*[height<=480]+ba/b'
                opts['merge_output_format'] = 'mp4'
            else:
                opts['format'] = 'bv*[vcodec^=avc1]+ba/bv*+ba/b'
                opts['merge_output_format'] = 'mp4'

        return opts

    def _download_worker(self, download_id: str, url: str, fmt: str, save_path: str, reencode: bool = False):
        snapshot = {}

        # Register a cancellation event for this download
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[download_id] = cancel_event

        def progress_hook(d):
            nonlocal snapshot

            # Check for cancellation — raises to abort yt-dlp
            if cancel_event.is_set():
                raise CancelledError("Download cancelled by user")

            with self._lock:
                info = self.downloads.get(download_id)
                if not info:
                    # Download was removed — abort immediately
                    raise CancelledError("Download removed")

                status = d.get('status')
                if status == 'downloading':
                    info.state = YTDownloadState.DOWNLOADING
                    downloaded = d.get('downloaded_bytes', 0) or 0
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    info.downloaded = downloaded
                    info.total_size = total
                    info.progress = (downloaded / total * 100) if total > 0 else 0
                    raw_speed = d.get('speed') or 0
                    info.speed = raw_speed / 1024  # KB/s
                    snapshot = info.to_dict()
                elif status == 'finished':
                    info.state = YTDownloadState.PROCESSING
                    info.progress = 99.0
                    snapshot = info.to_dict()
                else:
                    return

            self._notify('yt_updated', snapshot)

        ydl_opts = self._build_ydl_opts(fmt, save_path, progress_hook)

        # Common extra options for better compatibility
        ydl_opts.update({
            'socket_timeout': 30,  # Prevent hanging on unreachable URLs
        })

        # Add re-encode option only in safe mode
        if reencode:
            ydl_opts['recode-video'] = 'mp4'

        def _try_download(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Check cancellation before metadata extraction
                if cancel_event.is_set():
                    raise CancelledError("Download cancelled before starting")

                # Fetch metadata first to get title + thumbnail
                try:
                    meta = ydl.extract_info(url, download=False)
                    title = meta.get('title', 'Unknown')
                    thumbnail = meta.get('thumbnail', '')
                except CancelledError:
                    raise
                except Exception as meta_err:
                    logger.warning("Could not fetch metadata: %s", meta_err)
                    title = 'Unknown'
                    thumbnail = ''

                # Check cancellation again after metadata
                if cancel_event.is_set():
                    raise CancelledError("Download cancelled after metadata")

                with self._lock:
                    info = self.downloads.get(download_id)
                    if info:
                        info.title = title
                        info.thumbnail = thumbnail
                        info.state = YTDownloadState.DOWNLOADING
                        snap = info.to_dict()
                    else:
                        snap = None
                if snap:
                    self._notify('yt_updated', snap)

                ydl.download([url])

        try:
            # Check cancellation before starting at all
            if cancel_event.is_set():
                raise CancelledError("Download cancelled before starting")

            _try_download(ydl_opts)

            # Only mark finished if the download still exists (wasn't removed mid-flight)
            with self._lock:
                info = self.downloads.get(download_id)
                if info:
                    info.state = YTDownloadState.FINISHED
                    info.progress = 100.0
                    snapshot = info.to_dict()

            if info:
                self._notify('yt_finished', {'id': download_id, 'title': snapshot.get('title', '')})
                self._notify('yt_updated', snapshot)

        except CancelledError:
            logger.info("YouTube download %s cancelled by user", download_id)
            # Don't emit error — it was intentional
        except Exception as e:
            logger.error("YouTube download failed for %s: %s", url, e)
            error_snapshot = None
            with self._lock:
                info = self.downloads.get(download_id)
                if info:
                    info.state = YTDownloadState.ERROR
                    info.error = str(e)
                    error_snapshot = info.to_dict()

            self._notify('yt_error', {'id': download_id, 'error': str(e)})
            if error_snapshot:
                self._notify('yt_updated', error_snapshot)
        finally:
            with self._lock:
                self._cancel_events.pop(download_id, None)

    def remove_download(self, download_id: str):
        # Signal cancellation first so the worker thread can abort
        with self._lock:
            cancel_event = self._cancel_events.get(download_id)
            if cancel_event:
                cancel_event.set()
            if download_id in self.downloads:
                del self.downloads[download_id]
        self._notify('yt_removed', {'id': download_id})

    def get_all_downloads(self) -> list:
        with self._lock:
            return [d.to_dict() for d in self.downloads.values()]

    def get_download(self, download_id: str):
        with self._lock:
            d = self.downloads.get(download_id)
            return d.to_dict() if d else None
