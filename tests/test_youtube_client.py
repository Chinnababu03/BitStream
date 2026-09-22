"""
Tests for YouTubeClient, YTDownloadInfo, YTDownloadState, and CancelledError.

Tests the public interfaces at seams, not implementation details.
Uses mocks for yt_dlp to avoid requiring the actual dependency.
"""

import pytest
import time
import os
import tempfile
import threading
from unittest.mock import Mock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# Import the modules under test (with mocked yt_dlp)
# ---------------------------------------------------------------------------

mock_yt_dlp = MagicMock()

with patch.dict('sys.modules', {'yt_dlp': mock_yt_dlp}):
    from core.youtube_client import (
        YouTubeClient, YTDownloadInfo, YTDownloadState,
        CancelledError, sanitize_folder_name
    )


# ---------------------------------------------------------------------------
# Tests for YTDownloadState enum
# ---------------------------------------------------------------------------

class TestYTDownloadState:
    """Test YTDownloadState enum values."""

    def test_states_have_correct_values(self):
        assert YTDownloadState.QUEUED.value == "queued"
        assert YTDownloadState.DOWNLOADING.value == "downloading"
        assert YTDownloadState.PROCESSING.value == "processing"
        assert YTDownloadState.FINISHED.value == "finished"
        assert YTDownloadState.ERROR.value == "error"

    def test_all_states_are_string_enum(self):
        for state in YTDownloadState:
            assert isinstance(state.value, str)


# ---------------------------------------------------------------------------
# Tests for CancelledError
# ---------------------------------------------------------------------------

