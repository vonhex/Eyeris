<p align="center">
  <img src="eyeris-logo.png" alt="Eyeris" width="250" />
</p>

<p align="center">
  <a href="https://github.com/vonhex/Eyeris/releases/latest"><img src="https://img.shields.io/github/v/release/vonhex/Eyeris?style=flat-square" alt="Latest Release"></a>
  <a href="https://github.com/vonhex/Eyeris/pkgs/container/eyeris"><img src="https://img.shields.io/badge/Docker-ghcr.io-blue?style=flat-square&logo=docker" alt="Docker"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
</p>

> Self-hosted photo manager with AI tag ingestion. Your Pictures. Fast. Easy. Simple.

> [!WARNING]
> **Eyeris is designed for use on a trusted local network only.** It has no brute-force protection on the login endpoint, no multi-user access control, and image URLs embed session tokens that appear in server logs. Do not expose it directly to the internet. If you need remote access, use a VPN or put it behind Cloudflare Access — not a plain public tunnel.

Eyeris is a full-stack, self-hosted image management platform for large personal or home-lab photo libraries stored on NAS/SMB storage. It handles discovery, deduplication, metadata extraction, GPS reverse geocoding, face grouping, and browsing. AI analysis (descriptions, tags, categories, albums, sentiment) is provided by **A-EYE**, a separate tool you run yourself that writes XMP sidecar files back to the NAS. Eyeris picks those up automatically during each scan.

---

## Deployment

Three options depending on your setup. Pick one.

---

### Option 1 — Docker (recommended)

No Python or Node.js required. One command.

```bash
docker run -d \
  --name eyeris \
  -p 8000:8000 \
  -v /path/to/thumbnails:/data/thumbnails \
  -v /path/to/db:/data/db \
  -e SMB_HOST=192.168.1.x \
  -e SMB_USERNAME=youruser \
  -e SMB_PASSWORD=yourpass \
  -e SMB_SHARES=photos,media \
  ghcr.io/vonhex/eyeris:latest
```

Open `http://YOUR-IP:8000`. On first load the app auto-creates a login — the default password is shown on screen. Change it in **Settings → Change Password**.

> **GPU acceleration:** The container uses CPU PyTorch by default. For GPU inference (face detection), add `--gpus all` and ensure `nvidia-container-toolkit` is installed on the host.

**Docker Compose:**

```yaml
services:
  eyeris:
    image: ghcr.io/vonhex/eyeris:latest
    ports:
      - "8000:8000"
    volumes:
      - ./thumbnails:/data/thumbnails
      - ./db:/data/db
    environment:
      SMB_HOST: 192.168.1.x
      SMB_USERNAME: youruser
      SMB_PASSWORD: yourpass
      SMB_SHARES: photos,media
    restart: unless-stopped
```

---

### Option 2 — Install script (Linux)

Downloads the latest release and sets everything up. Works on Ubuntu, Debian, Fedora, and most Linux distros.

```bash
# Download latest release
curl -fsSL https://github.com/vonhex/Eyeris/releases/latest/download/eyeris-latest.tar.gz | tar -xz
cd eyeris-*

# Install (creates venv, installs deps, sets up .env)
./install.sh

# Edit your NAS settings
nano .env

# Start
./start.sh
```

**Optional: install as a systemd service** (runs on boot, auto-restarts):

```bash
sudo ./install.sh --service
# Manage with: systemctl {start|stop|restart|status} eyeris
# Logs:        journalctl -u eyeris -f
```

**Options:**

| Flag | Description | Default |
|---|---|---|
| `--service` | Install and enable systemd service | off |
| `--port PORT` | Port to listen on | `8000` |
| `--dir DIR` | Installation directory | current directory |

---

### Option 3 — Manual install (from source)

```bash
git clone https://github.com/vonhex/Eyeris.git
cd Eyeris
```

**Backend:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

**Frontend:**

```bash
cd frontend
npm install
npm run build      # builds to frontend/dist/ — served by the backend
cd ..
```

**Configure:**

```bash
cp .env.example .env
nano .env          # set SMB_HOST, SMB_USERNAME, SMB_PASSWORD, SMB_SHARES
```

**Run:**

