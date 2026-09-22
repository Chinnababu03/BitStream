import yt_dlp
import threading
import uuid
import os
import logging
import re
from typing import Dict, List, Callable, Optional, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


def sanitize_folder_name(name: str) -> str:
    """Sanitize a playlist title for use as a folder name on Windows/Linux."""
    if not name:
        return "YouTube Playlist"
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    cleaned = cleaned.strip(". ")
    return cleaned if cleaned else "YouTube Playlist"


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
    def __init__(self, save_path: str = "./downloads", max_concurrent_downloads: int = 3):
        self.save_path = os.path.abspath(save_path)
        os.makedirs(self.save_path, exist_ok=True)
        self.downloads: Dict[str, YTDownloadInfo] = {}
        self.callbacks: List[Callable] = []
        self._lock = threading.Lock()
        self._cancel_events: Dict[str, threading.Event] = {}
        self._max_concurrent = max_concurrent_downloads
        self._active_downloads = 0
        self._queue: List[str] = []

    def add_callback(self, callback: Callable):
        self.callbacks.append(callback)

    def _notify(self, event: str, data: dict):
        """Emit event to all callbacks. Must be called OUTSIDE _lock."""
        for cb in self.callbacks:
            try:
                cb(event, data)
            except Exception as e:
                logger.warning("Callback error for event '%s': %s", event, e)

    def _process_queue(self):
        """Start queued downloads if under max concurrency limit."""
        to_start = []
        with self._lock:
            while self._active_downloads < self._max_concurrent and len(self._queue) > 0:
                download_id = self._queue.pop(0)
                info = self.downloads.get(download_id)
                cancel_event = self._cancel_events.get(download_id)
                if not info or not cancel_event or cancel_event.is_set():
                    continue
                self._active_downloads += 1
                to_start.append((download_id, info.url, info.format, info.save_path, info.reencode))

        for download_id, url, fmt, spath, reencode in to_start:
            thread = threading.Thread(
                target=self._download_worker,
                args=(download_id, url, fmt, spath, reencode),
                daemon=True
            )
            thread.start()

    def _extract_playlist_info(self, url: str) -> dict:
        """Check if URL points to a playlist and return entry metadata."""
        opts = {
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'mweb']
                }
            },
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                meta = ydl.extract_info(url, download=False)
                if meta:
                    entries = meta.get('entries')
                    if entries is not None and isinstance(entries, (list, tuple)) and len(entries) > 0:
                        valid_entries = []
                        for e in entries:
                            if isinstance(e, dict):
                                v_url = e.get('url') or e.get('webpage_url')
                                v_id = e.get('id') or ''
                                if not v_url and v_id:
                                    v_url = f"https://www.youtube.com/watch?v={v_id}"
                                v_title = e.get('title') or "Untitled Track"
                                if v_url:
                                    valid_entries.append({
                                        'url': v_url,
                                        'title': v_title,
                                        'id': v_id
                                    })
                        if valid_entries:
                            return {
                                'is_playlist': True,
                                'playlist_title': meta.get('title') or 'YouTube Playlist',
                                'entries': valid_entries
                            }
        except Exception as e:
            logger.warning("Could not extract playlist info for URL %s: %s", url, e)

        return {'is_playlist': False, 'playlist_title': '', 'entries': []}

    def add_download(self, url: str, fmt: str = "best", save_path: str = None,
                     reencode: bool = False, process_playlist: bool = True) -> Union[str, dict]:
        """Start a YouTube/web video or playlist download.

        Returns a unique download ID string for single videos, or a dict for playlists containing:
        {'id': primary_id, 'ids': [...], 'is_playlist': True, 'count': N, 'playlist_title': title}.
        """
        base_save_path = os.path.abspath(save_path) if save_path else self.save_path

        if process_playlist:
            pl_info = self._extract_playlist_info(url)
            if pl_info['is_playlist'] and pl_info['entries']:
                pl_title = pl_info['playlist_title']
                folder_name = sanitize_folder_name(pl_title)
                target_save_path = os.path.join(base_save_path, folder_name)
                os.makedirs(target_save_path, exist_ok=True)

                created_ids = []
                for entry in pl_info['entries']:
                    item_id = str(uuid.uuid4())
                    cancel_event = threading.Event()
                    item_info = YTDownloadInfo(
                        id=item_id,
                        url=entry['url'],
                        title=entry['title'],
                        state=YTDownloadState.QUEUED,
                        progress=0.0,
                        speed=0.0,
                        total_size=0,
                        downloaded=0,
                        save_path=target_save_path,
                        format=fmt,
                        reencode=reencode,
                    )
                    with self._lock:
                        self.downloads[item_id] = item_info
                        self._cancel_events[item_id] = cancel_event
                        self._queue.append(item_id)

                    created_ids.append(item_id)
                    self._notify('yt_added', {'id': item_id})

                self._process_queue()

                primary_id = created_ids[0] if created_ids else ""
                return {
                    'id': primary_id,
                    'ids': created_ids,
                    'is_playlist': True,
                    'count': len(created_ids),
                    'playlist_title': pl_title
                }

        # Single video download
        download_id = str(uuid.uuid4())
        cancel_event = threading.Event()
        info = YTDownloadInfo(
            id=download_id,
            url=url,
            title="Fetching info...",
            state=YTDownloadState.QUEUED,
            progress=0.0,
            speed=0.0,
            total_size=0,
            downloaded=0,
            save_path=base_save_path,
            format=fmt,
            reencode=reencode,
        )

        with self._lock:
            self.downloads[download_id] = info
            self._cancel_events[download_id] = cancel_event
            self._queue.append(download_id)

        self._notify('yt_added', {'id': download_id})
        self._process_queue()

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
                opts['format'] = 'bv*[vcodec^=avc1]+ba/bv*+ba/b'
            else:
                try:
                    height = int(quality)
                except ValueError:
                    height = 720
                opts['format'] = (
                    f'bv*[vcodec^=avc1][height<={height}]+ba'
                    f'/bv*[height<={height}]+ba'
                    f'/b[height<={height}]'
                    f'/b'
                )
            opts['merge_output_format'] = 'mp4'
        else:
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

        opts.update({
            'socket_timeout': 30,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'mweb']
                }
            },
            'nocheckcertificate': True,
        })

        return opts

    def _download_worker(self, download_id: str, url: str, fmt: str, save_path: str, reencode: bool = False):
        snapshot = {}

        with self._lock:
            cancel_event = self._cancel_events.get(download_id)
        if not cancel_event:
            cancel_event = threading.Event()
            with self._lock:
                self._cancel_events[download_id] = cancel_event

        def progress_hook(d):
            nonlocal snapshot

            if cancel_event.is_set():
                raise CancelledError("Download cancelled by user")

            with self._lock:
                info = self.downloads.get(download_id)
                if not info:
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
        ydl_opts.update({'socket_timeout': 30})

        if reencode:
            ydl_opts['recode-video'] = 'mp4'

        def _try_download(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                if cancel_event.is_set():
                    raise CancelledError("Download cancelled before starting")

                try:
                    meta = ydl.extract_info(url, download=False)
                    title = meta.get('title', 'Unknown')
                    thumbnail = meta.get('thumbnail', '')
                except CancelledError:
                    raise
                except Exception as meta_err:
                    logger.warning("Could not fetch metadata: %s", meta_err)
                    with self._lock:
                        existing_info = self.downloads.get(download_id)
                        title = existing_info.title if (existing_info and existing_info.title != "Fetching info...") else 'Unknown'
                        thumbnail = existing_info.thumbnail if existing_info else ''

                if cancel_event.is_set():
                    raise CancelledError("Download cancelled after metadata")

                with self._lock:
                    info = self.downloads.get(download_id)
                    if info:
                        if title and title != 'Unknown':
                            info.title = title
                        if thumbnail:
                            info.thumbnail = thumbnail
                        info.state = YTDownloadState.DOWNLOADING
                        snap = info.to_dict()
                    else:
                        snap = None
                if snap:
                    self._notify('yt_updated', snap)

                ydl.download([url])

        try:
            if cancel_event.is_set():
                raise CancelledError("Download cancelled before starting")

            _try_download(ydl_opts)

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
                self._active_downloads = max(0, self._active_downloads - 1)
            self._process_queue()

    def remove_download(self, download_id: str):
        with self._lock:
            if download_id in self._queue:
                self._queue.remove(download_id)
            cancel_event = self._cancel_events.pop(download_id, None)
            if cancel_event:
                cancel_event.set()
            if download_id in self.downloads:
                del self.downloads[download_id]
        self._notify('yt_removed', {'id': download_id})
        self._process_queue()

    def get_all_downloads(self) -> list:
        with self._lock:
            return [d.to_dict() for d in self.downloads.values()]

    def get_download(self, download_id: str):
        with self._lock:
            d = self.downloads.get(download_id)
            return d.to_dict() if d else None

