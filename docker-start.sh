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

# Pass --build to force a local image build (dev use)
EXTRA_ARGS=()
for arg in "$@"; do
    EXTRA_ARGS+=("$arg")
done

# ── Launch ────────────────────────────────────────────────────────────────────
echo "  Starting Eyeris..."
docker compose -f docker-compose.yml up -d "${EXTRA_ARGS[@]}"

echo ""
echo "  Eyeris is running → http://localhost:8000"
echo "  Logs : docker compose logs -f"
echo "  Stop : docker compose down"
echo ""
