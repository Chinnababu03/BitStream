FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for yt-dlp audio/video merging (ffmpeg)
# libtorrent manylinux wheels are self-contained — no system Boost needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create downloads directory
RUN mkdir -p /app/downloads && mkdir -p /app/config

# Expose web port
EXPOSE 8080

# Expose libtorrent port range
EXPOSE 6881-6891/tcp
EXPOSE 6881-6891/udp

# Use main.py as the unified entry point
CMD ["python", "main.py"]
