#!/usr/bin/env bash
# Eyeris install script
# Works from a downloaded release archive or a git clone.
# Usage: ./install.sh [--service] [--port PORT] [--dir DIR]
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
die()  { echo -e "${RED}✗${NC} $*" >&2; exit 1; }
hr()   { echo -e "${BOLD}────────────────────────────────────────${NC}"; }

# ── Defaults ─────────────────────────────────────────────────────────
INSTALL_SERVICE=false
PORT=8000
EYERIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Argument parsing ─────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --service)   INSTALL_SERVICE=true; shift ;;
    --port)      PORT="$2"; shift 2 ;;
    --dir)       EYERIS_DIR="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--service] [--port PORT] [--dir DIR]"
      echo "  --service   Install and enable a systemd service"
      echo "  --port      Port to listen on (default: 8000)"
      echo "  --dir       Installation directory (default: current dir)"
      exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

# ── Banner ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  Eyeris — AI Photo Manager${NC}"
echo -e "  Installing to: ${EYERIS_DIR}"
hr

# ── Prerequisites ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Checking prerequisites…${NC}"

# Python 3.10+
if ! command -v python3 &>/dev/null; then
  die "Python 3 not found. Install Python 3.10 or later."
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [[ $PY_MAJOR -lt 3 || ($PY_MAJOR -eq 3 && $PY_MINOR -lt 10) ]]; then
  die "Python $PY_VER found — need 3.10 or later."
fi
ok "Python $PY_VER"

# pip / venv
if ! python3 -m venv --help &>/dev/null; then
  die "python3-venv not found. Install it (e.g. sudo apt install python3-venv)"
fi
ok "python3-venv"

# Node.js — only needed if frontend/dist/ is missing
NEED_NODE=false
if [[ ! -d "$EYERIS_DIR/frontend/dist" ]]; then
  NEED_NODE=true
  if ! command -v node &>/dev/null; then
    die "frontend/dist not found and Node.js is not installed.\nEither download a release archive (includes pre-built frontend) or install Node.js 18+."
  fi
  NODE_VER=$(node --version | tr -d 'v' | cut -d. -f1)
  if [[ $NODE_VER -lt 18 ]]; then
    die "Node.js $(node --version) found — need 18 or later."
  fi
  ok "Node.js $(node --version)"
else
  ok "frontend/dist already present (skipping Node.js)"
fi

echo ""

# ── Python virtualenv + deps ──────────────────────────────────────────
hr
echo ""
echo -e "${BOLD}Setting up Python environment…${NC}"

cd "$EYERIS_DIR"

if [[ ! -d venv ]]; then
  python3 -m venv venv
  ok "Virtual environment created"
else
  ok "Virtual environment already exists"
fi

source venv/bin/activate

echo "Installing Python dependencies (this may take a few minutes)…"
pip install --upgrade pip --quiet
pip install -r backend/requirements.txt --quiet
ok "Python dependencies installed"

# ── Frontend build (only if dist missing) ────────────────────────────
if [[ "$NEED_NODE" == true ]]; then
  echo ""
  hr
  echo ""
  echo -e "${BOLD}Building frontend…${NC}"
  cd frontend
  npm ci --silent
  npm run build --silent
  cd "$EYERIS_DIR"
  ok "Frontend built"
fi

# ── .env setup ───────────────────────────────────────────────────────
echo ""
hr
echo ""
echo -e "${BOLD}Configuration…${NC}"

if [[ ! -f "$EYERIS_DIR/.env" ]]; then
  cp "$EYERIS_DIR/.env.example" "$EYERIS_DIR/.env"
  warn ".env created from .env.example — edit it with your NAS settings before starting."
else
  ok ".env already exists"
fi

# ── Systemd service (optional) ────────────────────────────────────────
if [[ "$INSTALL_SERVICE" == true ]]; then
  echo ""
  hr
  echo ""
  echo -e "${BOLD}Installing systemd service…${NC}"

  if [[ $EUID -ne 0 ]]; then
    die "--service requires root. Re-run with: sudo $0 --service"
  fi

  SERVICE_FILE="/etc/systemd/system/eyeris.service"
  VENV_UVICORN="$EYERIS_DIR/venv/bin/uvicorn"

  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Eyeris Photo Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=$EYERIS_DIR/backend
ExecStart=$VENV_UVICORN main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable eyeris
  systemctl restart eyeris
  ok "systemd service installed and started"
  echo ""
  echo -e "  Manage with: ${BOLD}systemctl {start|stop|restart|status} eyeris${NC}"
  echo -e "  Logs:        ${BOLD}journalctl -u eyeris -f${NC}"
fi

# ── Done ──────────────────────────────────────────────────────────────
echo ""
hr
echo ""
echo -e "${GREEN}${BOLD}Eyeris installed successfully!${NC}"
echo ""

if [[ "$INSTALL_SERVICE" == false ]]; then
  echo -e "  Start the app:   ${BOLD}./start.sh${NC}"
  echo -e "  Or manually:     ${BOLD}source venv/bin/activate && cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT${NC}"
fi

if [[ ! -f "$EYERIS_DIR/.env" ]] || grep -q "192.168.1.x" "$EYERIS_DIR/.env" 2>/dev/null; then
  echo ""
  warn "Edit ${BOLD}.env${NC} with your NAS IP, username, password, and share names before starting."
fi

echo ""
echo -e "  Open: ${BOLD}http://$(hostname -I | awk '{print $1}'):${PORT}${NC}"
echo ""
