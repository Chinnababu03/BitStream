/* ============================================================
   DownloadHub — Frontend App Logic
   Handles: WebSocket, Torrents, YouTube Downloads, UI state
   ============================================================ */

'use strict';

// ------------------------------------------------------------------
// State
// ------------------------------------------------------------------
let torrentsMap = {};     // hash → torrent object
let ytMap = {};           // id   → yt download object
let currentDeleteHash = null;
let currentTab = 'dashboard';
let currentAddTab = 'torrent';

// ------------------------------------------------------------------
// Socket
// ------------------------------------------------------------------
const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => {
    setConnected(true);
});

socket.on('disconnect', () => {
    setConnected(false);
});

socket.on('connected', (data) => {
    // Bulk-load on initial connect
    if (data.torrents) {
        torrentsMap = {};
        data.torrents.forEach(t => { torrentsMap[t.hash] = t; });
        renderAll();
    }
    if (data.yt_downloads) {
        ytMap = {};
        data.yt_downloads.forEach(d => { ytMap[d.id] = d; });
        renderAll();
    }
});

// Torrent events
socket.on('torrent_added',   () => fetchTorrents());
socket.on('torrent_removed', () => fetchTorrents());
socket.on('all_paused',      () => fetchTorrents());
socket.on('all_resumed',     () => fetchTorrents());

socket.on('torrent_updated', (t) => {
    torrentsMap[t.hash] = t;
    patchTorrentCard(t);
    updateDashStats();
});

socket.on('torrent_finished', (data) => {
    showToast(`✓ Download complete: ${data.name || data.hash}`, 'success');
    fetchTorrents();
});

socket.on('torrent_error', (data) => {
    showToast(`✗ Torrent error: ${data.error}`, 'danger');
});

// YouTube events
socket.on('yt_added',   () => fetchYT());
socket.on('yt_removed', () => fetchYT());

socket.on('yt_updated', (d) => {
    ytMap[d.id] = d;
    patchYTCard(d);
    updateDashStats();
});

socket.on('yt_finished', (data) => {
    showToast(`✓ YouTube download complete: ${data.title || data.id}`, 'success');
});

socket.on('yt_error', (data) => {
    showToast(`✗ YouTube error: ${data.error}`, 'danger');
});

// ------------------------------------------------------------------
// Connection indicator
// ------------------------------------------------------------------
function setConnected(ok) {
    const dot   = document.getElementById('conn-dot');
    const label = document.getElementById('conn-label');
    if (ok) {
        dot.classList.add('connected');
        label.textContent = 'Connected';
    } else {
        dot.classList.remove('connected');
        label.textContent = 'Disconnected';
    }
}

// ------------------------------------------------------------------
// Data fetching
// ------------------------------------------------------------------
function fetchTorrents() {
    fetch('/api/torrents')
        .then(r => r.json())
        .then(data => {
            torrentsMap = {};
            data.forEach(t => { torrentsMap[t.hash] = t; });
            renderTorrents();
            updateDashStats();
            renderDashRecent();
        })
        .catch(err => console.error('fetchTorrents:', err));
}

function fetchYT() {
    fetch('/api/youtube')
        .then(r => r.json())
        .then(data => {
            ytMap = {};
            data.forEach(d => { ytMap[d.id] = d; });
            renderYT();
            updateDashStats();
            renderDashRecent();
        })
        .catch(err => console.error('fetchYT:', err));
}

function fetchAll() {
    fetchTorrents();
    fetchYT();
}

// ------------------------------------------------------------------
// Render helpers
// ------------------------------------------------------------------
function renderAll() {
    renderTorrents();
    renderYT();
    updateDashStats();
    renderDashRecent();
}

// ---- Torrents ----
function renderTorrents() {
    const grid = document.getElementById('torrent-grid');
    const badge = document.getElementById('torrent-badge');
    const label = document.getElementById('torrent-count-label');
    const list = Object.values(torrentsMap);

    badge.textContent = list.length;
    label.textContent = `${list.length} torrent${list.length !== 1 ? 's' : ''}`;

    if (list.length === 0) {
        grid.innerHTML = `<div style="grid-column:1/-1"><div class="empty-state">
            <i class="bi bi-magnet"></i>
            <p>No torrents added yet</p>
            <small>Paste a magnet link or upload a .torrent file</small>
        </div></div>`;
        return;
    }

    grid.innerHTML = list.map(t => torrentCardHTML(t)).join('');
}

