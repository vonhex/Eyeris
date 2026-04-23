# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Start both backend and frontend together
./start.sh

# Backend only (from repo root)
source venv/bin/activate
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend only (dev server)
cd frontend
npm run dev
```

- Frontend dev: http://localhost:5173
- Backend API: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs
- In production, the backend serves the built frontend from `frontend/dist/` as a SPA

## Frontend Build & Lint

```bash
cd frontend
npm run build    # build to dist/
npm run lint     # ESLint
npm run preview  # preview production build
```

## Configuration

All config comes from `.env` at the repo root (loaded by `backend/config.py`). Key settings:

| Variable | Purpose |
|---|---|
| `SMB_HOST`, `SMB_USERNAME`, `SMB_PASSWORD`, `SMB_SHARES` | NAS access via SMB |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | MariaDB connection |
| `LLAMA_CPP_URL` | llama.cpp server (Gemma 4 vision model) for AI analysis |
| `SCAN_CONCURRENCY` | Parallel AI analysis workers (default: 2) |
| `SCAN_INTERVAL_MINUTES` | Background scan frequency (default: 60) |
| `ES_HOST`, `ES_ENABLED` | Elasticsearch (currently disabled — no-ops unless `ES_ENABLED=true`) |
| `NSFW_FOLDERS` | SMB shares whose images get auto-tagged `nsfw` |
| `THUMBNAIL_DIR` | Local thumbnail storage (`backend/thumbnails/`) |

Settings can also be updated at runtime via `PUT /api/settings` (persisted back to `.env`).

## Architecture

### Two-Phase Scan Pipeline

The core of the app is a two-phase scanner (`backend/services/scanner_service.py`) that runs as a persistent `asyncio` background task:

- **Phase 1** (discovery): Lists all SMB shares in parallel, downloads new images, deduplicates by SHA-256 hash (keeping the higher-quality copy), generates 300×300 thumbnails, and immediately runs the fast GPU models (NudeNet + YOLOv8-face + SigLIP + FaceNet) on each image. Phases 1 and 2 run **concurrently** — Phase 2 starts consuming unanalyzed images as soon as Phase 1 produces them.
- **Phase 2** (AI analysis): Picks up unanalyzed images and sends them to the llama.cpp Gemma 4 vision server for rich descriptions, tags, categories, albums, sentiment, and face metadata. Concurrency is capped by `asyncio.Semaphore(SCAN_CONCURRENCY)`.

NSFW images detected by either phase are automatically moved on the NAS into a `_detected_nsfw/` subfolder within the first `NSFW_FOLDERS` share.

### Dual AI Architecture

There are two separate AI layers with different responsibilities:

1. **Fast GPU models** (`backend/services/gpu_models.py`) — run on `cuda:0` (RTX 3060) during Phase 1:
   - **NudeNet** (ONNX): NSFW detection; fires at ≥80% confidence
   - **YOLOv8n-face** (`yolov8n-face.pt`): Face bounding-box detection
   - **FaceNet** (`facenet-pytorch` InceptionResnetV1/vggface2): 512-d face embeddings for clustering
   - **SigLIP** (`google/siglip-base-patch16-224`): Zero-shot tag classification against ~300 candidate tags; tags saved at ≥80% confidence

2. **Gemma 4 vision** (`backend/services/ai_service.py`) — runs via llama.cpp's OpenAI-compatible API during Phase 2; returns structured JSON with description, tags, category, album, sentiment score, and face descriptions.

### Face Clustering

Faces accumulate 512-d FaceNet embeddings stored as JSON in `faces.embedding`. Clustering (`POST /api/faces/cluster`) uses a union-find algorithm with cosine similarity threshold (default 0.65) to group faces into clusters. Each cluster can be assigned a person name via `PUT /api/faces/cluster/{cluster_id}/name`. Face crop thumbnails are stored at `backend/thumbnails/faces/{face_id}.jpg` and served at `GET /api/faces/{face_id}/crop`.

### Backend (FastAPI + SQLAlchemy)

**`backend/main.py`** — App entry point. Registers routers, runs inline DB migrations for new `faces` columns on startup, and serves the built React frontend as a SPA fallback.

**`backend/models.py`** — ORM models: `Image`, `Tag`, `Category`, `ImageTag`, `ImageCategory`, `Face`, `ScanJob`. `Face` has `face_bbox` (JSON `[x1,y1,x2,y2]`), `embedding` (JSON float array), `crop_path`, and `cluster_id`.

**`backend/routers/`** — One router per resource: `images`, `tags`, `categories`, `albums`, `faces`, `scan`, `stats`, `settings`.

**`backend/services/`**:
- `scanner_service.py` — Two-phase scan pipeline (see above).
- `gpu_models.py` — All local GPU model loading and inference (lazy-loaded singletons).
- `ai_service.py` — Gemma 4 vision via llama.cpp OpenAI-compatible API.
- `smb_service.py` — SMB/NAS: listing paths, reading/moving/deleting files.
- `image_service.py` — EXIF orientation correction, thumbnail generation, base64 encoding, hash computation.
- `search_service.py` — Elasticsearch integration (all no-ops unless `ES_ENABLED=true`).

### Frontend (React + Vite + Tailwind)

Single-page app. All API calls go through `src/api.js` using axios with `baseURL: "/api"`.

**Pages**: Gallery, ImageDetail, Albums (list + detail), People, Tags, Sentiments, Folders, Dashboard, Settings.

**Components**: `FilterSidebar`, `ImageCard`, `ImageGrid`, `ScanProgress`, `SearchBar`, `TagEditor`, `HardwareStats`, `NsfwSection`.

Thumbnails are served at `/api/images/{id}/thumbnail`; full images at `/api/images/{id}/file` — both proxy from the NAS via SMB.
