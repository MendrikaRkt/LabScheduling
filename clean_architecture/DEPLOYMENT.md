# Deployment Guide

This guide describes how to deploy the University Lab Scheduler in production.
Three options are covered, from easiest to most controlled:

1. [Streamlit Community Cloud](#1-streamlit-community-cloud-easiest) - easiest, zero infrastructure
2. [Docker / Docker Compose](#2-docker--docker-compose) - portable and reproducible
3. [Traditional server with systemd](#3-traditional-server-systemd) - full control

A [configuration reference](#configuration-reference) and a
[troubleshooting](#troubleshooting) section follow.

---

## Prerequisites

- Python 3.10 or later (for local and server deployments).
- Docker 24+ and the Docker Compose plugin (for the container option).
- A clone of this repository.

The application reads its scheduling parameters from `config/config.yaml` and
its logging configuration from `config/logging.yaml`. Runtime behaviour is
controlled by environment variables (see the reference below).

---

## 1. Streamlit Community Cloud (easiest)

Streamlit Community Cloud builds and hosts the app directly from GitHub.

1. Push the repository to GitHub (already done:
   `MendrikaRkt/university-lab-scheduler`).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **New app** and select:
   - Repository: `MendrikaRkt/university-lab-scheduler`
   - Branch: `main`
   - Main file path: `presentation/app.py`
4. (Optional) Open **Advanced settings -> Secrets** and paste the contents of
   `.streamlit/secrets.toml.example`, filling in real values.
5. Click **Deploy**.

The bundled `.streamlit/config.toml` is picked up automatically (headless mode,
XSRF protection, upload cap, hidden error details). The platform installs the
dependencies listed in `requirements.txt`.

To update the deployed app, push to the `main` branch; Streamlit Cloud rebuilds
automatically.

---

## 2. Docker / Docker Compose

The repository ships a multi-stage `Dockerfile` (small, non-root runtime image)
and a `docker-compose.yml`.

### Quick start

```bash
cp .env.example .env          # adjust values if needed
docker compose up -d --build
# open http://localhost:8501
```

Or use the helper script:

```bash
./scripts/deploy.sh docker    # build + run
./scripts/deploy.sh logs      # tail logs
./scripts/deploy.sh stop      # stop the stack
```

### What the container provides

- Runs as a non-root user (`appuser`).
- Exposes port `8501` (override the host port with `APP_PORT` in `.env`).
- Persists `logs/` and `outputs/` via bind mounts.
- Declares a `HEALTHCHECK` that probes Streamlit's `/_stcore/health` endpoint
  through `scripts/healthcheck.py`.

### Building the image manually

```bash
docker build -t university-lab-scheduler:latest .
docker run -p 8501:8501 -e LOG_LEVEL=INFO university-lab-scheduler:latest
```

---

## 3. Traditional server (systemd)

For a VM or bare-metal host where you want full control.

```bash
# 1. Create a dedicated user and directory
sudo useradd --system --create-home --home-dir /opt/lab-scheduler labscheduler
sudo chown -R labscheduler:labscheduler /opt/lab-scheduler

# 2. Deploy the code (git clone or rsync) into /opt/lab-scheduler
sudo -u labscheduler git clone \
  https://github.com/MendrikaRkt/university-lab-scheduler.git /opt/lab-scheduler

# 3. Create a virtual environment and install dependencies
cd /opt/lab-scheduler
sudo -u labscheduler python3 -m venv .venv
sudo -u labscheduler .venv/bin/pip install -r requirements.txt

# 4. Install and start the service
sudo cp deploy/lab-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lab-scheduler

# 5. Check status and logs
systemctl status lab-scheduler
journalctl -u lab-scheduler -f
```

### Reverse proxy (recommended)

Put the app behind Nginx or Caddy to terminate TLS and forward to port 8501.
Streamlit uses WebSockets, so the proxy must forward the `Upgrade` and
`Connection` headers. Minimal Nginx example:

```nginx
server {
    listen 443 ssl;
    server_name scheduler.example.com;

    # ssl_certificate / ssl_certificate_key ...

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

---

## Configuration reference

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `APP_PORT` | `8501` | Host port mapped to the container |
| `STREAMLIT_SERVER_PORT` | `8501` | Port Streamlit binds to |
| `STREAMLIT_SERVER_ADDRESS` | `0.0.0.0` | Bind address |
| `STREAMLIT_SERVER_HEADLESS` | `true` | Run without opening a browser |
| `STREAMLIT_BROWSER_GATHER_USAGE_STATS` | `false` | Disable telemetry |

Files:

- `config/config.yaml` - scheduling parameters (subjects, rooms, solver).
- `config/logging.yaml` - logging handlers, formatters and levels.
- `.streamlit/config.toml` - Streamlit server/theme settings.
- `.streamlit/secrets.toml` - secrets (never commit; use the `.example`).

---

## Health checks

- **Liveness**: Streamlit exposes `GET /_stcore/health` (returns HTTP 200 when
  the server is up). The Docker `HEALTHCHECK` and `scripts/healthcheck.py` use
  this endpoint.
- **Readiness / diagnostics**: the in-app **Health & status** page runs a deep
  check (dependencies importable, configuration loads, subject count) and shows
  a per-check table. The same logic is available programmatically:

  ```python
  from infrastructure.health import check_health
  print(check_health().to_dict())
  ```

---

## Logging

Logs are written to stdout (captured by Docker/systemd) and to rotating files
under `logs/` (`app.log` and `error.log`, 5 MB x 5 backups). Change verbosity
with `LOG_LEVEL` without editing any file.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Port 8501 already in use | Another process bound the port | Set `APP_PORT` to a free port, or stop the other process |
| Blank page / WebSocket errors behind proxy | Proxy not forwarding WebSocket headers | Add the `Upgrade`/`Connection` headers (see Nginx example) |
| Container marked `unhealthy` | App still starting or crashed | Check `docker compose logs`; increase `start_period` if startup is slow |
| `ModuleNotFoundError` | Dependencies not installed | Reinstall with `pip install -r requirements.txt` or rebuild the image |
| Config errors on startup | Invalid `config.yaml` | Open the **Health & status** page; it reports the configuration check detail |
| Uploads rejected | Wrong extension or file too large | Allowed: `.xlsx`, `.xls`, `.csv`; max 25 MB (see `maxUploadSize`) |
| Logs not persisted in Docker | Missing bind mount | Ensure `./logs:/app/logs` is present (it is in `docker-compose.yml`) |

For deeper diagnostics, set `LOG_LEVEL=DEBUG` and inspect `logs/app.log` and
`logs/error.log`.