function torrentCardHTML(t) {
    const badgeCls = `badge-${t.state}`;
    const fillCls  = `fill-${t.state}`;
    const pct      = typeof t.progress === 'number' ? t.progress.toFixed(1) : '0.0';
    const dlSpeed  = formatSpeed((t.download_rate || 0) * 1024);
    const ulSpeed  = formatSpeed((t.upload_rate  || 0) * 1024);
    const isPaused = t.state === 'paused';

    return `<div class="dl-card" id="tc-${t.hash}">
        <div class="dl-card-header">
            <div class="dl-card-icon" style="background:${stateColor(t.state,true)};color:${stateColor(t.state)}">
                <i class="bi ${torrentIcon(t.state)}"></i>
            </div>
            <div class="dl-card-meta">
                <div class="dl-card-name" title="${esc(t.name)}">${esc(t.name)}</div>
                <div class="dl-card-sub">${formatSize(t.total_size)} · ${t.num_peers} peers / ${t.num_seeds} seeds</div>
            </div>
            <span class="dl-badge ${badgeCls}">${t.state}</span>
        </div>
        <div class="progress-wrap">
            <div class="progress-bar">
                <div class="progress-fill ${fillCls}" style="width:${pct}%"></div>
            </div>
            <div class="progress-stats">
                <span><i class="bi bi-arrow-down" style="color:var(--accent)"></i><span class="val">${dlSpeed}</span></span>
                <span><i class="bi bi-arrow-up" style="color:var(--green)"></i><span class="val">${ulSpeed}</span></span>
                <span><i class="bi bi-people" style="color:var(--text-muted)"></i><span class="val">${t.num_peers}</span></span>
                <span class="dl-pct">${pct}%</span>
            </div>
        </div>
        <div class="dl-card-actions">
            <button class="btn btn-ghost btn-sm" onclick="togglePause('${t.hash}','${t.state}')" title="${isPaused ? 'Resume' : 'Pause'}">
                <i class="bi ${isPaused ? 'bi-play-fill' : 'bi-pause-fill'}"></i>
                ${isPaused ? 'Resume' : 'Pause'}
            </button>
            <button class="btn btn-ghost btn-sm" onclick="showTorrentDetails('${t.hash}')">
                <i class="bi bi-info-circle"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="confirmDelete('${t.hash}','${esc(t.name)}')">
                <i class="bi bi-trash3"></i>
            </button>
        </div>
    </div>`;
}

function patchTorrentCard(t) {
    const card = document.getElementById(`tc-${t.hash}`);
    if (!card) {
        // Card not yet in DOM — re-render
        renderTorrents();
        renderDashRecent();
        return;
    }

    const pct = typeof t.progress === 'number' ? t.progress.toFixed(1) : '0.0';

    // Progress bar
    const fill = card.querySelector('.progress-fill');
    if (fill) {
        fill.style.width = `${pct}%`;
        fill.className = `progress-fill fill-${t.state}`;
    }

    // Stats
    const valEls = card.querySelectorAll('.progress-stats .val');
    if (valEls.length >= 3) {
        valEls[0].textContent = formatSpeed((t.download_rate || 0) * 1024);
        valEls[1].textContent = formatSpeed((t.upload_rate  || 0) * 1024);
        valEls[2].textContent = t.num_peers;
    }
    const pctEl = card.querySelector('.dl-pct');
    if (pctEl) pctEl.textContent = `${pct}%`;

    // Badge
    const badge = card.querySelector('.dl-badge');
    if (badge) { badge.className = `dl-badge badge-${t.state}`; badge.textContent = t.state; }

    // Name (may have resolved from "Loading...")
    const nameEl = card.querySelector('.dl-card-name');
    if (nameEl && t.name !== 'Loading...') nameEl.textContent = t.name;

    // Icon
    const iconBox = card.querySelector('.dl-card-icon');
    if (iconBox) {
        iconBox.style.color       = stateColor(t.state);
        iconBox.style.background  = stateColor(t.state, true);
        iconBox.innerHTML = `<i class="bi ${torrentIcon(t.state)}"></i>`;
    }

    // Pause button
    const pauseBtn = card.querySelector('.dl-card-actions button:first-child');
    if (pauseBtn) {
        const isPaused = t.state === 'paused';
        pauseBtn.innerHTML = `<i class="bi ${isPaused ? 'bi-play-fill' : 'bi-pause-fill'}"></i> ${isPaused ? 'Resume' : 'Pause'}`;
        pauseBtn.title = isPaused ? 'Resume' : 'Pause';
        pauseBtn.onclick = () => togglePause(t.hash, t.state);
    }

    // Also refresh dash sub-size
    const subEl = card.querySelector('.dl-card-sub');
    if (subEl) subEl.textContent = `${formatSize(t.total_size)} · ${t.num_peers} peers / ${t.num_seeds} seeds`;
}

