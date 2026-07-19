"""
Tests for TorrentClient, TorrentInfo, TorrentState, and helper functions.

Tests the public interfaces at seams, not implementation details.
Uses mocks for libtorrent to avoid requiring the actual dependency.
"""

import pytest
import time
import os
import tempfile
import threading
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import asdict


# ---------------------------------------------------------------------------
# Import the modules under test (with mocked libtorrent)
# ---------------------------------------------------------------------------

# Mock libtorrent before importing torrent_client
mock_lt = MagicMock()
mock_lt.session.return_value = MagicMock()
mock_lt.torrent_flags.auto_managed = 0x01
mock_lt.torrent_flags.paused = 0x02
mock_lt.alert.category_t.all_categories = 0xFFFFFFFF
mock_lt.torrent_status.queued_for_checking = 0
mock_lt.torrent_status.checking_files = 1
mock_lt.torrent_status.checking_resume_data = 2
mock_lt.torrent_status.downloading_metadata = 3
mock_lt.torrent_status.downloading = 4
mock_lt.torrent_status.finished = 5
mock_lt.torrent_status.seeding = 6
mock_lt.torrent_status.allocating = 7
mock_lt.session.delete_files = 0x01

with patch.dict('sys.modules', {'libtorrent': mock_lt}):
    from core.torrent_client import (
        TorrentClient, TorrentInfo, TorrentState,
        format_size, format_speed
    )


# ---------------------------------------------------------------------------
# Tests for TorrentState enum
# ---------------------------------------------------------------------------

class TestTorrentState:
    """Test TorrentState enum values."""

    def test_states_have_correct_values(self):
        assert TorrentState.QUEUED.value == "queued"
        assert TorrentState.CHECKING.value == "checking"
        assert TorrentState.DOWNLOADING.value == "downloading"
        assert TorrentState.SEEDING.value == "seeding"
        assert TorrentState.PAUSED.value == "paused"
        assert TorrentState.ERROR.value == "error"
        assert TorrentState.FINISHED.value == "finished"

    def test_all_states_are_string_enum(self):
        for state in TorrentState:
            assert isinstance(state.value, str)


# ---------------------------------------------------------------------------
# Tests for TorrentInfo dataclass
# ---------------------------------------------------------------------------

class TestTorrentInfo:
    """Test TorrentInfo dataclass."""

    def _make_info(self, **kwargs):
        """Create a TorrentInfo with sensible defaults."""
        defaults = {
            'hash': 'abc123def456',
            'name': 'Test Torrent',
            'state': TorrentState.DOWNLOADING,
            'progress': 50.0,
            'download_rate': 1024.0,
            'upload_rate': 512.0,
            'num_peers': 10,
            'num_seeds': 5,
            'total_size': 1073741824,  # 1 GB
            'downloaded': 536870912,   # 512 MB
            'uploaded': 268435456,     # 256 MB
            'save_path': '/downloads',
            'added_time': time.time(),
        }
        defaults.update(kwargs)
        return TorrentInfo(**defaults)

    def test_to_dict_converts_state_to_string(self):
        info = self._make_info(state=TorrentState.DOWNLOADING)
        d = info.to_dict()
        assert d['state'] == 'downloading'

    def test_to_dict_converts_timestamps_to_iso(self):
        now = time.time()
        info = self._make_info(added_time=now, finished_time=now)
        d = info.to_dict()
        assert 'T' in d['added_time']  # ISO format contains T
        assert 'T' in d['finished_time']

    def test_to_dict_handles_zero_finished_time(self):
        info = self._make_info(finished_time=0)
        d = info.to_dict()
        assert d['finished_time'] is None

    def test_to_dict_includes_all_fields(self):
        info = self._make_info()
        d = info.to_dict()
        expected_keys = {
            'hash', 'name', 'state', 'progress', 'download_rate',
            'upload_rate', 'num_peers', 'num_seeds', 'total_size',
            'downloaded', 'uploaded', 'save_path', 'added_time',
            'finished_time', 'error', 'files'
        }
        assert expected_keys.issubset(set(d.keys()))


# ---------------------------------------------------------------------------
# Tests for format_size helper
# ---------------------------------------------------------------------------

class TestFormatSize:
    """Test format_size helper function."""

    def test_zero_bytes(self):
        assert format_size(0) == "0.00 B"

    def test_one_byte(self):
        assert format_size(1) == "1.00 B"

    def test_one_kilobyte(self):
        assert format_size(1024) == "1.00 KB"

    def test_one_megabyte(self):
        assert format_size(1024 * 1024) == "1.00 MB"

    def test_one_gigabyte(self):
        assert format_size(1024 ** 3) == "1.00 GB"

    def test_one_terabyte(self):
        assert format_size(1024 ** 4) == "1.00 TB"

    def test_fractional_values(self):
        assert format_size(1536) == "1.50 KB"  # 1.5 KB

    def test_large_values(self):
        assert format_size(1024 ** 5) == "1.00 PB"


