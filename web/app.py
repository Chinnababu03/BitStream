"""
DownloadHub Web Application.

Flask + SocketIO web layer. Uses the DownloadManager facade for all download
operations, and the EventBus for real-time updates.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import logging
import tempfile
import os

from core.config import Settings
from core.event_bus import EventBus, get_event_bus
from core.download_manager import DownloadManager
from core.container import create_container

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def create_app(settings: Settings = None) -> tuple:
    """Application factory. Creates the Flask app and wires everything up.

    Args:
        settings: Optional settings override (for testing).

    Returns:
        Tuple of (app, socketio, container).
    """
    # Create container with provided settings or defaults
    container = create_container(settings=settings)
    app_settings = container.settings
    event_bus = container.event_bus
    manager = container.download_manager

    # -----------------------------------------------------------------------
    # Flask + SocketIO
    # -----------------------------------------------------------------------
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')
    app.config['SECRET_KEY'] = app_settings.secret_key
    app.config['MAX_CONTENT_LENGTH'] = app_settings.max_upload_size

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

    # -----------------------------------------------------------------------
    # Event bus → SocketIO bridge
    # -----------------------------------------------------------------------
    def on_event(event: str, data: dict):
        """Forward events from the event bus to WebSocket clients."""
        socketio.emit(event, data)

    event_bus.subscribe_all(on_event)

    # -----------------------------------------------------------------------
    # Page routes
    # -----------------------------------------------------------------------

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/health')
    def health():
        """Health check endpoint for Docker / monitoring."""
        return jsonify({
            'status': 'ok',
            'service': 'DownloadHub',
            'download_path': app_settings.download_path,
        })

    # -----------------------------------------------------------------------
    # Torrent API
    # -----------------------------------------------------------------------

    @app.route('/api/torrents', methods=['GET'])
    def get_torrents():
        torrents = [t.to_dict() for t in manager.get_all_torrents()]
        return jsonify(torrents)

    @app.route('/api/torrents', methods=['POST'])
    def add_torrent():
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        magnet = (data.get('magnet') or '').strip()
        save_path_raw = data.get('save_path')
        save_path = save_path_raw.strip() if save_path_raw else None

        if not magnet:
            return jsonify({'error': 'No magnet link provided'}), 400

        if not magnet.startswith('magnet:'):
            return jsonify({'error': 'Invalid magnet link (must start with magnet:)'}), 400

        # Validate custom save path
        if save_path:
            if not manager.is_safe_path(save_path):
                return jsonify({'error': 'Save path is outside the allowed downloads directory'}), 400
        else:
            save_path = app_settings.download_path

        hash_str = manager.add_torrent(magnet, save_path)
        if hash_str:
            return jsonify({'hash': hash_str, 'success': True})
        return jsonify({'error': 'Failed to add torrent. Check the magnet link.'}), 500

    @app.route('/api/upload-torrent', methods=['POST'])
    def upload_torrent():
        """Accept a .torrent file upload, save it temporarily, and add it."""
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        f = request.files['file']
        if not f.filename or not f.filename.lower().endswith('.torrent'):
            return jsonify({'error': 'File must be a .torrent file'}), 400

        save_path = request.form.get('save_path', '').strip() or app_settings.download_path
        if not manager.is_safe_path(save_path):
            return jsonify({'error': 'Save path is outside the allowed downloads directory'}), 400

        # Save to a temp file in the system temp directory
        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.torrent')
            os.close(tmp_fd)
            f.save(tmp_path)

            hash_str = manager.add_torrent(tmp_path, save_path)

            # Remove temp file (libtorrent has parsed it already)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

            if hash_str:
                return jsonify({'hash': hash_str, 'success': True})
            return jsonify({'error': 'Failed to parse .torrent file'}), 500

        except Exception as e:
            logger.error("Error uploading .torrent: %s", e)
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return jsonify({'error': str(e)}), 500

    @app.route('/api/torrents/<hash_str>', methods=['DELETE'])
    def remove_torrent(hash_str):
        data = request.get_json() or {}
        delete_files = data.get('delete_files', False)
        manager.remove_torrent(hash_str, delete_files)
        return jsonify({'success': True})

    @app.route('/api/torrents/<hash_str>/pause', methods=['POST'])
    def pause_torrent(hash_str):
        manager.pause_torrent(hash_str)
        return jsonify({'success': True})

    @app.route('/api/torrents/<hash_str>/resume', methods=['POST'])
    def resume_torrent(hash_str):
        manager.resume_torrent(hash_str)
        return jsonify({'success': True})

    @app.route('/api/torrents/<hash_str>/files', methods=['GET'])
    def get_torrent_files(hash_str):
        files = manager.get_torrent_files(hash_str)
        if files is None:
            return jsonify({'error': 'Torrent not found'}), 404
        return jsonify({'files': files or []})

    @app.route('/api/torrents/<hash_str>/files/<int:file_index>/priority', methods=['POST'])
    def set_file_priority(hash_str, file_index):
        data = request.get_json() or {}
        priority = data.get('priority', 1)
        manager.set_file_priority(hash_str, file_index, int(priority))
        return jsonify({'success': True})

    @app.route('/api/stats', methods=['GET'])
    def get_stats():
        return jsonify(manager.get_torrent_stats())

    @app.route('/api/settings', methods=['GET'])
    def get_settings():
        return jsonify({
            'download_limit': 0,
            'upload_limit': 0,
            'save_path': manager.settings.download_path
        })

    @app.route('/api/settings', methods=['POST'])
    def update_settings():
        data = request.get_json() or {}
        if data.get('download_limit') is not None:
            manager.set_download_limit(int(data['download_limit']))
        if data.get('upload_limit') is not None:
            manager.set_upload_limit(int(data['upload_limit']))
        if data.get('save_path') is not None:
            try:
                manager.set_download_path(data['save_path'].strip())
            except Exception as e:
                logger.error("Failed to update download path: %s", e)
                return jsonify({'error': str(e)}), 400
        return jsonify({'success': True})

    @app.route('/api/pause-all', methods=['POST'])
    def pause_all():
        manager.pause_all_torrents()
        return jsonify({'success': True})

    @app.route('/api/resume-all', methods=['POST'])
    def resume_all():
        manager.resume_all_torrents()
        return jsonify({'success': True})

    @app.route('/api/browse-dir', methods=['GET'])
    def browse_dir():
        """API for browsing directories on the server's local file system."""
        path_query = request.args.get('path', '').strip()
        
        # If no path is provided, default to user's home directory
        if not path_query:
            path_query = os.path.expanduser("~")
            
        path_abs = os.path.abspath(path_query)
        
        # If the path does not exist, fall back to home or root
        if not os.path.exists(path_abs) or not os.path.isdir(path_abs):
            path_abs = os.path.expanduser("~")
            if not os.path.exists(path_abs):
                path_abs = os.path.abspath(os.sep)
                
        subdirs = []
        drives = []
        
        try:
            for name in os.listdir(path_abs):
                full_path = os.path.join(path_abs, name)
                if os.path.isdir(full_path):
                    # Exclude system folders and hidden directories
                    if not name.startswith('.') and not name.startswith('$') and name.lower() != 'system volume information':
                        subdirs.append(name)
            subdirs.sort(key=str.lower)
        except Exception:
            # Handle permission errors gracefully
            pass
            
        parent = os.path.dirname(path_abs)
        # If parent is equal to path, we are at the system root (e.g. C:\ or /)
        if parent == path_abs:
            parent = None
            
        # Drive detection on Windows when parent is None (at root level)
        if os.name == 'nt' and not parent:
            import string
            try:
                from ctypes import windll
                bitmask = windll.kernel32.GetLogicalDrives()
                for letter in string.ascii_uppercase:
                    if bitmask & 1:
                        drives.append(f"{letter}:\\")
                    bitmask >>= 1
            except Exception:
                pass
                
        return jsonify({
            'current_path': path_abs,
            'parent_path': parent,
            'subdirs': subdirs,
            'drives': drives
        })

    # -----------------------------------------------------------------------
    # YouTube API
    # -----------------------------------------------------------------------

    @app.route('/api/youtube', methods=['GET'])
    def get_yt_downloads():
        return jsonify(manager.get_all_youtube_downloads())

    @app.route('/api/youtube', methods=['POST'])
    def add_yt_download():
        data = request.get_json() or {}
        url = (data.get('url') or '').strip()
        fmt = (data.get('format') or 'best').strip()
        save_path_raw = data.get('save_path')
        save_path = save_path_raw.strip() if save_path_raw else app_settings.download_path
        reencode = data.get('reencode', False)  # Safe re-encode mode

        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        allowed_qualities = {'best', '1080', '720', '480', '360', '320', '192', '128'}
        is_valid = False
        if fmt in {'best', 'video_720', 'video_1080', 'video_480', 'audio_mp3'}:
            is_valid = True
        elif '_' in fmt:
            parts = fmt.split('_', 1)
            if parts[0] in {'mp4', 'mp3'} and parts[1] in allowed_qualities:
                is_valid = True

        if not is_valid:
            fmt = 'mp4_best'

        if not manager.is_safe_path(save_path):
            return jsonify({'error': 'Save path is outside the allowed downloads directory'}), 400

        download_id = manager.add_youtube_download(url, fmt=fmt, save_path=save_path, reencode=reencode)
        return jsonify({'id': download_id, 'success': True})

    @app.route('/api/youtube/<download_id>', methods=['DELETE'])
    def remove_yt_download(download_id):
        manager.remove_youtube_download(download_id)
        return jsonify({'success': True})

    # -----------------------------------------------------------------------
    # File serving
    # -----------------------------------------------------------------------

    @app.route('/downloads/<path:filename>')
    def serve_download(filename):
        return send_from_directory(app_settings.download_path, filename)

    # -----------------------------------------------------------------------
    # WebSocket events
    # -----------------------------------------------------------------------

    @socketio.on('connect')
    def handle_connect():
        emit('connected', {
            'torrents': [t.to_dict() for t in manager.get_all_torrents()],
            'yt_downloads': manager.get_all_youtube_downloads()
        })

    @socketio.on('request_update')
    def handle_request_update():
        emit('torrents_update', [t.to_dict() for t in manager.get_all_torrents()])
        emit('yt_update', manager.get_all_youtube_downloads())

    return app, socketio, container
