#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# ── .env check ────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo ""
        echo "  Created .env from .env.example."
        echo "  Please edit .env with your settings, then run this script again."
        echo ""
        exit 0
    else
        echo "  No .env file found. Copy .env.example to .env and fill in your settings."
        exit 1
    fi
fi

# ── GPU detection ─────────────────────────────────────────────────────────────
GPU="cpu"

if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null 2>&1; then
    GPU="nvidia"
elif [ -c /dev/kfd ]; then
    GPU="amd"
elif [ -d /dev/dri ] && lspci 2>/dev/null | grep -qiE 'intel.*(graphics|uhd|iris|arc)'; then
    GPU="intel"
fi

echo "  GPU mode : $GPU"

# ── Build compose command ──────────────────────────────────────────────────────
COMPOSE_FILES=(-f docker-compose.yml)
[ "$GPU" != "cpu" ] && COMPOSE_FILES+=(-f "docker-compose.${GPU}.yml")

# Pass --build to force a local image build (dev use)
EXTRA_ARGS=()
for arg in "$@"; do
    EXTRA_ARGS+=("$arg")
done

# ── Launch ────────────────────────────────────────────────────────────────────
echo "  Starting Eyeris..."
docker compose "${COMPOSE_FILES[@]}" up -d "${EXTRA_ARGS[@]}"

echo ""
echo "  Eyeris is running → http://localhost:8000"
echo "  Logs : docker compose logs -f"
echo "  Stop : docker compose down"
echo ""
