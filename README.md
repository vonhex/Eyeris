<p align="center">
  <img src="eyeris-logo.png" alt="Eyeris" width="250" />
</p>

> Self-hosted photo manager with AI tag ingestion. Your Pictures. Fast. Easy. Simple.

> [!WARNING]
> **Eyeris is designed for use on a trusted local network only.** It has no brute-force protection on the login endpoint, no multi-user access control, and image URLs embed session tokens that appear in server logs. Do not expose it directly to the internet. If you need remote access, use a VPN or put it behind Cloudflare Access — not a plain public tunnel.

Eyeris is a full-stack, self-hosted image management platform for large personal or home-lab photo libraries stored on NAS/SMB storage. It handles discovery, deduplication, metadata extraction, face grouping, and browsing. AI analysis (descriptions, tags, categories, albums, sentiment) is provided by **A-EYE**, a separate tool you run yourself that writes XMP sidecar files back to the NAS. Eyeris picks those up automatically during each scan. Built-in GPU models handle face detection and clustering independently of A-EYE.

---

## Quick Deploy — Docker / Unraid

```bash
# Simplest option — runs on any Linux machine with Docker
docker pull ghcr.io/vonhex/eyeris:latest

docker run -d \
  --name eyeris \
  -p 8000:8000 \
  -v /mnt/user/appdata/eyeris/thumbnails:/data/thumbnails \
  -v /mnt/user/appdata/eyeris/db:/data/db \
  -e SMB_HOST=192.168.1.x \
  -e SMB_USERNAME=youruser \
  -e SMB_PASSWORD=yourpass \
  -e SMB_SHARES=photos,media \
  ghcr.io/vonhex/eyeris:latest
```

Open `http://YOUR-IP:8000` — that's it. On first load the app auto-generates a login password and shows it on screen. All settings (SMB creds, scan schedule, SearXNG) can be updated at runtime via the Settings page.

> **GPU acceleration:** The container uses CPU PyTorch by default. For GPU inference (face detection), pass `--gpus all` and ensure `nvidia-container-toolkit` is installed on the host.

**Unraid Community App:** Import the template from this repo or search "eyeris" on Unraid. The container uses SQLite by default (no separate database needed). Add a MariaDB host for multi-container setups.

See [unraid/template.xml](unraid/template.xml) for full configuration options.

---

## How A-EYE fits in

[A-EYE](https://github.com/SpaceinvaderOne/a-eye) is set up independently by the user (outside of Eyeris). It processes images on the NAS and writes `.xmp` sidecar files alongside them containing AI-generated descriptions, tags, and album names. During each scan, Eyeris reads those sidecars and ingests their content into the database — no configuration needed on the Eyeris side beyond having the NAS shares mounted.

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
- **Hardware monitoring** — Live CPU, GPU (NVIDIA, AMD, Intel), and RAM stats — auto-detected, no hardcoded paths
- **Web search** — Search images and videos via SearXNG with direct-to-NAS download
- **Password-protected** — JWT auth with auto-generated default password on first run

---

## Architecture

### Scan Pipeline

The scanner (`backend/services/scanner_service.py`) runs as a persistent `asyncio` background task.

**Discovery (per image):**
1. List all SMB shares in parallel
2. Download new images, compute SHA-256 hash
3. Deduplicate (keep higher-quality copy by file size + EXIF completeness)
4. Extract EXIF, GPS, camera model; apply orientation correction
5. Generate 300×300 JPEG thumbnail
6. Run face detection (YOLOv8) + FaceNet embedding extraction
7. Check for `.xmp` sidecar — if present, load description, tags, and album into DB

### Face Grouping

Faces accumulate 512-d FaceNet embeddings stored in the database. `POST /api/faces/cluster` runs a union-find algorithm with cosine similarity (default threshold: 0.65) to group faces into person clusters. Each cluster can be named and merged via the People page in the UI.

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
│   ├── images.py            # Image CRUD, search, bulk ops, favorites
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
    ├── image_service.py     # EXIF, orientation, thumbnails, hashing
    ├── smb_service.py       # SMB/CIFS file I/O
    ├── llm_search.py        # Weighted keyword search
    ├── search_service.py    # Index helpers (no-op, search via SearXNG)
    └── watcher_service.py   # Real-time NAS file watcher
```

### Frontend

React + Vite + Tailwind SPA. All API calls go through `src/api.js` (Axios, `baseURL: "/api"`).

**Pages:** Gallery, Image Detail, People, Tags, Folders, Duplicates, Blurry, Image Search, Dashboard, Settings

---

## Installation — Native (non-Docker)

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- SMB/CIFS-accessible NAS storage
- **[A-EYE](https://github.com/SpaceinvaderOne/a-eye)** — optional, provides AI tags/descriptions via XMP sidecars
- **[SearXNG](https://github.com/searxng/searxng)** — optional, required for web image/video search
- NVIDIA GPU recommended for face detection (falls back to CPU)

### 1. Clone & configure

```bash
git clone https://github.com/vonhex/Eyeris.git
cd Eyeris
cp .env.example .env
# Edit .env with your values (see below)
```

### 2. Backend

```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
npm run build      # production build → frontend/dist/
```

### 4. Run

```bash
# Development (backend + frontend dev server)
./start.sh

# Production (backend serves built frontend)
source venv/bin/activate
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# NAS (SMB/CIFS)
SMB_HOST=192.168.1.x
SMB_USERNAME=your_nas_user
SMB_PASSWORD=your_nas_password
SMB_SHARES=photos,media         # comma-separated share names

# Database — SQLite by default (Docker/Unraid)
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

Settings can also be updated at runtime via `PUT /api/settings` (persisted back to `.env`).

---

## Authentication

On first run, Eyeris auto-generates a login with the default password **`eyeris`**. Change it immediately via **Settings → Change Password**. There is no multi-user support — one password controls all access.

Auth tokens are 30-day JWTs stored in the browser. If your token is compromised, change your password (this invalidates all existing tokens).

---

## API Reference

All API endpoints (except `/auth/*`) require a `Bearer` token in the `Authorization` header.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Login with password, returns JWT |
| `PUT` | `/auth/change-password` | Change password |
| `GET` | `/api/images` | List images (pagination, filters, sort, search) |
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

Full interactive docs at `http://localhost:8000/docs` (Swagger UI).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, Uvicorn |
| Database | SQLite (default) or MariaDB/MySQL |
| Frontend | React, Vite, Tailwind CSS, Axios |
| Face detection | YOLOv8n-face + FaceNet (facenet-pytorch) |
| AI tagging | [A-EYE](https://github.com/SpaceinvaderOne/a-eye) (external, via XMP sidecars) |
| Storage | SMB/CIFS |
| Search | Weighted SQL keyword search; SearXNG for web image search |

---

## License

MIT
