# BitStream

A self-hosted download manager with a web UI that downloads BitTorrent magnet links and extracts web streams from YouTube, Vimeo, Twitch, and more.

BitStream bridges the gap between peer-to-peer downloading and web video archiving by letting you download torrents (via magnet links or `.torrent` files) and capture online streams (from YouTube, Vimeo, and 1000+ other video sites) directly to your local storage through a single, responsive glassmorphic dashboard.

---

## Features

- **Dual Download Engines**: Integrated BitTorrent client (powered by `libtorrent`) and media stream extractor (powered by `yt-dlp`).
- **Premium Web UI**: A modern, responsive dark-mode control panel featuring real-time download status, speeds, and peer statistics with active Socket.IO bindings.
- **Smart Media Conversion**: Downloads streams as raw video (MP4) or automatically extracts and transcodes audio to MP3.
- **File Prioritization**: Set individual file priorities (Don't Download / Normal / High / Max) for torrent downloads.
- **Speed Limits**: Configure global download/upload speed limits to manage network bandwidth.
- **Self-Hosted & Private**: Lightweight Python backend designed to run on a local server, NAS, or in a Docker container.

---

## Quick Start

### Option 1: Docker (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/Chinnababu03/BitStream.git
   cd BitStream
   ```
2. Start the container in the background:
   ```bash
   docker-compose up -d
   ```
3. Access the web UI at **[http://localhost:8080](http://localhost:8080)**.

---

### Option 2: Manual Local Startup

Ensure you have Python 3.8+ installed.

#### On Windows:
1. Run the automatic startup script:
   ```cmd
   .\start.bat
   ```

#### On Linux / macOS:
1. Make the script executable and run it:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

#### Or Run Manually:
1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```
2. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

---

## Usage & Controls Distinction

Because BitStream integrates two different download technologies, they have different capabilities:

| Feature | BitTorrent Downloads (Magnet/Files) | YouTube / Web Video Downloads |
| :--- | :--- | :--- |
| **Engine** | Peer-to-peer pieces via `libtorrent` | Direct HTTP stream extraction via `yt-dlp` |
| **Pause & Resume** | ✅ **Supported** (individual and "Pause All" / "Resume All") | ❌ **Unsupported** (stream extractions cannot be paused) |
| **Cancellation** | ✅ Supported (via Delete/Trash icon) | ✅ Supported (via Delete/Trash icon) |
| **Card Action Buttons** | Pause/Resume, Info (i), and Delete (Trash) | Info (i) and Delete (Cancel) |

---

## Project Structure

```
BitStream/
├── core/
│   └── torrent_client.py    # libtorrent wrapper with thread-safe operations
├── web/
│   ├── app.py               # Flask + SocketIO server
│   ├── templates/
│   │   └── index.html       # Redesigned premium Web UI template
│   └── static/
│       └── app.js           # Frontend client-side Socket.IO bindings
├── downloads/               # Default download directory
├── config/                  # Configuration storage
├── Dockerfile               # Docker image definition
├── docker-compose.yml       # Docker Compose service definition
├── requirements.txt         # Python dependencies
└── run_book.txt             # Deployment runbook
```

---

## Contributing

We welcome contributions to BitStream! To propose changes and collaborate:

1. **Fork the Project** on GitHub.
2. **Create your Feature Branch**:
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3. **Commit your Changes**:
   ```bash
   git commit -m 'Add some AmazingFeature'
   ```
4. **Push to the Branch**:
   ```bash
   git push origin feature/AmazingFeature
   ```
5. **Open a Pull Request** to the `main` branch.

Please ensure your code follows the existing style and is well-documented.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.