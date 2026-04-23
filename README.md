# Eyeris

> Self-hosted AI photo manager with A-EYE Docker integration — scans NAS shares, detects faces, auto-tags content, and organizes your collection with local vision models.

Eyeris is a full-stack, self-hosted image management platform built for large personal or home-lab photo libraries stored on NAS/SMB storage. It runs entirely on-premises using local AI models — no cloud dependency.

---

## Features

- **Automatic NAS scanning** — Recursively discovers images across SMB/CIFS shares
- **Two-phase AI pipeline** — Fast GPU models in Phase 1, rich Gemma 4 vision analysis in Phase 2
- **Face detection & clustering** — YOLOv8 face detection + FaceNet embeddings grouped by person
- **NSFW detection** — NudeNet-powered detection with automatic NAS folder quarantine
- **Smart tagging** — SigLIP zero-shot classification against ~300 candidate tags
- **AI descriptions** — Gemma 4 vision generates natural-language descriptions, categories, albums, and sentiment
- **Semantic search** — LLM query expansion for natural language photo discovery
- **Duplicate detection** — SHA-256 deduplication + perceptual hash visual similarity grouping
- **EXIF & GPS metadata** — Date taken, camera model, GPS coordinates with reverse geocoding
- **XMP sidecar support** — Loads tags and descriptions from `.xmp` sidecars
- **Real-time file watching** — Detects new images on the NAS immediately
- **Hardware monitoring** — Live CPU, GPU (NVIDIA + AMD), and RAM stats
- **A-EYE Docker integration** — Drop-in Docker setup for the AI inference layer

---

## Architecture

### Two-Phase Scan Pipeline

The scanner (`backend/services/scanner_service.py`) runs as a persistent `asyncio` background task. Both phases run **concurrently** — Phase 2 starts consuming images as soon as Phase 1 produces them.

**Phase 1 — Discovery:**
- Lists all SMB shares in parallel
- Downloads new images, computes SHA-256 hash
- Deduplicates (keeps higher-quality copy by file size + EXIF completeness)
- Generates 300×300 JPEG thumbnails
- Runs fast GPU models: NudeNet (NSFW), YOLOv8-face, FaceNet embeddings, SigLIP tags
- Loads XMP sidecar metadata

**Phase 2 — AI Analysis:**
- Sends images to Gemma 4 vision (via LM Studio or Ollama)
- Returns: description, tags, category, album, faces, sentiment score, NSFW flag
- Concurrency capped by `SCAN_CONCURRENCY` semaphore

### Dual AI Architecture

| Layer | Models | Runs On | Purpose |
|---|---|---|---|
| Fast GPU | NudeNet, YOLOv8n-face, FaceNet, SigLIP | RTX/AMD GPU (Phase 1) | NSFW detection, face bounding boxes, embeddings, zero-shot tags |
| Vision LLM | Gemma 4 via llama.cpp / Ollama | LM Studio server (Phase 2) | Descriptions, rich tags, categories, albums, sentiment |

### Face Clustering

Faces accumulate 512-d FaceNet embeddings stored in the database. `POST /api/faces/cluster` runs a union-find algorithm with cosine similarity (default threshold: 0.65) to group faces into person clusters. Each cluster can be named and merged via the UI.

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
    ├── scanner_service.py   # Two-phase scan pipeline
    ├── gpu_models.py        # YOLOv8-face, FaceNet, SigLIP inference
    ├── ai_service.py        # Gemma 4 vision (LM Studio / Ollama)
    ├── image_service.py     # EXIF, orientation, thumbnails, hashing
    ├── smb_service.py       # SMB/CIFS file I/O
    ├── llm_search.py        # LLM query expansion + weighted DB search
    ├── search_service.py    # Elasticsearch integration (optional)
    └── watcher_service.py   # Real-time NAS file watcher
```

### Frontend

React + Vite + Tailwind SPA. All API calls go through `src/api.js` (Axios, `baseURL: "/api"`).

**Pages:** Gallery, Image Detail, Albums, People, Tags, Folders, Duplicates, Image Search, Scan History, Dashboard, Settings

**Key components:** `FilterSidebar`, `ImageGrid`, `ImageCard`, `TagEditor`, `ScanProgress`, `HardwareStats`, `NsfwSection`

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
| `GET` | `/api/searxng/search` | Web image search proxy |
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
NSFW_FOLDERS=photos             # shares whose images are checked for NSFW auto-move

# MariaDB
DB_HOST=localhost
DB_PORT=3306
DB_USER=eyeris
DB_PASSWORD=your_db_password
DB_NAME=eyeris

# AI — LM Studio (default)
LLAMA_CPP_URL=http://localhost:1234
LMSTUDIO_MODEL=gemma-4

# AI — Ollama (alternative, takes precedence if set)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:12b

# Scanner
SCAN_CONCURRENCY=2              # parallel Phase 2 AI workers
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
- MariaDB or MySQL
- SMB/CIFS-accessible NAS storage
- LM Studio with Gemma 4 **or** Ollama with a compatible vision model
- NVIDIA or AMD GPU recommended (falls back to CPU)

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

### 6. A-EYE Docker Integration

Eyeris supports the A-EYE Docker stack for running the AI inference layer (LM Studio / llama.cpp) as a containerized service. See the `A-EYE/` directory for the Docker Compose setup and configuration.

---

## Development

```bash
# Backend hot-reload
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

> **Note:** The `--reload` flag on uvicorn does not work reliably in this environment. For backend changes in production, use `restart-backend.sh`.

### Database Migrations

No migration tool needed. `main.py` runs inline SQL `ALTER TABLE` statements on startup to add any missing columns to existing tables.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, Uvicorn |
| Database | MariaDB / MySQL |
| Frontend | React, Vite, Tailwind CSS, Axios |
| AI (Phase 1) | NudeNet, YOLOv8n-face, FaceNet (facenet-pytorch), SigLIP |
| AI (Phase 2) | Gemma 4 via LM Studio (llama.cpp) or Ollama |
| Storage | SMB/CIFS (QNAP NAS or compatible) |
| Search | LLM query expansion + SQL weighted search; Elasticsearch optional |
| Containerization | Docker (A-EYE integration) |

---

## License

MIT