```bash
# Both backend + frontend dev server
./start.sh

# Production only (backend serves the built frontend)
source venv/bin/activate
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Creating a Release

Releases are automated via GitHub Actions. Push a version tag and the workflow will:
1. Build the React frontend
2. Package source + pre-built frontend into `.tar.gz` and `.zip` archives
3. Build and push the Docker image to `ghcr.io/vonhex/eyeris` with version tags
4. Create a GitHub Release with the archives and SHA-256 checksums attached

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## How A-EYE fits in

[A-EYE](https://github.com/SpaceinvaderOne/a-eye) is set up independently by the user (outside of Eyeris). It processes images on the NAS and writes `.xmp` sidecar files alongside them containing AI-generated descriptions, tags, and album names. During each scan, Eyeris reads those sidecars and ingests their content into the database — no configuration needed on the Eyeris side beyond having the NAS shares configured.

```
NAS share
├── photo.jpg          ← discovered and indexed by Eyeris
└── photo.jpg.xmp      ← written by A-EYE, ingested by Eyeris on next scan
```

---

## Features

- **Automatic NAS scanning** — Recursively discovers images across SMB/CIFS shares
- **A-EYE tag ingestion** — Reads XMP sidecars written by A-EYE (descriptions, tags, albums)
- **Face detection & grouping** — Detects faces with YOLOv8, extracts FaceNet embeddings, clusters into people
- **Duplicate detection** — SHA-256 deduplication + perceptual hash visual similarity grouping
- **EXIF & GPS metadata** — Date taken, camera model, GPS coordinates with reverse geocoding
- **Semantic search** — Weighted keyword search across filenames, AI descriptions, and tags
- **Real-time file watching** — Detects new images on the NAS immediately
- **Hardware monitoring** — Live CPU, GPU (NVIDIA, AMD, Intel), and RAM stats
- **Web search** — Search images and videos via SearXNG with direct-to-NAS download
- **Untagged view** — Dedicated tab showing images not yet processed by A-EYE
- **Password-protected** — JWT auth with auto-generated default password on first run

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# NAS (SMB/CIFS)
SMB_HOST=192.168.1.x
SMB_USERNAME=your_nas_user
SMB_PASSWORD=your_nas_password
SMB_SHARES=photos,media         # comma-separated share names

# Database — SQLite by default
# Leave DB_HOST empty for built-in SQLite. Set to a MariaDB host for multi-container setups.
DB_HOST=                        # e.g. 10.0.1.106 or leave empty
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_db_password
DB_NAME=image_catalog

# Scanner
SCAN_CONCURRENCY=2              # parallel scan workers
SCAN_INTERVAL_MINUTES=60        # auto-scan frequency

# Scheduled scanning (optional)
SCAN_SCHEDULE_ENABLED=false
SCAN_SCHEDULE_START=22:00       # 24-hour format
SCAN_SCHEDULE_END=06:00

# SearXNG web search (optional)
SEARXNG_URL=http://localhost:8887

# Authentication — auto-generated on first run, do not edit manually
# EYERIS_SECRET_KEY=
# EYERIS_PASSWORD_HASH=

# Thumbnails (internal path)
THUMBNAIL_DIR=backend/thumbnails
```

All settings can also be updated at runtime via **Settings** in the UI (persisted back to `.env`).

---

## Authentication

On first run, Eyeris auto-generates a login with the default password **`eyeris`**. Change it via **Settings → Change Password**. There is no multi-user support — one password controls all access.

Tokens are 30-day JWTs stored in the browser. Changing your password invalidates all existing tokens.

---

## Architecture

### Scan Pipeline

The scanner (`backend/services/scanner_service.py`) runs as a persistent `asyncio` background task.

**Per image:**
1. List all SMB shares in parallel
2. Download image, compute SHA-256 hash
3. Deduplicate (keep higher-quality copy by file size + EXIF completeness)
4. Extract EXIF, GPS, camera model; GPS reverse-geocoded to city/country
5. Generate 300×300 JPEG thumbnail
6. Run face detection (YOLOv8) + FaceNet embedding extraction
7. Check for `.xmp` sidecar — if present, load description, tags, and album into DB

### Face Grouping

Faces accumulate 512-d FaceNet embeddings stored in the database. `POST /api/faces/cluster` runs a union-find algorithm with cosine similarity (default threshold: 0.65) to group faces into person clusters. Each cluster can be named and merged via the People page.

### Backend