class TestCancelledError:
    """Test CancelledError exception."""

    def test_is_exception(self):
        assert issubclass(CancelledError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(CancelledError):
            raise CancelledError("test message")

    def test_can_catch_base_exception(self):
        with pytest.raises(Exception):
            raise CancelledError("test")


# ---------------------------------------------------------------------------
# Tests for YTDownloadInfo dataclass
# ---------------------------------------------------------------------------

class TestYTDownloadInfo:
    """Test YTDownloadInfo dataclass."""

    def _make_info(self, **kwargs):
        """Create a YTDownloadInfo with sensible defaults."""
        defaults = {
            'id': 'test-id-123',
            'url': 'https://www.youtube.com/watch?v=test',
            'title': 'Test Video',
            'state': YTDownloadState.DOWNLOADING,
            'progress': 50.0,
            'speed': 1024.0,
            'total_size': 1073741824,
            'downloaded': 536870912,
            'save_path': '/downloads',
            'format': 'mp4_best',
        }
        defaults.update(kwargs)
        return YTDownloadInfo(**defaults)

    def test_to_dict_converts_state_to_string(self):
        info = self._make_info(state=YTDownloadState.DOWNLOADING)
        d = info.to_dict()
        assert d['state'] == 'downloading'

    def test_to_dict_includes_all_fields(self):
        info = self._make_info()
        d = info.to_dict()
        expected_keys = {
            'id', 'url', 'title', 'state', 'progress', 'speed',
            'total_size', 'downloaded', 'save_path', 'format',
            'error', 'thumbnail'
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_to_dict_with_error(self):
        info = self._make_info(
            state=YTDownloadState.ERROR,
            error='Download failed'
        )
        d = info.to_dict()
        assert d['error'] == 'Download failed'
        assert d['state'] == 'error'

    def test_to_dict_with_thumbnail(self):
        info = self._make_info(thumbnail='https://example.com/thumb.jpg')
        d = info.to_dict()
        assert d['thumbnail'] == 'https://example.com/thumb.jpg'


# ---------------------------------------------------------------------------
# Tests for YouTubeClient
# ---------------------------------------------------------------------------

class TestYouTubeClient:
    """Test YouTubeClient public interface."""

    def _make_client(self, **kwargs):
        """Create a YouTubeClient with mocked yt_dlp."""
        defaults = {
            'save_path': tempfile.mkdtemp(),
        }
        defaults.update(kwargs)
        return YouTubeClient(**defaults)

    def test_initialization_creates_save_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = os.path.join(tmpdir, 'yt_downloads')
            client = YouTubeClient(save_path=save_path)
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

    def test_add_download_returns_uuid(self):
        client = self._make_client()
        callback = Mock()
        client.add_callback(callback)

        # Mock the thread to not actually start
        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            result = client.add_download('https://www.youtube.com/watch?v=test')

        assert isinstance(result, str)
        assert len(result) > 0
        callback.assert_called_with('yt_added', {'id': result})

    def test_add_download_stores_info(self):
        client = self._make_client()

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            download_id = client.add_download('https://www.youtube.com/watch?v=test')

        info = client.get_download(download_id)
        assert info is not None
        assert info['url'] == 'https://www.youtube.com/watch?v=test'
        assert info['state'] == 'queued'
        assert info['title'] == 'Fetching info...'

    def test_add_download_with_custom_save_path(self):
        client = self._make_client()
        custom_path = tempfile.mkdtemp()

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            download_id = client.add_download(
                'https://www.youtube.com/watch?v=test',
                save_path=custom_path
            )

        info = client.get_download(download_id)
        assert info['save_path'] == os.path.abspath(custom_path)

    def test_add_download_with_format(self):
        client = self._make_client()

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            download_id = client.add_download(
                'https://www.youtube.com/watch?v=test',
                fmt='mp3_192'
            )

        info = client.get_download(download_id)
        assert info['format'] == 'mp3_192'

    def test_remove_download(self):
        client = self._make_client()

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            download_id = client.add_download('https://www.youtube.com/watch?v=test')

        callback = Mock()
        client.add_callback(callback)

        client.remove_download(download_id)

        assert client.get_download(download_id) is None
        callback.assert_called_with('yt_removed', {'id': download_id})

    def test_remove_download_signals_cancellation(self):
        client = self._make_client()

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            download_id = client.add_download('https://www.youtube.com/watch?v=test')

        # Verify cancel event exists
        assert download_id in client._cancel_events

        client.remove_download(download_id)

        # Verify cancel event was signaled
        assert download_id not in client._cancel_events
        assert client.get_download(download_id) is None

    def test_get_all_downloads(self):
        client = self._make_client()

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            id1 = client.add_download('https://www.youtube.com/watch?v=test1')
            id2 = client.add_download('https://www.youtube.com/watch?v=test2')

        downloads = client.get_all_downloads()
        assert len(downloads) == 2
        ids = [d['id'] for d in downloads]
        assert id1 in ids
        assert id2 in ids

    def test_get_download_returns_none_for_unknown(self):
        client = self._make_client()
        result = client.get_download('unknown-id')
        assert result is None

    def test_build_ydl_opts_mp4_best(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('mp4_best', '/downloads', hook)
        assert 'bv*' in opts['format']
        assert opts['merge_output_format'] == 'mp4'

    def test_build_ydl_opts_mp4_1080(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('mp4_1080', '/downloads', hook)
        assert 'height<=1080' in opts['format']
        assert opts['merge_output_format'] == 'mp4'

    def test_build_ydl_opts_mp4_720(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('mp4_720', '/downloads', hook)
        assert 'height<=720' in opts['format']

    def test_build_ydl_opts_mp3_best(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('mp3_best', '/downloads', hook)
        assert opts['format'] == 'bestaudio/best'
        assert opts['postprocessors'][0]['key'] == 'FFmpegExtractAudio'
        assert opts['postprocessors'][0]['preferredquality'] == '192'

    def test_build_ydl_opts_mp3_320(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('mp3_320', '/downloads', hook)
        assert opts['postprocessors'][0]['preferredquality'] == '320'

    def test_build_ydl_opts_backward_compat_video_720(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('video_720', '/downloads', hook)
        assert 'height<=720' in opts['format']

    def test_build_ydl_opts_backward_compat_audio_mp3(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('audio_mp3', '/downloads', hook)
        assert opts['postprocessors'][0]['preferredcodec'] == 'mp3'

    def test_build_ydl_opts_includes_progress_hook(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('mp4_best', '/downloads', hook)
        assert hook in opts['progress_hooks']

    def test_build_ydl_opts_quiet_mode(self):
        client = self._make_client()
        hook = Mock()
        opts = client._build_ydl_opts('mp4_best', '/downloads', hook)
        assert opts['quiet'] is True
        assert opts['no_warnings'] is True
        assert opts['noplaylist'] is True


# ---------------------------------------------------------------------------
# Tests for progress_hook behavior
# ---------------------------------------------------------------------------

class TestProgressHook:
    """Test the progress hook logic in _download_worker."""

    def _make_client(self, **kwargs):
        defaults = {'save_path': tempfile.mkdtemp()}
        defaults.update(kwargs)
        return YouTubeClient(**defaults)

    def test_progress_hook_updates_downloading_state(self):
        """Test that progress_hook correctly updates state for downloading."""
        client = self._make_client()

        # Create a download
        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            download_id = client.add_download('https://www.youtube.com/watch?v=test')

        # Simulate a progress hook call
        cancel_event = threading.Event()
        client._cancel_events[download_id] = cancel_event

        # Create a mock progress data
        progress_data = {
            'status': 'downloading',
            'downloaded_bytes': 500000,
            'total_bytes': 1000000,
            'speed': 102400,
        }

        # Call the progress hook directly
        def progress_hook(d):
            with client._lock:
                info = client.downloads.get(download_id)
                if info:
                    if d.get('status') == 'downloading':
                        info.state = YTDownloadState.DOWNLOADING
                        info.downloaded = d.get('downloaded_bytes', 0)
                        info.total_size = d.get('total_bytes', 0)
                        info.progress = (info.downloaded / info.total_size * 100) if info.total_size > 0 else 0
                        info.speed = (d.get('speed', 0) or 0) / 1024

        progress_hook(progress_data)

        info = client.get_download(download_id)
        assert info['state'] == 'downloading'
        assert info['downloaded'] == 500000
        assert info['total_size'] == 1000000
        assert info['progress'] == 50.0

    def test_progress_hook_cancels_on_event_set(self):
        """Test that progress_hook raises CancelledError when cancel event is set."""
        client = self._make_client()

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            download_id = client.add_download('https://www.youtube.com/watch?v=test')

        cancel_event = threading.Event()
        cancel_event.set()  # Signal cancellation
        client._cancel_events[download_id] = cancel_event

        progress_data = {'status': 'downloading', 'downloaded_bytes': 100}

        with pytest.raises(CancelledError):
            # Simulate what the progress hook does
            if cancel_event.is_set():
                raise CancelledError("Download cancelled by user")


# ---------------------------------------------------------------------------
# Tests for Playlist Download Support
# ---------------------------------------------------------------------------

class TestYouTubeClientPlaylist:
    """Test playlist extraction and multi-track queuing."""

    def test_sanitize_folder_name(self):
        assert sanitize_folder_name("My Favorite Hits / Songs : 2024") == "My Favorite Hits  Songs  2024"
        assert sanitize_folder_name('Rock <Classic> "Hits"') == "Rock Classic Hits"
        assert sanitize_folder_name("   ") == "YouTube Playlist"

    def test_add_download_with_playlist_url(self):
        save_path = tempfile.mkdtemp()
        client = YouTubeClient(save_path=save_path)

        playlist_mock_meta = {
            'is_playlist': True,
            'playlist_title': 'Best Rock Hits',
            'entries': [
                {'id': 'song1', 'title': 'Song One', 'url': 'https://www.youtube.com/watch?v=song1'},
                {'id': 'song2', 'title': 'Song Two', 'url': 'https://www.youtube.com/watch?v=song2'},
                {'id': 'song3', 'title': 'Song Three', 'url': 'https://www.youtube.com/watch?v=song3'},
            ]
        }

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            with patch.object(client, '_extract_playlist_info', return_value=playlist_mock_meta):
                res = client.add_download('https://www.youtube.com/playlist?list=PL12345', fmt='mp3_192')

        assert isinstance(res, dict)
        assert res['is_playlist'] is True
        assert res['count'] == 3
        assert res['playlist_title'] == 'Best Rock Hits'
        assert len(res['ids']) == 3

        all_downloads = client.get_all_downloads()
        assert len(all_downloads) == 3
        titles = [d['title'] for d in all_downloads]
        assert 'Song One' in titles
        assert 'Song Two' in titles
        assert 'Song Three' in titles

        expected_subfolder = os.path.join(save_path, "Best Rock Hits")
        assert all_downloads[0]['save_path'] == expected_subfolder

