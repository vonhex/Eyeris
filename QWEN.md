# Eyeris — Project Context

## Overview

Eyeris is a **full-stack, self-hosted photo management platform** designed for large personal/home-lab photo libraries stored on NAS/SMB shares. It discovers images via SMB/CIFS, extracts EXIF/GPS metadata, generates thumbnails, detects faces (YOLOv8 + FaceNet), and ingests AI-generated descriptions/tags/XMP sidecars from [A-EYE](https://github.com/SpaceinvaderOne/a-eye).

**Key capabilities:** face grouping/clustering, duplicate detection (SHA-256 + perceptual hash), semantic keyword search, real-time file watching, web image search via SearXNG proxy, hardware monitoring, and tag/category management.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI, SQLAlchemy (MySQL/MariaDB via pymysql), Uvicorn |
| **Frontend** | React 19, Vite 8, Tailwind CSS 4, React Router 7, Axios |
| **Database** | MariaDB / MySQL |
| **Face detection** | YOLOv8n-face + FaceNet (facenet-pytorch) |
| **AI tagging** | A-EYE (external; writes XMP sidecars to NAS) |
| **Search** | Weighted SQL keyword search; Elasticsearch optional |
| **Storage** | SMB/CIFS shares mounted on the host |

---

## Directory Structure

```
images-app/
├── backend/                     # FastAPI backend
│   ├── main.py                  # App entry, lifespan (DB migrations, scanner/watcher startup), SPA serving
│   ├── config.py                # Settings class (dotenv-backed)
│   ├── models.py                # SQLAlchemy ORM models (Image, Tag, Category, Face, ScanJob, etc.)
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── database.py              # DB session factory, Base
│   ├── routers/                 # API route modules
│   │   ├── images.py            # Image CRUD, search, bulk ops, favorites
│   │   ├── tags.py              # Tag listing with counts
│   │   ├── categories.py        # Category listing with counts
│   │   ├── albums.py            # Metadata + virtual tag-based albums
│   │   ├── faces.py             # Face/people management, clustering, merging
│   │   ├── scan.py              # Scan control (start/stop/pause/resume/reset)
│   │   ├── stats.py             # Dashboard stats, hardware, locations, cameras
│   │   ├── settings.py          # Read/update .env via API
│   │   ├── searxng.py           # Web image/video search proxy + NAS download
│   │   └── aeye.py              # A-EYE integration
│   ├── services/                # Business logic
│   │   ├── scanner_service.py   # Async scan pipeline (discovery, hashing, EXIF, faces, XMP ingestion)
│   │   ├── gpu_models.py        # YOLOv8-face + FaceNet inference
│   │   ├── image_service.py     # EXIF extraction, orientation correction, thumbnails, hashing
│   │   ├── smb_service.py       # SMB/CIFS file I/O
│   │   ├── llm_search.py        # Weighted keyword search logic
│   │   ├── search_service.py    # Elasticsearch integration (optional)
│   │   └── watcher_service.py   # Real-time NAS file watcher (watchfiles)
│   └── thumbnails/              # Generated thumbnails (git-ignored)
├── frontend/                    # React + Vite SPA
│   ├── src/
│   │   ├── api.js               # Axios instance, all API calls (baseURL: /api)
│   │   ├── App.jsx              # React Router routes → page components
│   │   └── pages/               # Page components (Gallery, ImageDetail, Albums, People, etc.)
│   └── public/                  # Static assets (logo, icons)
├── venv/                        # Python virtual environment
├── start.sh                     # Dev launcher (starts both backend + frontend in parallel)
├── restart-backend.sh           # Quick backend restart helper
├── mount-nas.sh                 # NAS share mounter (adds fstab entries)
└── .env.example                 # Configuration template
```

---

## Key Architectural Details

### Startup Lifespan (`main.py`)
- Creates DB tables if not exists via `Base.metadata.create_all()`
- Runs inline SQL migrations on startup (ALTER TABLE for new columns/indexes on `images` and `faces` tables) — no external migration tool needed
- Attempts to ensure Elasticsearch index exists (gracefully handles ES being unavailable)
- Starts background scanner service (`start_background_scanner()`)
- Starts real-time file watcher (`start_watcher()`)

### Scan Pipeline (`scanner_service.py`)
Runs as a persistent `asyncio` background task:
1. Lists SMB shares in parallel
2. Downloads new images, computes SHA-256 hash
3. Deduplicates (keeps higher-quality copy by file size + EXIF completeness)
4. Extracts EXIF, GPS, camera model; applies orientation correction
5. Generates 300×300 JPEG thumbnail
6. Runs face detection (YOLOv8) + FaceNet embedding extraction
7. Checks for `.xmp` sidecar — if present, ingests description, tags, album into DB

### Configuration (`config.py`)
- Loaded from `.env` via `python-dotenv`
- Key settings: NAS credentials, DB connection, scan concurrency/intervals, scheduled scan windows, optional Elasticsearch config, SearXNG URL, A-EYE credentials
- Settings are **editable at runtime** via `PUT /api/settings` (persisted back to `.env`)

### Face Clustering (`faces.py` + `gpu_models.py`)
- Faces accumulate 512-d FaceNet embeddings in DB
- `POST /api/faces/cluster` runs union-find with cosine similarity (threshold ~0.65)
- Clusters can be named and merged via the UI

### SPA Serving
- In production, FastAPI serves the built React frontend from `backend/../frontend/dist/`
- All non-API routes fall back to `index.html` for client-side routing
- CORS middleware allows `localhost:5173` during development

---

## Running the Project

### Prerequisites
- Python 3.10+ with virtual environment
- Node.js 18+ and npm
- MariaDB / MySQL
- SMB/CIFS NAS storage (mounted via `mount-nas.sh`)
- A-EYE (external, optional)
- SearXNG (external, optional for web search)

### Setup
```bash
# 1. Clone & configure
git clone <repo> && cd Eyeris
cp .env.example .env    # edit with your NAS/DB credentials

# 2. Mount NAS shares
sudo bash mount-nas.sh

# 3. Backend setup
cd backend
python -m venv ../venv
source ../venv/bin/activate
pip install -r requirements.txt

# 4. Frontend setup
cd frontend
npm install
npm run build           # production build → dist/
```

### Development Mode
```bash
./start.sh              # Starts both backend (uvicorn) + frontend (vite dev) in parallel
```

Or individually:
```bash
# Backend (with auto-reload)
source venv/bin/activate
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend dev server (HMR)
cd frontend
npm run dev
```

### Production
```bash
source venv/bin/activate
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

| URL | Purpose |
|---|---|
| `http://localhost:5173` | Frontend dev server (development) |
| `http://localhost:8000` | Backend API + SPA frontend (production) |
| `http://localhost:8000/docs` | Swagger OpenAPI docs |

---

## Database Models (Summary)

- **Image** — Core model: file_path, SHA-256 hash, EXIF/GPS metadata, AI description, album, perceptual_hash, face_count, favorite flag, quality_flags JSON
- **Tag / Category** — Many-to-many with Image via junction tables; Categories support parent hierarchy
- **Face** — Links to Image: person_name, cluster_id, FaceNet embedding (512-d float array), bbox, crop_path, ignored flag
- **ScanJob** — Tracks scan status, phases, timestamps, errors

Database migrations are inline SQL ALTER TABLE statements in `main.py` lifespan.

---

## Frontend Pages

Gallery, Image Detail, Albums, People, Tags, Folders, Duplicates, Image Search, Scan History, Dashboard, Settings

Key shared components: `FilterSidebar`, `ImageGrid`, `ImageCard`, `TagEditor`, `ScanProgress`, `HardwareStats`

All API calls flow through `frontend/src/api.js` (Axios with `baseURL: "/api"`).

---

## Development Conventions

- **Backend:** FastAPI routers split by domain. Services layer handles business logic. Settings class wraps all env vars with defaults.
- **Frontend:** React functional components, React Router for navigation, Tailwind CSS for styling. No TypeScript (plain JS/JSX).
- **Database:** SQLAlchemy ORM with MySQL dialect. No Alembic — migrations are inline in lifespan startup.
- **Error handling:** Graceful degradation (e.g., ES unavailable doesn't crash the app; face detection failures logged but don't stop scanning).