// ---- YouTube ----
function renderYT() {
    const grid  = document.getElementById('yt-grid');
    const badge = document.getElementById('yt-badge');
    const label = document.getElementById('yt-count-label');
    const list  = Object.values(ytMap);

    badge.textContent = list.length;
    label.textContent = `${list.length} download${list.length !== 1 ? 's' : ''}`;

    if (list.length === 0) {
        grid.innerHTML = `<div style="grid-column:1/-1"><div class="empty-state">
            <i class="bi bi-youtube"></i>
            <p>No YouTube downloads yet</p>
            <small>Supports YouTube, Vimeo, Twitter/X, and 1000+ other sites</small>
        </div></div>`;
        return;
    }

    grid.innerHTML = list.map(d => ytCardHTML(d)).join('');
}

function ytCardHTML(d) {
    const badgeCls = `badge-${d.state}`;
    const fillCls  = `fill-${d.state}`;
    const pct      = typeof d.progress === 'number' ? Math.min(100, d.progress).toFixed(1) : '0.0';
    const speed    = formatSpeed((d.speed || 0) * 1024);
    const fmtLabel = getFormatLabel(d.format);

    return `<div class="dl-card" id="ytc-${d.id}">
        <div class="dl-card-header">
            <div class="dl-card-icon" style="background:var(--red-dim);color:var(--red)">
                <i class="bi bi-youtube"></i>
            </div>
            <div class="dl-card-meta">
                <div class="dl-card-name" title="${esc(d.title)}">${esc(d.title)}</div>
                <div class="dl-card-sub">${fmtLabel} · ${formatSize(d.total_size || 0)}</div>
            </div>
            <span class="dl-badge ${badgeCls}">${d.state}</span>
        </div>
        <div class="progress-wrap">
            <div class="progress-bar">
                <div class="progress-fill ${fillCls}" style="width:${pct}%"></div>
            </div>
            <div class="progress-stats">
                <span><i class="bi bi-arrow-down" style="color:var(--accent)"></i><span class="val">${speed}</span></span>
                <span>${formatSize(d.downloaded || 0)} / ${formatSize(d.total_size || 0)}</span>
                <span class="dl-pct">${pct}%</span>
            </div>
        </div>
        <div class="dl-card-actions">
            ${d.state === 'error' ? `<button class="btn btn-ghost btn-sm" onclick="retryYT('${d.id}','${esc(d.url)}','${d.format}')"><i class="bi bi-arrow-clockwise"></i> Retry</button>` : ''}
            <button class="btn btn-ghost btn-sm" onclick="showYTDetails('${d.id}')">
                <i class="bi bi-info-circle"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="removeYTDownload('${d.id}')">
                <i class="bi bi-trash3"></i>
            </button>
        </div>
    </div>`;
}

