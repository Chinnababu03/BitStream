import libtorrent as lt
import time
import os
import logging
import threading
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class TorrentState(Enum):
    QUEUED = "queued"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    PAUSED = "paused"
    ERROR = "error"
    FINISHED = "finished"


@dataclass
class TorrentInfo:
    hash: str
    name: str
    state: TorrentState
    progress: float
    download_rate: float
    upload_rate: float
    num_peers: int
    num_seeds: int
    total_size: int
    downloaded: int
    uploaded: int
    save_path: str
    added_time: float
    finished_time: float = 0
    error: str = ""
    files: List[dict] = None

    def to_dict(self):
        d = asdict(self)
        d['state'] = self.state.value
        d['added_time'] = datetime.fromtimestamp(self.added_time).isoformat() if self.added_time else None
        d['finished_time'] = datetime.fromtimestamp(self.finished_time).isoformat() if self.finished_time else None
        return d


class TorrentClient:
    def __init__(self, save_path: str = "./downloads", listen_port: int = 6881):
        self.save_path = os.path.abspath(save_path)
        os.makedirs(self.save_path, exist_ok=True)

        self.session = lt.session()
        self.session.listen_on(listen_port, listen_port + 10)
        # Set alert mask once
        self.session.set_alert_mask(lt.alert.category_t.all_categories)

        self.torrents: Dict[str, lt.torrent_handle] = {}
        self.torrent_info: Dict[str, TorrentInfo] = {}
        self.callbacks: List[Callable] = []
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # Start DHT and peer discovery services
        try:
            self.session.start_dht()
        except Exception:
            pass
        try:
            self.session.start_lsd()
            self.session.start_upnp()
            self.session.start_natpmp()
        except Exception:
            pass

        self._apply_settings()

    def _apply_settings(self):
        settings = {
            'download_rate_limit': 0,
            'upload_rate_limit': 0,
            'connections_limit': 200,
            'listen_queue_size': 5,
            'active_downloads': 3,
            'active_seeds': 5,
            'active_limit': 8,
            'dont_count_slow_torrents': True,
            'auto_manage_startup': 5,
            'auto_manage_interval': 30,
            'enable_dht': True,
        }
        self.session.apply_settings(settings)

    def add_callback(self, callback: Callable):
        self.callbacks.append(callback)

    def _notify(self, event: str, data: dict):
        """Emit an event to all registered callbacks. Must be called OUTSIDE of _lock."""
        for cb in self.callbacks:
            try:
                cb(event, data)
            except Exception as e:
                logger.warning("Callback error for event '%s': %s", event, e)

    def add_torrent(self, torrent_input: str, save_path: str = None) -> Optional[str]:
        """Add torrent from magnet link or .torrent file path"""
        save_path = save_path or self.save_path

        try:
            if torrent_input.startswith('magnet:'):
                params = lt.parse_magnet_uri(torrent_input)
                params.save_path = save_path
                params.flags |= lt.torrent_flags.auto_managed
                handle = self.session.add_torrent(params)
            else:
                info = lt.torrent_info(torrent_input)
                params = lt.add_torrent_params()
                params.ti = info
                params.save_path = save_path
                params.flags |= lt.torrent_flags.auto_managed
                handle = self.session.add_torrent(params)

            torrent_hash = str(handle.info_hash())

            with self._lock:
                self.torrents[torrent_hash] = handle
                self.torrent_info[torrent_hash] = TorrentInfo(
                    hash=torrent_hash,
                    name=handle.name() if handle.has_metadata() else "Loading...",
                    state=TorrentState.QUEUED,
                    progress=0.0,
                    download_rate=0.0,
                    upload_rate=0.0,
                    num_peers=0,
                    num_seeds=0,
                    total_size=0,
                    downloaded=0,
                    uploaded=0,
                    save_path=save_path,
                    added_time=time.time(),
                    files=[]
                )

            self._notify('torrent_added', {'hash': torrent_hash})
            return torrent_hash

        except Exception as e:
            logger.error("Failed to add torrent '%s': %s", torrent_input, e)
            self._notify('error', {'error': str(e), 'input': torrent_input})
            return None

    def remove_torrent(self, torrent_hash: str, delete_files: bool = False):
        with self._lock:
            if torrent_hash in self.torrents:
                handle = self.torrents[torrent_hash]
                if delete_files:
                    self.session.remove_torrent(handle, lt.session.delete_files)
                else:
                    self.session.remove_torrent(handle)
                del self.torrents[torrent_hash]
                if torrent_hash in self.torrent_info:
                    del self.torrent_info[torrent_hash]
        self._notify('torrent_removed', {'hash': torrent_hash})

    def pause_torrent(self, torrent_hash: str):
        with self._lock:
            if torrent_hash in self.torrents:
                handle = self.torrents[torrent_hash]
                handle.auto_managed(False)
                handle.pause()
                self.torrent_info[torrent_hash].state = TorrentState.PAUSED
        self._notify('torrent_paused', {'hash': torrent_hash})

    def resume_torrent(self, torrent_hash: str):
        with self._lock:
            if torrent_hash in self.torrents:
                handle = self.torrents[torrent_hash]
                handle.auto_managed(True)
                handle.resume()
                if torrent_hash in self.torrent_info:
                    self.torrent_info[torrent_hash].state = TorrentState.QUEUED
        self._notify('torrent_resumed', {'hash': torrent_hash})

    def pause_all(self):
        with self._lock:
            for handle in self.torrents.values():
                handle.auto_managed(False)
                handle.pause()
            for info in self.torrent_info.values():
                info.state = TorrentState.PAUSED
        self._notify('all_paused', {})

    def resume_all(self):
        with self._lock:
            for handle in self.torrents.values():
                handle.auto_managed(True)
                handle.resume()
            for info in self.torrent_info.values():
                if info.state == TorrentState.PAUSED:
                    info.state = TorrentState.QUEUED
        self._notify('all_resumed', {})

    def set_download_limit(self, limit_kbps: int):
        self.session.set_download_rate_limit(limit_kbps * 1024)

    def set_upload_limit(self, limit_kbps: int):
        self.session.set_upload_rate_limit(limit_kbps * 1024)

    def get_torrent_info(self, torrent_hash: str) -> Optional[TorrentInfo]:
        with self._lock:
            return self.torrent_info.get(torrent_hash)

    def get_all_torrents(self) -> List[TorrentInfo]:
        with self._lock:
            return list(self.torrent_info.values())

    def _update_torrent_info_locked(self, handle: lt.torrent_handle, torrent_hash: str, pending_events: list):
        """Update torrent info while _lock is held. Appends events to pending_events instead of emitting."""
        if not handle.is_valid():
            return

        status = handle.status()

        # In libtorrent 2.x, paused is a flag not a state
        # Check paused flag first
        try:
            is_paused = bool(status.flags & lt.torrent_flags.paused)
        except Exception:
            is_paused = False

        state_map = {
            lt.torrent_status.queued_for_checking:  TorrentState.QUEUED,
            lt.torrent_status.checking_files:       TorrentState.CHECKING,
            lt.torrent_status.checking_resume_data: TorrentState.CHECKING,
            lt.torrent_status.downloading_metadata: TorrentState.QUEUED,
            lt.torrent_status.downloading:          TorrentState.DOWNLOADING,
            lt.torrent_status.finished:             TorrentState.FINISHED,
            lt.torrent_status.seeding:              TorrentState.SEEDING,
            lt.torrent_status.allocating:           TorrentState.QUEUED,
        }
        # Add paused state mapping if it exists (libtorrent 1.x)
        if hasattr(lt.torrent_status, 'paused'):
            state_map[lt.torrent_status.paused] = TorrentState.PAUSED

        # Determine if the torrent has an error
        # In libtorrent 2.x, error_file is -1 (file_index_t::none) when there is NO error.
        # -1 is truthy in Python, so we must check != -1, not just bool().
        has_error = False
        try:
            has_error = (status.error_file != -1)
        except Exception:
            has_error = bool(status.error_file) if status.error_file else False
        # Also check errc (error code) for actual errors (e.g. tracker errors)
        if not has_error:
            try:
                has_error = (status.errc.value() != 0)
            except Exception:
                pass

        if has_error:
            state = TorrentState.ERROR
        elif is_paused:
            state = TorrentState.PAUSED
        else:
            state = state_map.get(status.state, TorrentState.QUEUED)

        info = self.torrent_info.get(torrent_hash)
        if info:
            old_state = info.state
            info.state = state
            info.progress = status.progress * 100
            info.download_rate = status.download_rate / 1024
            info.upload_rate = status.upload_rate / 1024
            info.num_peers = status.num_peers
            info.num_seeds = status.num_seeds
            info.total_size = status.total_wanted
            info.downloaded = status.total_wanted_done
            info.uploaded = status.total_upload
            info.error = str(status.error_file) if has_error else ""

            if handle.has_metadata() and info.name == "Loading...":
                info.name = handle.name()
                ti = handle.torrent_file()
                if ti:
                    info.files = []
                    for i in range(ti.num_files()):
                        fe = ti.file_at(i)
                        info.files.append({
                            'index': i,
                            'path': fe.path,
                            'size': fe.size,
                            'priority': handle.file_priority(i)
                        })

            if state == TorrentState.FINISHED and old_state != TorrentState.FINISHED:
                info.finished_time = time.time()
                pending_events.append(('torrent_finished', {'hash': torrent_hash, 'name': info.name}))
            elif state == TorrentState.ERROR and old_state != TorrentState.ERROR:
                pending_events.append(('torrent_error', {'hash': torrent_hash, 'error': info.error}))

            pending_events.append(('torrent_updated', info.to_dict()))

    def _process_alerts(self):
        alerts = self.session.pop_alerts()
        for alert in alerts:
            try:
                if isinstance(alert, lt.metadata_received_alert):
                    hash_str = str(alert.handle.info_hash())
                    self._notify('metadata_received', {'hash': hash_str, 'name': alert.handle.name()})
                elif isinstance(alert, lt.torrent_error_alert):
                    hash_str = str(alert.handle.info_hash())
                    self._notify('torrent_error', {'hash': hash_str, 'error': str(alert)})
            except Exception as e:
                logger.warning("Error processing alert: %s", e)

    def _update_loop(self):
        while self._running:
            pending_events = []

            # Collect all state updates under the lock, but do NOT emit inside it
            with self._lock:
                for hash_str, handle in list(self.torrents.items()):
                    if handle.is_valid():
                        self._update_torrent_info_locked(handle, hash_str, pending_events)
                    else:
                        logger.warning("Removing invalid torrent handle: %s", hash_str)
                        del self.torrents[hash_str]
                        if hash_str in self.torrent_info:
                            del self.torrent_info[hash_str]

            # Emit events outside the lock to prevent deadlocks
            for event, data in pending_events:
                self._notify(event, data)

            self._process_alerts()
            time.sleep(1)

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._update_loop, daemon=True)
            self._thread.start()
            logger.info("TorrentClient started")
            self._notify('started', {})

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.session.pause()
        logger.info("TorrentClient stopped")
        self._notify('stopped', {})

    def get_stats(self) -> dict:
        with self._lock:
            total_download = sum(t.download_rate for t in self.torrent_info.values())
            total_upload = sum(t.upload_rate for t in self.torrent_info.values())
            total_peers = sum(t.num_peers for t in self.torrent_info.values())
            downloading = sum(1 for t in self.torrent_info.values() if t.state == TorrentState.DOWNLOADING)
            seeding = sum(1 for t in self.torrent_info.values() if t.state == TorrentState.SEEDING)

            return {
                'total_download_rate': total_download,
                'total_upload_rate': total_upload,
                'total_peers': total_peers,
                'downloading_count': downloading,
                'seeding_count': seeding,
                'total_torrents': len(self.torrents)
            }

    def set_file_priority(self, torrent_hash: str, file_index: int, priority: int):
        with self._lock:
            if torrent_hash in self.torrents:
                self.torrents[torrent_hash].file_priority(file_index, priority)

    def get_session_stats(self) -> dict:
        stats = self.session.status()
        return {
            'total_download': stats.total_download,
            'total_upload': stats.total_upload,
            'payload_download_rate': stats.payload_download_rate / 1024,
            'payload_upload_rate': stats.payload_upload_rate / 1024,
            'num_peers': stats.num_peers,
            'dht_nodes': stats.dht_nodes
        }


def format_size(bytes_val: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"


def format_speed(bytes_per_sec: float) -> str:
    return format_size(bytes_per_sec) + "/s"