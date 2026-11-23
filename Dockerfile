FROM python:3.12-slim

RUN apt-get update     && apt-get install -y --no-install-recommends ffmpeg     && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# /data holds config, queue/watcher state, logs and the Widevine keys (searched in the cwd).
# World-writable so the container can run as any uid (see PUID/PGID in docker-compose.yml).
RUN mkdir -p /data /downloads && chmod 777 /data /downloads
ENV CRUNCHYROLLER_HOST=0.0.0.0     CRUNCHYROLLER_DATA_DIR=/data     XDG_STATE_HOME=/data     HOME=/data     PYTHONUNBUFFERED=1
USER 1000:1000
WORKDIR /data
VOLUME ["/data", "/downloads"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s     CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"

# --browser: web server + watcher, without a pywebview window.
CMD ["python", "/app/main.py", "--gui", "--browser", "--port", "8000"]
