#!/usr/bin/env bash
# Starts the whole Alpha stack (macOS / Linux). Usage: bash run_alpha.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "=================================================="
echo "  Alpha Investigation System - starting..."
echo "=================================================="

if ! command -v docker >/dev/null 2>&1; then
    echo "[x] Docker is not installed: https://docs.docker.com/get-docker/"
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "[x] Docker is installed but not running. Start it and try again."
    exit 1
fi

if [ ! -f .env ]; then
    cp .env.example .env
    echo "[i] Created .env from .env.example"
fi

if ! grep -Eq '^(LLM_API_KEY|LLM_1_KEY)=.+' .env; then
    echo
    echo "[!] No model key in .env (LLM_API_KEY or LLM_1_KEY) - the app will start, but case analysis will fail."
    echo "    Open .env, set LLM_API_KEY, then run this script again."
    echo
fi

# A shared secret so only the app can call the analysis workflow.
if ! grep -Eq '^ALPHA_WEBHOOK_TOKEN=.+' .env; then
    TOKEN=$(od -An -tx1 -N24 /dev/urandom | tr -d ' \n')
    printf '\nALPHA_WEBHOOK_TOKEN=%s\n' "$TOKEN" >> .env
    echo "[i] Added ALPHA_WEBHOOK_TOKEN to .env"
fi

WEB_PORT=$(grep -E '^WEB_PORT=' .env | cut -d= -f2- | tr -d '\r')
WEB_PORT=${WEB_PORT:-8601}

echo "[1/2] Building and starting services (first run can take a few minutes)..."
if ! docker compose up -d --build --wait --remove-orphans; then
    echo
    echo "[x] Some services failed to start. Last log lines:"
    docker compose logs --tail 40
    exit 1
fi

URL="http://localhost:${WEB_PORT}"
echo "[2/2] Opening ${URL}"
if command -v open >/dev/null 2>&1; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
fi

echo "=================================================="
echo "  Alpha is running:  ${URL}"
echo "  To stop it:        docker compose down"
echo "=================================================="