function patchYTCard(d) {
    const card = document.getElementById(`ytc-${d.id}`);
    if (!card) {
        renderYT();
        renderDashRecent();
        return;
    }

    const pct = typeof d.progress === 'number' ? Math.min(100, d.progress).toFixed(1) : '0.0';
    const speed = formatSpeed((d.speed || 0) * 1024);

    const fill = card.querySelector('.progress-fill');
    if (fill) {
        fill.style.width = `${pct}%`;
        fill.className = `progress-fill fill-${d.state}`;
    }

    const valEls = card.querySelectorAll('.progress-stats .val');
    if (valEls[0]) valEls[0].textContent = speed;

    const pctEl = card.querySelector('.dl-pct');
    if (pctEl) pctEl.textContent = `${pct}%`;

    const badge = card.querySelector('.dl-badge');
    if (badge) { badge.className = `dl-badge badge-${d.state}`; badge.textContent = d.state; }

    const nameEl = card.querySelector('.dl-card-name');
    if (nameEl && d.title && d.title !== 'Fetching info...') nameEl.textContent = d.title;

    const subEl = card.querySelector('.dl-card-sub');
    const fmtLabel = getFormatLabel(d.format);
    if (subEl) subEl.textContent = `${fmtLabel} · ${formatSize(d.total_size || 0)}`;
}

// ---- Dashboard ----
function updateDashStats() {
    const tList = Object.values(torrentsMap);
    const yList = Object.values(ytMap);

    const dlRate = tList.reduce((s, t) => s + (t.download_rate || 0) * 1024, 0);
    const ulRate = tList.reduce((s, t) => s + (t.upload_rate  || 0) * 1024, 0);
    const peers  = tList.reduce((s, t) => s + (t.num_peers    || 0), 0);

    document.getElementById('dash-dl').textContent      = formatSpeed(dlRate);
    document.getElementById('dash-ul').textContent      = formatSpeed(ulRate);
    document.getElementById('dash-peers').textContent   = peers;
    document.getElementById('dash-torrents').textContent= tList.length;
    document.getElementById('dash-yt').textContent      = yList.length;
}

function renderDashRecent() {
    const container = document.getElementById('dash-recent');
    const tList = Object.values(torrentsMap).slice(0, 3).map(t => torrentCardHTML(t));
    const yList = Object.values(ytMap).slice(0, 3).map(d => ytCardHTML(d));
    const combined = [...tList, ...yList].slice(0, 6);

    if (combined.length === 0) {
        container.innerHTML = `<div style="grid-column:1/-1"><div class="empty-state">
            <i class="bi bi-inbox"></i>
            <p>No downloads yet</p>
            <small>Add a magnet link, .torrent file, or YouTube URL to get started</small>
        </div></div>`;
        return;
    }

    container.innerHTML = combined.join('');
}

// ------------------------------------------------------------------
// Torrent actions
// ------------------------------------------------------------------
function addMagnetLink() {
    const input  = document.getElementById('magnet-input');
    const magnet = input.value.trim();

    if (!magnet) { showToast('Please enter a magnet link', 'warning'); return; }
    if (!magnet.startsWith('magnet:')) { showToast('Invalid magnet link (must start with magnet:)', 'warning'); return; }

    const savePath = document.getElementById('torrent-save-path').value.trim() || null;
    const btn = document.getElementById('add-magnet-btn');
    setLoading(btn, true, 'Adding...');

    fetch('/api/torrents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ magnet, save_path: savePath })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Torrent added successfully', 'success');
            input.value = '';
            fetchTorrents();
            showTab('torrents');
        } else {
            showToast(data.error || 'Failed to add torrent', 'danger');
        }
    })
    .catch(() => showToast('Network error — could not add torrent', 'danger'))
    .finally(() => setLoading(btn, false, '<i class="bi bi-link-45deg"></i> Add'));
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.torrent')) {
        showToast('Please select a .torrent file', 'warning');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    const savePath = document.getElementById('torrent-save-path').value.trim();
    if (savePath) formData.append('save_path', savePath);

    showToast(`Uploading ${file.name}...`, 'info');

    fetch('/api/upload-torrent', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Torrent added from file', 'success');
                fetchTorrents();
                showTab('torrents');
            } else {
                showToast(data.error || 'Failed to add .torrent file', 'danger');
            }
        })
        .catch(() => showToast('Upload failed', 'danger'));
}

function togglePause(hash, state) {
    const action = state === 'paused' ? 'resume' : 'pause';
    fetch(`/api/torrents/${hash}/${action}`, { method: 'POST' })
        .then(() => fetchTorrents())
        .catch(err => console.error(err));
}

function confirmDelete(hash, name) {
    currentDeleteHash = hash;
    document.getElementById('delete-modal-title').textContent = `Remove: ${name}`;
    document.getElementById('delete-files-check').checked = false;
    openModal('delete-modal');
}