# ---------------------------------------------------------------------------
# Tests for format_speed helper
# ---------------------------------------------------------------------------

class TestFormatSpeed:
    """Test format_speed helper function."""

    def test_zero_speed(self):
        assert format_speed(0) == "0.00 B/s"

    def test_one_kbps(self):
        assert format_speed(1024) == "1.00 KB/s"

    def test_one_mbps(self):
        assert format_speed(1024 * 1024) == "1.00 MB/s"


# ---------------------------------------------------------------------------
# Tests for TorrentClient
# ---------------------------------------------------------------------------

class TestTorrentClient:
    """Test TorrentClient public interface."""

    def _make_client(self, **kwargs):
        """Create a TorrentClient with mocked session."""
        defaults = {
            'save_path': tempfile.mkdtemp(),
            'listen_port': 6881,
        }
        defaults.update(kwargs)
        return TorrentClient(**defaults)

    def test_initialization_creates_save_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = os.path.join(tmpdir, 'test_downloads')
            client = TorrentClient(save_path=save_path)
            assert os.path.exists(save_path)

    def test_add_callback(self):
        client = self._make_client()
        callback = Mock()
        client.add_callback(callback)
        assert callback in client.callbacks

    def test_notify_calls_all_callbacks(self):
        client = self._make_client()
        cb1 = Mock()
        cb2 = Mock()
        client.add_callback(cb1)
        client.add_callback(cb2)
        client._notify('test_event', {'key': 'value'})
        cb1.assert_called_once_with('test_event', {'key': 'value'})
        cb2.assert_called_once_with('test_event', {'key': 'value'})

    def test_notify_handles_callback_exception(self):
        client = self._make_client()
        bad_callback = Mock(side_effect=RuntimeError("callback error"))
        good_callback = Mock()
        client.add_callback(bad_callback)
        client.add_callback(good_callback)
        # Should not raise, should still call good_callback
        client._notify('test_event', {})
        good_callback.assert_called_once()

    def test_add_torrent_with_magnet(self):
        client = self._make_client()
        # Mock the session to return a handle
        mock_handle = MagicMock()
        mock_handle.info_hash.return_value = 'abc123'
        mock_handle.has_metadata.return_value = False
        mock_handle.name.return_value = 'Test Torrent'
        client.session.add_torrent.return_value = mock_handle

        callback = Mock()
        client.add_callback(callback)

        result = client.add_torrent('magnet:?xt=urn:btih:abc123')

        assert result == 'abc123'
        callback.assert_called_with('torrent_added', {'hash': 'abc123'})

    def test_add_torrent_returns_none_on_error(self):
        client = self._make_client()
        client.session.add_torrent.side_effect = RuntimeError("Failed")

        callback = Mock()
        client.add_callback(callback)

        result = client.add_torrent('magnet:?xt=urn:btih:invalid')
        assert result is None
        callback.assert_called_with('error', {'error': 'Failed', 'input': 'magnet:?xt=urn:btih:invalid'})

    def test_remove_torrent(self):
        client = self._make_client()
        mock_handle = MagicMock()
        client.torrents['abc123'] = mock_handle
        client.torrent_info['abc123'] = self._make_info(hash='abc123')

        callback = Mock()
        client.add_callback(callback)

        client.remove_torrent('abc123')

        assert 'abc123' not in client.torrents
        assert 'abc123' not in client.torrent_info
        callback.assert_called_with('torrent_removed', {'hash': 'abc123'})

    def test_pause_torrent(self):
        client = self._make_client()
        mock_handle = MagicMock()
        client.torrents['abc123'] = mock_handle
        client.torrent_info['abc123'] = self._make_info(hash='abc123', state=TorrentState.DOWNLOADING)

        callback = Mock()
        client.add_callback(callback)

        client.pause_torrent('abc123')

        mock_handle.auto_managed.assert_called_with(False)
        mock_handle.pause.assert_called_once()
        assert client.torrent_info['abc123'].state == TorrentState.PAUSED
        callback.assert_called_with('torrent_paused', {'hash': 'abc123'})

    def test_resume_torrent(self):
        client = self._make_client()
        mock_handle = MagicMock()
        client.torrents['abc123'] = mock_handle
        client.torrent_info['abc123'] = self._make_info(hash='abc123', state=TorrentState.PAUSED)

        callback = Mock()
        client.add_callback(callback)

        client.resume_torrent('abc123')

        mock_handle.auto_managed.assert_called_with(True)
        mock_handle.resume.assert_called_once()
        callback.assert_called_with('torrent_resumed', {'hash': 'abc123'})

    def test_pause_all(self):
        client = self._make_client()
        mock_handle1 = MagicMock()
        mock_handle2 = MagicMock()
        client.torrents['abc123'] = mock_handle1
        client.torrents['def456'] = mock_handle2
        client.torrent_info['abc123'] = self._make_info(hash='abc123')
        client.torrent_info['def456'] = self._make_info(hash='def456')

        callback = Mock()
        client.add_callback(callback)

        client.pause_all()

        mock_handle1.auto_managed.assert_called_with(False)
        mock_handle1.pause.assert_called_once()
        mock_handle2.auto_managed.assert_called_with(False)
        mock_handle2.pause.assert_called_once()
        assert client.torrent_info['abc123'].state == TorrentState.PAUSED
        assert client.torrent_info['def456'].state == TorrentState.PAUSED
        callback.assert_called_with('all_paused', {})

    def test_resume_all(self):
        client = self._make_client()
        mock_handle = MagicMock()
        client.torrents['abc123'] = mock_handle
        client.torrent_info['abc123'] = self._make_info(hash='abc123', state=TorrentState.PAUSED)

        callback = Mock()
        client.add_callback(callback)

        client.resume_all()

        mock_handle.auto_managed.assert_called_with(True)
        mock_handle.resume.assert_called_once()
        callback.assert_called_with('all_resumed', {})

    def test_get_torrent_info(self):
        client = self._make_client()
        info = self._make_info(hash='abc123')
        client.torrent_info['abc123'] = info

        result = client.get_torrent_info('abc123')
        assert result == info

    def test_get_torrent_info_returns_none_for_unknown(self):
        client = self._make_client()
        result = client.get_torrent_info('unknown')
        assert result is None

    def test_get_all_torrents(self):
        client = self._make_client()
        info1 = self._make_info(hash='abc123')
        info2 = self._make_info(hash='def456')
        client.torrent_info['abc123'] = info1
        client.torrent_info['def456'] = info2

        result = client.get_all_torrents()
        assert len(result) == 2
        assert info1 in result
        assert info2 in result

    def test_get_stats(self):
        client = self._make_client()
        client.torrent_info['abc123'] = self._make_info(
            hash='abc123',
            state=TorrentState.DOWNLOADING,
            download_rate=1024.0,
            upload_rate=512.0,
            num_peers=10
        )
        client.torrent_info['def456'] = self._make_info(
            hash='def456',
            state=TorrentState.SEEDING,
            download_rate=0.0,
            upload_rate=256.0,
            num_peers=5
        )
        client.torrents['abc123'] = MagicMock()
        client.torrents['def456'] = MagicMock()

        stats = client.get_stats()
        assert stats['total_download_rate'] == 1024.0
        assert stats['total_upload_rate'] == 768.0
        assert stats['total_peers'] == 15
        assert stats['downloading_count'] == 1
        assert stats['seeding_count'] == 1
        assert stats['total_torrents'] == 2

    def test_start_and_stop(self):
        client = self._make_client()
        callback = Mock()
        client.add_callback(callback)

        client.start()
        assert client._running is True
        assert client._thread is not None
        callback.assert_called_with('started', {})

        client.stop()
        assert client._running is False
        callback.assert_called_with('stopped', {})

    def test_set_download_limit(self):
        client = self._make_client()
        client.set_download_limit(1000)  # 1000 KB/s
        client.session.set_download_rate_limit.assert_called_with(1000 * 1024)

    def test_set_upload_limit(self):
        client = self._make_client()
        client.set_upload_limit(500)  # 500 KB/s
        client.session.set_upload_rate_limit.assert_called_with(500 * 1024)

    def _make_info(self, **kwargs):
        """Helper to create TorrentInfo for tests."""
        defaults = {
            'hash': 'abc123',
            'name': 'Test Torrent',
            'state': TorrentState.DOWNLOADING,
            'progress': 50.0,
            'download_rate': 1024.0,
            'upload_rate': 512.0,
            'num_peers': 10,
            'num_seeds': 5,
            'total_size': 1073741824,
            'downloaded': 536870912,
            'uploaded': 268435456,
            'save_path': '/downloads',
            'added_time': time.time(),
        }
        defaults.update(kwargs)
        return TorrentInfo(**defaults)