```
backend/
├── main.py                  # App entry, startup migrations, SPA fallback
├── config.py                # dotenv-backed Settings class (SQLite or MariaDB)
├── models.py                # SQLAlchemy ORM models
├── schemas.py               # Pydantic request/response schemas
├── database.py              # DB session factory
├── routers/
│   ├── auth.py              # Login, auto-setup, change password (JWT)
│   ├── images.py            # Image CRUD, search, bulk ops, favorites, untagged filter
│   ├── tags.py              # Tag listing with counts
│   ├── categories.py        # Category listing with counts
│   ├── albums.py            # Metadata + virtual tag-based albums
│   ├── faces.py             # Face/people management, clustering, merging
│   ├── scan.py              # Scan control (start, stop, pause, reset)
│   ├── stats.py             # Dashboard stats, hardware, locations, cameras
│   ├── settings.py          # Read/update .env via API
│   └── searxng.py           # Web image search proxy + NAS download
└── services/
    ├── scanner_service.py   # Scan pipeline and XMP ingestion
    ├── gpu_models.py        # YOLOv8-face + FaceNet inference (GPU/CPU)
    ├── image_service.py     # EXIF, GPS geocoding, orientation, thumbnails, hashing
    ├── smb_service.py       # SMB/CIFS file I/O
    ├── llm_search.py        # Weighted keyword search
    ├── search_service.py    # Index helpers
    └── watcher_service.py   # Real-time NAS file watcher
```

### Frontend

React + Vite + Tailwind SPA. All API calls go through `src/api.js` (Axios, `baseURL: "/api"`).

**Pages:** Gallery, Image Detail, People, Tags, Folders, Duplicates, Blurry, Image Search, Dashboard, Settings

---

## API Reference

All endpoints except `/auth/*` require `Authorization: Bearer <token>`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Login with password, returns JWT |
| `PUT` | `/auth/change-password` | Change password |
| `GET` | `/api/images` | List images (pagination, filters, sort, search, untagged) |
| `GET` | `/api/images/{id}` | Image detail with tags, faces, metadata |
| `GET` | `/api/images/{id}/thumbnail` | Thumbnail JPEG |
| `GET` | `/api/images/{id}/file` | Full-resolution image from NAS |
| `GET` | `/api/images/duplicates` | Perceptual hash similarity groups |
| `DELETE` | `/api/images/{id}` | Delete image and thumbnail |
| `POST` | `/api/images/bulk-delete` | Delete multiple images |
| `POST` | `/api/images/bulk-download` | ZIP download of selected images |
| `POST` | `/api/images/bulk-tags` | Add/remove tags from multiple images |
| `PUT` | `/api/images/{id}/tags` | Set exact tag list |
| `PUT` | `/api/images/{id}/favorite` | Toggle favorite |
| `GET` | `/api/faces/people` | Person clusters with face counts |
| `GET` | `/api/faces/{face_id}/crop` | Face crop thumbnail |
| `POST` | `/api/faces/cluster` | Re-cluster all face embeddings |
| `POST` | `/api/faces/cluster/merge` | Merge clusters into one |
| `PUT` | `/api/faces/cluster/{cluster_id}/name` | Assign person name |
| `GET` | `/api/scan/status` | Current job + schedule state |
| `POST` | `/api/scan/start` | Start/resume scan |
| `POST` | `/api/scan/stop` | Request stop |
| `POST` | `/api/scan/pause` | Pause scan |
| `POST` | `/api/scan/resume` | Resume scan |
| `POST` | `/api/scan/reset` | Truncate all data + delete thumbnails |
| `POST` | `/api/scan/phash` | Compute perceptual hashes |
| `GET` | `/api/tags` | All tags with image counts |
| `GET` | `/api/albums` | All albums (metadata + virtual) |
| `GET` | `/api/stats` | Dashboard stats |
| `GET` | `/api/stats/hardware` | Live CPU/GPU/RAM metrics |
| `GET` | `/api/stats/locations` | Location names with counts |
| `GET` | `/api/stats/cameras` | Camera models with counts |
| `GET/PUT` | `/api/settings` | Read/update .env config |
| `GET` | `/api/searxng/search` | Web image/video search via SearXNG |
| `POST` | `/api/searxng/download` | Download web image to NAS |

Full interactive docs: `http://localhost:8000/docs`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, Uvicorn |
| Database | SQLite (default) or MariaDB/MySQL |
| Frontend | React 19, Vite, Tailwind CSS, Axios |
| Face detection | YOLOv8n-face + FaceNet (facenet-pytorch) |
| GPS geocoding | reverse_geocode (offline, no API key) |
| AI tagging | [A-EYE](https://github.com/SpaceinvaderOne/a-eye) (external, via XMP sidecars) |
| Storage | SMB/CIFS via smbprotocol |
| Search | Weighted SQL keyword search; SearXNG for web image search |
| CI/CD | GitHub Actions — auto-builds Docker image + release archives on tag push |

---

## License

MIT