function deleteTorrent() {
    if (!currentDeleteHash) return;
    const deleteFiles = document.getElementById('delete-files-check').checked;

    fetch(`/api/torrents/${currentDeleteHash}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delete_files: deleteFiles })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Torrent removed', 'success');
            delete torrentsMap[currentDeleteHash];
            renderTorrents();
            renderDashRecent();
            updateDashStats();
        }
    })
    .catch(() => showToast('Error removing torrent', 'danger'))
    .finally(() => {
        closeModal('delete-modal');
        currentDeleteHash = null;
    });
}

function showTorrentDetails(hash) {
    const t = torrentsMap[hash];
    if (!t) return;

    document.getElementById('torrent-modal-title').textContent = t.name;

    const filesHTML = (t.files && t.files.length > 0)
        ? `<div class="file-list">${t.files.map(f => `
            <div class="file-item">
                <i class="bi bi-file-earmark" style="color:var(--text-muted)"></i>
                <span class="file-name" title="${esc(f.path)}">${f.path.split('/').pop() || f.path}</span>
                <span class="file-size">${formatSize(f.size)}</span>
                <select class="priority-select"
                        onchange="setFilePriority('${hash}',${f.index},this.value)">
                    <option value="0" ${f.priority===0?'selected':''}>Skip</option>
                    <option value="1" ${f.priority===1?'selected':''}>Normal</option>
                    <option value="4" ${f.priority===4?'selected':''}>High</option>
                    <option value="7" ${f.priority===7?'selected':''}>Max</option>
                </select>
            </div>`).join('')}</div>`
        : `<p style="color:var(--text-muted);font-size:13px">No file info available yet (metadata loading...)</p>`;

    document.getElementById('torrent-modal-body').innerHTML = `
        <table class="info-table" style="margin-bottom:20px">
            <tr><td class="label">Name</td>    <td class="value">${esc(t.name)}</td></tr>
            <tr><td class="label">Hash</td>    <td class="value"><code>${t.hash}</code></td></tr>
            <tr><td class="label">Status</td>  <td class="value"><span class="dl-badge badge-${t.state}">${t.state}</span></td></tr>
            <tr><td class="label">Progress</td><td class="value">${(t.progress||0).toFixed(2)}%</td></tr>
            <tr><td class="label">Size</td>    <td class="value">${formatSize(t.downloaded)} / ${formatSize(t.total_size)}</td></tr>
            <tr><td class="label">Uploaded</td><td class="value">${formatSize(t.uploaded)}</td></tr>
            <tr><td class="label">DL Speed</td><td class="value">${formatSpeed((t.download_rate||0)*1024)}</td></tr>
            <tr><td class="label">UL Speed</td><td class="value">${formatSpeed((t.upload_rate||0)*1024)}</td></tr>
            <tr><td class="label">Peers / Seeds</td><td class="value">${t.num_peers} / ${t.num_seeds}</td></tr>
            <tr><td class="label">Save Path</td><td class="value" style="font-size:11px;word-break:break-all">${esc(t.save_path)}</td></tr>
            <tr><td class="label">Added</td>   <td class="value">${t.added_time ? new Date(t.added_time).toLocaleString() : '—'}</td></tr>
        </table>
        <div style="font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:10px;text-transform:uppercase;letter-spacing:.05em">Files (${(t.files||[]).length})</div>
        ${filesHTML}`;

    openModal('torrent-modal');
}

function setFilePriority(hash, index, priority) {
    fetch(`/api/torrents/${hash}/files/${index}/priority`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority: parseInt(priority) })
    }).catch(err => console.error(err));
}

// ------------------------------------------------------------------
// YouTube actions
// ------------------------------------------------------------------
function updateYTQualities() {
    const type = document.getElementById('yt-type-select').value;
    const qualSelect = document.getElementById('yt-quality-select');
    if (!qualSelect) return;
    
    let options = [];
    if (type === 'mp4') {
        options = [
            { value: 'best', text: 'Best Quality (auto)' },
            { value: '1080', text: '1080p Full HD' },
            { value: '720', text: '720p HD' },
            { value: '480', text: '480p' },
            { value: '360', text: '360p' }
        ];
    } else {
        options = [
            { value: 'best', text: 'Best Audio (auto)' },
            { value: '320', text: '320 kbps (High Quality)' },
            { value: '192', text: '192 kbps (Standard)' },
            { value: '128', text: '128 kbps (Low Quality)' }
        ];
    }
    
    qualSelect.innerHTML = options.map(opt => `<option value="${opt.value}">${opt.text}</option>`).join('');
}

function getFormatLabel(format) {
    if (!format) return 'Best';
    if (format.startsWith('mp4_')) {
        const q = format.split('_')[1];
        return `Video (MP4) — ${q === 'best' ? 'Best Quality' : q + 'p'}`;
    } else if (format.startsWith('mp3_')) {
        const q = format.split('_')[1];
        return `Audio (MP3) — ${q === 'best' ? 'Best Quality' : q + ' kbps'}`;
    }
    const oldMap = { best:'Best Quality', video_1080:'Video 1080p', video_720:'Video 720p', video_480:'Video 480p', audio_mp3:'Audio MP3' };
    return oldMap[format] || format;
}

function addYouTubeDownload() {
    const url = document.getElementById('yt-url-input').value.trim();
    const type = document.getElementById('yt-type-select').value;
    const quality = document.getElementById('yt-quality-select').value;
    const fmt = `${type}_${quality}`;
    const savePath = document.getElementById('yt-save-path').value.trim() || null;
    const reencode = document.querySelector('input[name="yt-mode"]:checked').value === 'safe';

    if (!url) { showToast('Please enter a URL', 'warning'); return; }

    try { new URL(url); } catch { showToast('Please enter a valid URL', 'warning'); return; }

    const btn = document.getElementById('add-yt-btn');
    setLoading(btn, true, 'Starting...');

    fetch('/api/youtube', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, format: fmt, save_path: savePath, reencode })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('YouTube download started!', 'success');
            document.getElementById('yt-url-input').value = '';
            fetchYT();
            showTab('youtube');
        } else {
            showToast(data.error || 'Failed to start download', 'danger');
        }
    })
    .catch(() => showToast('Network error', 'danger'))
    .finally(() => setLoading(btn, false, '<i class="bi bi-youtube"></i> Start Download'));
}

function removeYTDownload(id) {
    fetch(`/api/youtube/${id}`, { method: 'DELETE' })
        .then(() => {
            delete ytMap[id];
            renderYT();
            renderDashRecent();
            updateDashStats();
            showToast('Download removed', 'success');
        })
        .catch(() => showToast('Error removing download', 'danger'));
}

function retryYT(id, url, fmt) {
    // Chain the retry after the DELETE completes — no more race condition
    fetch(`/api/youtube/${id}`, { method: 'DELETE' })
        .then(() => {
            // Clean up local state
            delete ytMap[id];
            renderYT();
            renderDashRecent();
            updateDashStats();
            // Now safely start the retry with safe mode
            return fetch('/api/youtube', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, format: fmt, reencode: true })
            });
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                fetchYT();
                showToast('Retrying download...', 'info');
            } else {
                showToast(data.error || 'Retry failed', 'danger');
            }
        })
        .catch(() => showToast('Retry failed', 'danger'));
}

function showYTDetails(id) {
    const d = ytMap[id];
    if (!d) return;
    document.getElementById('yt-modal-title').textContent = d.title || 'Download Details';
    const fmtLabel = getFormatLabel(d.format);
    const modeLabel = d.reencode ? '🛡️ Safe Re-encode' : '⚡ Fast Copy';
    const modeColor = d.reencode ? 'var(--green)' : 'var(--accent)';

    document.getElementById('yt-modal-body').innerHTML = `
        <table class="info-table">
            <tr><td class="label">Title</td>     <td class="value">${esc(d.title)}</td></tr>
            <tr><td class="label">URL</td>        <td class="value" style="font-size:11px;word-break:break-all"><a href="${esc(d.url)}" target="_blank">${esc(d.url)}</a></td></tr>
            <tr><td class="label">Status</td>     <td class="value"><span class="dl-badge badge-${d.state}">${d.state}</span></td></tr>
            <tr><td class="label">Mode</td>       <td class="value" style="color:${modeColor}">${modeLabel}</td></tr>
            <tr><td class="label">Format</td>     <td class="value">${fmtLabel}</td></tr>
            <tr><td class="label">Progress</td>   <td class="value">${Math.min(100,d.progress||0).toFixed(1)}%</td></tr>
            <tr><td class="label">Downloaded</td> <td class="value">${formatSize(d.downloaded||0)} / ${formatSize(d.total_size||0)}</td></tr>
            <tr><td class="label">Speed</td>      <td class="value">${formatSpeed((d.speed||0)*1024)}</td></tr>
            <tr><td class="label">Save Path</td>  <td class="value" style="font-size:11px;word-break:break-all">${esc(d.save_path)}</td></tr>
            ${d.error ? `<tr><td class="label" style="color:var(--red)">Error</td><td class="value" style="color:var(--red)">${esc(d.error)}</td></tr>` : ''}
        </table>`;
    openModal('yt-modal');
}

// ------------------------------------------------------------------
// Settings
// ------------------------------------------------------------------
function loadSettings() {
    fetch('/api/settings')
        .then(r => r.json())
        .then(data => {
            document.getElementById('setting-dl-limit').value = data.download_limit || 0;
            document.getElementById('setting-ul-limit').value = data.upload_limit   || 0;
            document.getElementById('setting-save-path').value = data.save_path    || '';
        })
        .catch(err => console.error('loadSettings:', err));
}

function saveSettings() {
    const dlLimit = parseInt(document.getElementById('setting-dl-limit').value) || 0;
    const ulLimit = parseInt(document.getElementById('setting-ul-limit').value) || 0;

    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ download_limit: dlLimit, upload_limit: ulLimit })
    })
    .then(() => showToast('Settings saved', 'success'))
    .catch(() => showToast('Error saving settings', 'danger'));
}

// ------------------------------------------------------------------
// Tab navigation
// ------------------------------------------------------------------
function showTab(name) {
    currentTab = name;

    document.querySelectorAll('.tab-page').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${name}`).classList.add('active');

    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.tab === name);
    });

    const titles = { dashboard:'Dashboard', torrents:'Torrents', youtube:'YouTube Downloads', add:'Add Download', settings:'Settings' };
    document.getElementById('topbar-title').textContent = titles[name] || name;

    // Hide torrent actions on non-torrent pages
    const torrentActions = document.getElementById('torrent-actions-container');
    if (torrentActions) {
        torrentActions.style.display = ['dashboard','torrents'].includes(name) ? '' : 'none';
    }

    if (name === 'settings') loadSettings();
}

