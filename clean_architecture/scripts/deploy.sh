#!/usr/bin/env bash
#
# Deployment helper for the University Lab Scheduler.
#
# Usage:
#   ./scripts/deploy.sh docker        Build and run with Docker Compose
#   ./scripts/deploy.sh local         Run locally with Streamlit
#   ./scripts/deploy.sh stop          Stop the Docker Compose stack
#   ./scripts/deploy.sh logs          Tail container logs
#
# The script is intentionally conservative: it fails fast on errors and never
# overwrites an existing .env file.

set -euo pipefail

# Resolve the project root (parent of this script's directory).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

APP_PORT="${APP_PORT:-8501}"

log()  { printf '\n[deploy] %s\n' "$*"; }
fail() { printf '\n[deploy][error] %s\n' "$*" >&2; exit 1; }

ensure_env() {
    if [[ ! -f .env ]]; then
        log "No .env found. Creating one from .env.example."
        cp .env.example .env
        log "Edit .env to customize settings if needed."
    fi
}

compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        fail "Docker Compose is not installed."
    fi
}

deploy_docker() {
    command -v docker >/dev/null 2>&1 || fail "Docker is not installed."
    ensure_env
    local dc; dc="$(compose_cmd)"
    log "Building and starting the container..."
    ${dc} up -d --build
    log "Waiting for the health check to pass..."
    sleep 5
    ${dc} ps
    log "Application available at: http://localhost:${APP_PORT}"
}

deploy_local() {
    command -v python3 >/dev/null 2>&1 || fail "Python 3 is not installed."
    log "Installing runtime dependencies..."
    python3 -m pip install -r requirements.txt
    log "Starting Streamlit on port ${APP_PORT}..."
    exec streamlit run presentation/app.py \
        --server.port "${APP_PORT}" \
        --server.address 0.0.0.0
}

stop_docker() {
    local dc; dc="$(compose_cmd)"
    log "Stopping the stack..."
    ${dc} down
}

show_logs() {
    local dc; dc="$(compose_cmd)"
    ${dc} logs -f --tail=100
}

case "${1:-}" in
    docker) deploy_docker ;;
    local)  deploy_local ;;
    stop)   stop_docker ;;
    logs)   show_logs ;;
    *)
        echo "Usage: $0 {docker|local|stop|logs}"
        exit 1
        ;;
esac
