<p align="center">
  <img src="eyeris-logo-icon.png" alt="Eyeris" width="500" />
</p>

> Self-hosted photo manager with A-EYE integration — scans NAS shares, ingests AI-generated tags and descriptions, groups faces, and organizes your collection.

Eyeris is a full-stack, self-hosted image management platform for large personal or home-lab photo libraries stored on NAS/SMB storage. It handles discovery, deduplication, metadata extraction, face grouping, and browsing. AI analysis (descriptions, tags, categories, sentiment) is provided by **A-EYE**, a separate tool you run yourself that writes XMP sidecar files back to the NAS. Eyeris picks those up automatically during each scan.

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
├── config.py                # dotenv-backed Settings class
├── models.py                # SQLAlchemy ORM models
├── schemas.py               # Pydantic request/response schemas
├── database.py              # DB session factory
├── routers/
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
    ├── gpu_models.py        # YOLOv8-face + FaceNet inference
    ├── image_service.py     # EXIF, orientation, thumbnails, hashing
    ├── smb_service.py       # SMB/CIFS file I/O
    ├── llm_search.py        # Weighted keyword search
    ├── search_service.py    # Elasticsearch integration (optional)
    └── watcher_service.py   # Real-time NAS file watcher
```

### Frontend

React + Vite + Tailwind SPA. All API calls go through `src/api.js` (Axios, `baseURL: "/api"`).

**Pages:** Gallery, Image Detail, Albums, People, Tags, Folders, Duplicates, Image Search, Scan History, Dashboard, Settings

**Key components:** `FilterSidebar`, `ImageGrid`, `ImageCard`, `TagEditor`, `ScanProgress`, `HardwareStats`

---

## Database Models

| Model | Key Fields |
|---|---|
| `Image` | `file_path`, `file_hash` (SHA-256), `perceptual_hash`, `width/height`, `thumbnail_path`, `analyzed`, `ai_description`, `album`, `face_count`, `favorite`, `date_taken`, `gps_lat/lon`, `camera_model`, `location_name`, `quality_flags` (JSON) |
| `Tag` | `name` (unique); many-to-many with Image via `ImageTag` |
| `Category` | `name`, `parent_id` (self-referential); many-to-many via `ImageCategory` |
| `Face` | `image_id`, `person_name`, `cluster_id`, `face_bbox` (JSON), `embedding` (JSON 512-d), `crop_path`, `ignored` |
| `ScanJob` | `status`, `source_folder`, `phase1_total/done`, `phase2_total/done`, `started_at`, `completed_at` |

---

## API Reference

### Images
| Method | Path | Description |
|---|---|---|
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

### Faces & People
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/faces/people` | Person clusters with face counts |
| `GET` | `/api/faces/{face_id}/crop` | Face crop thumbnail |
| `POST` | `/api/faces/cluster` | Re-cluster all face embeddings |
| `POST` | `/api/faces/cluster/merge` | Merge clusters into one |
| `PUT` | `/api/faces/cluster/{cluster_id}/name` | Assign person name |

### Scan Control
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/scan/status` | Current job + schedule state |
| `POST` | `/api/scan/start` | Start/resume scan |
| `POST` | `/api/scan/stop` | Request stop |
| `POST` | `/api/scan/pause` | Pause scan |
| `POST` | `/api/scan/resume` | Resume scan |
| `POST` | `/api/scan/reset` | Truncate all data + delete thumbnails |
| `POST` | `/api/scan/phash` | Compute perceptual hashes |

### Other
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/tags` | All tags with image counts |
| `GET` | `/api/albums` | All albums (metadata + virtual) |
| `GET` | `/api/stats` | Dashboard stats |
| `GET` | `/api/stats/hardware` | Live CPU/GPU/RAM metrics |
| `GET` | `/api/stats/locations` | Location names with counts |
| `GET` | `/api/stats/cameras` | Camera models with counts |
| `GET/PUT` | `/api/settings` | Read/update .env config |
| `GET` | `/api/searxng/search` | Web image/video search via SearXNG (`?category=images\|videos`) |
| `POST` | `/api/searxng/download` | Download web image to NAS |

Full interactive docs at `http://localhost:8000/docs` (Swagger UI).

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# NAS (SMB/CIFS)
SMB_HOST=192.168.1.x
SMB_USERNAME=your_nas_user
SMB_PASSWORD=your_nas_password
SMB_SHARES=photos,media         # comma-separated share names

# MariaDB
DB_HOST=localhost
DB_PORT=3306
DB_USER=eyeris
DB_PASSWORD=your_db_password
DB_NAME=eyeris

# Scanner
SCAN_CONCURRENCY=2              # parallel scan workers
SCAN_INTERVAL_MINUTES=60        # auto-scan frequency

# Scheduled scanning (optional)
SCAN_SCHEDULE_ENABLED=false
SCAN_SCHEDULE_START=22:00       # 24-hour format
SCAN_SCHEDULE_END=06:00

# Thumbnails
THUMBNAIL_DIR=backend/thumbnails

# Elasticsearch (optional, disabled by default)
ES_ENABLED=false
ES_HOST=http://localhost:9200
ES_INDEX=eyeris
```

Settings can also be updated at runtime via `PUT /api/settings` (persisted back to `.env`).

---

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- **[MariaDB](https://github.com/mariadb)** (or MySQL)
- SMB/CIFS-accessible NAS storage
- **[A-EYE](https://github.com/SpaceinvaderOne/a-eye)** — set up separately by the user; provides AI tags/descriptions via XMP sidecars
- **[SearXNG](https://github.com/searxng/searxng)** — set up separately; required for web image/video search (`GET /api/searxng/search`)

### 1. Clone & configure

```bash
git clone https://github.com/vonhex/Eyeris.git
cd Eyeris
cp .env.example .env
# Edit .env with your values
```

### 2. Mount NAS shares

```bash
sudo bash mount-nas.sh
# Mounts shares to /mnt/nas/<share_name>/
# Adds persistent entries to /etc/fstab
```

### 3. Backend

```bash
cd backend
python -m venv ../venv
source ../venv/bin/activate
pip install -r requirements.txt
```

### 4. Frontend

```bash
cd frontend
npm install
npm run build      # production build → frontend/dist/
```

### 5. Run

```bash
# Development (backend + frontend dev server)
./start.sh

# Production (backend serves built frontend)
source venv/bin/activate
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

| URL | Purpose |
|---|---|
| `http://localhost:5173` | Frontend dev server |
| `http://localhost:8000` | Backend API (also serves built frontend in production) |
| `http://localhost:8000/docs` | Swagger API docs |

---

## Development

```bash
# Backend
source venv/bin/activate
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend dev server (HMR)
cd frontend
npm run dev

# Lint frontend
cd frontend
npm run lint
```

### Database Migrations

No migration tool needed. `main.py` runs inline SQL `ALTER TABLE` statements on startup to add any missing columns to existing tables.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, Uvicorn |
| Database | [MariaDB](https://github.com/mariadb) / MySQL |
| Frontend | React, Vite, Tailwind CSS, Axios |
| Face detection | YOLOv8n-face + FaceNet (facenet-pytorch) |
| AI tagging | [A-EYE](https://github.com/SpaceinvaderOne/a-eye) (external, via XMP sidecars) |
| Storage | SMB/CIFS (QNAP NAS or compatible) |
| Search | Weighted SQL keyword search; Elasticsearch optional |

---

## License

MIT