function switchAddTab(name) {
    currentAddTab = name;
    document.getElementById('add-form-torrent').style.display = name === 'torrent' ? '' : 'none';
    document.getElementById('add-form-youtube').style.display = name === 'youtube' ? '' : 'none';
    document.getElementById('add-tab-torrent').classList.toggle('active', name === 'torrent');
    document.getElementById('add-tab-youtube').classList.toggle('active', name === 'youtube');
}

// ------------------------------------------------------------------
// Modal helpers
// ------------------------------------------------------------------
function openModal(id) {
    document.getElementById(id).classList.add('open');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('open');
}

// Close on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('open');
    }
});

// ------------------------------------------------------------------
// Toast notifications
// ------------------------------------------------------------------
function showToast(message, type = 'info') {
    const icons = { success: 'bi-check-circle-fill', danger: 'bi-x-circle-fill', warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };
    const iconColors = { success: 'var(--green)', danger: 'var(--red)', warning: 'var(--yellow)', info: 'var(--accent)' };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="bi ${icons[type] || icons.info} toast-icon" style="color:${iconColors[type]||iconColors.info}"></i>
        <span class="toast-msg">${message}</span>
        <button class="toast-close" onclick="this.closest('.toast').remove()"><i class="bi bi-x"></i></button>`;

    document.getElementById('toast-stack').appendChild(toast);

    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 250);
    }, 4000);
}

// ------------------------------------------------------------------
// Formatting helpers
// ------------------------------------------------------------------
function formatSize(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
    return `${bytes.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatSpeed(bps) {
    return formatSize(bps) + '/s';
}

function esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;')
        .replace(/"/g,'&quot;')
        .replace(/'/g,'&#39;');
}

function stateColor(state, bg = false) {
    const colors = {
        downloading: 'var(--accent)',
        seeding:     'var(--green)',
        finished:    'var(--green)',
        paused:      'var(--yellow)',
        error:       'var(--red)',
        checking:    'var(--accent)',
        queued:      'var(--text-muted)',
        processing:  'var(--purple)',
    };
    const bgMap = {
        downloading: 'var(--accent-dim)',
        seeding:     'var(--green-dim)',
        finished:    'var(--green-dim)',
        paused:      'var(--yellow-dim)',
        error:       'var(--red-dim)',
        checking:    'var(--accent-dim)',
        queued:      'var(--bg-hover)',
        processing:  'var(--purple-dim)',
    };
    return bg ? (bgMap[state] || 'var(--bg-hover)') : (colors[state] || 'var(--text-muted)');
}

function torrentIcon(state) {
    return {
        downloading: 'bi-arrow-down-circle-fill',
        seeding:     'bi-arrow-up-circle-fill',
        finished:    'bi-check-circle-fill',
        paused:      'bi-pause-circle-fill',
        error:       'bi-x-circle-fill',
        checking:    'bi-arrow-clockwise',
        queued:      'bi-hourglass-split',
    }[state] || 'bi-magnet-fill';
}

function setLoading(btn, loading, resetHTML) {
    btn.disabled = loading;
    if (loading) {
        btn.dataset.original = btn.innerHTML;
        btn.innerHTML = '<span class="spinner"></span> ' + resetHTML;
    } else {
        btn.innerHTML = resetHTML;
    }
}

// ------------------------------------------------------------------
// Drag-and-drop for .torrent files
// ------------------------------------------------------------------
function setupDropZone() {
    const zone = document.getElementById('drop-zone');
    if (!zone) return;

    zone.addEventListener('click', () => document.getElementById('torrent-file-input').click());

    ['dragenter','dragover','dragleave','drop'].forEach(ev => {
        zone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); });
    });

    zone.addEventListener('dragenter', () => zone.classList.add('drag-over'));
    zone.addEventListener('dragover',  () => zone.classList.add('drag-over'));
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));

    zone.addEventListener('drop', (e) => {
        zone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.torrent')) {
            showToast('Please drop a .torrent file', 'warning');
            return;
        }
        // Simulate file input
        const dt = new DataTransfer();
        dt.items.add(file);
        const input = document.getElementById('torrent-file-input');
        input.files = dt.files;
        handleFileSelect({ target: { files: dt.files, value: '' } });
    });
}

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    // Populate qualities
    updateYTQualities();

    // Restore saved YouTube mode preference from localStorage
    const savedMode = localStorage.getItem('yt-download-mode');
    if (savedMode) {
        const radio = document.querySelector(`input[name="yt-mode"][value="${savedMode}"]`);
        if (radio) radio.checked = true;
    }

    // Save mode preference when changed
    document.querySelectorAll('input[name="yt-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            localStorage.setItem('yt-download-mode', e.target.value);
        });
    });

    // Sidebar nav
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => showTab(item.dataset.tab));
    });

    // Drop zone
    setupDropZone();

    // Pause / Resume all
    document.getElementById('pause-all-btn').addEventListener('click', () => {
        fetch('/api/pause-all', { method: 'POST' }).then(() => fetchTorrents());
    });

    document.getElementById('resume-all-btn').addEventListener('click', () => {
        fetch('/api/resume-all', { method: 'POST' }).then(() => fetchTorrents());
    });

    // Delete confirm
    document.getElementById('delete-confirm-btn').addEventListener('click', deleteTorrent);

    // Initial data load
    fetchAll();

    // Load settings to update save path placeholders
    fetch('/api/settings')
        .then(r => r.json())
        .then(data => {
            const path = data.save_path || '';
            const torrentPath = document.getElementById('torrent-save-path');
            const ytPath = document.getElementById('yt-save-path');
            if (torrentPath) torrentPath.placeholder = path;
            if (ytPath) ytPath.placeholder = path;
        })
        .catch(() => {});

    // Periodic fallback refresh every 10s (in case WS events are missed)
    setInterval(fetchAll, 10000);
});