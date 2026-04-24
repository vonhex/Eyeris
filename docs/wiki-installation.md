# Installation Guide

Eyeris can be installed three ways. Pick the one that matches your setup and follow only that section — you don't need to read the others.

| I am... | Use this path |
|---|---|
| Running **Unraid** | [Path 1: Unraid](#path-1-unraid) |
| Running **Docker** on Linux, Windows, or macOS | [Path 2: Docker](#path-2-docker) |
| A **developer** who wants to run the source directly | [Path 3: Developer / Manual](#path-3-developer--manual) |

---

## Path 1: Unraid

**You do not need to download any files.** Eyeris installs directly from the Community Apps store.

### Prerequisites
- Unraid with the Community Apps plugin installed
- *(Optional)* NVIDIA GPU with the Unraid NVIDIA Driver plugin for hardware acceleration

### Steps

1. Open the **Apps** tab in Unraid
2. Search for **Eyeris**
3. Click **Install**
4. Configure the template:
   - Set **Thumbnail Path** → your appdata folder (e.g. `/mnt/user/appdata/eyeris/thumbnails`)
   - Set **Database Path** → your appdata folder (e.g. `/mnt/user/appdata/eyeris/db`)
   - Set **Photo Path** → your photo directory (e.g. `/mnt/user/Photos`)
   - Fill in your NAS credentials if your photos are on a separate SMB share
5. Click **Apply** and wait for the container to start
6. Open the WebUI at `http://YOUR-UNRAID-IP:8000`
7. Log in with username **`eyeris`** — you will be prompted to set a password on first run

---

## Path 2: Docker

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed
- **NVIDIA GPU users only:** Install [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on the host machine before starting
- **Intel / AMD GPU users:** No extra driver install needed — devices are passed through automatically

### Step 1 — Get the files

```bash
git clone https://github.com/vonhex/Eyeris.git
cd Eyeris
```

Or download and unzip the [latest release](https://github.com/vonhex/Eyeris/releases/latest) instead of cloning.

### Step 2 — Run the start script for the first time

```bash
chmod +x docker-start.sh
./docker-start.sh
```

The script will:
- Create a `.env` config file from the template
- Tell you to fill it in, then exit

### Step 3 — Edit your .env file

Open `.env` in any text editor and fill in your settings:

```bash
nano .env   # or use any editor you prefer
```

| Variable | Required? | Description |
|---|---|---|
| `SMB_HOST` | Optional | IP or hostname of your NAS (leave blank to use local files) |
| `SMB_USERNAME` | Optional | SMB username |
| `SMB_PASSWORD` | Optional | SMB password |
| `SMB_SHARES` | Optional | Comma-separated share names to scan, e.g. `photos,media` |
| `DB_HOST` | Optional | MariaDB host — **leave blank to use built-in SQLite** (recommended) |
| `DB_PORT` | Optional | MariaDB port (default: `3306`) |
| `DB_USER` | Optional | MariaDB username |
| `DB_PASSWORD` | Optional | MariaDB password |
| `DB_NAME` | Optional | MariaDB database name (default: `image_catalog`) |
| `SCAN_CONCURRENCY` | Optional | Parallel scan workers (default: `2`, raise for fast CPUs) |
| `SCAN_INTERVAL_MINUTES` | Optional | How often to rescan for new images (default: `60`) |
| `SCAN_SCHEDULE_ENABLED` | Optional | Restrict scanning to a time window (`true`/`false`) |
| `SCAN_SCHEDULE_START` | Optional | Window start time, e.g. `22:00` |
| `SCAN_SCHEDULE_END` | Optional | Window end time, e.g. `06:00` |
| `LLAMA_CPP_URL` | Optional | URL of a running llama.cpp server for AI image descriptions |
| `SEARXNG_URL` | Optional | URL of a SearXNG instance for web image search |
| `NSFW_FOLDERS` | Optional | Comma-separated shares where detected NSFW images are auto-moved |

> **Minimum config:** You only need `SMB_HOST`, `SMB_USERNAME`, `SMB_PASSWORD`, and `SMB_SHARES` if your photos are on a NAS. Everything else has safe defaults.

### Step 4 — Start Eyeris

```bash
./docker-start.sh
```

The script automatically detects your GPU and picks the right configuration:

| Detected | What runs |
|---|---|
| NVIDIA GPU (`nvidia-smi` found) | NVIDIA container with full CUDA acceleration |
| AMD GPU (`/dev/kfd` found) | AMD device passthrough (CPU inference for now) |
| Intel GPU (`/dev/dri` + Intel detected) | Intel device passthrough (CPU inference for now) |
| No GPU | CPU-only mode — everything works, AI is slower |

### Step 5 — Open the app

Go to **http://localhost:8000**

- **Username:** `eyeris`
- **Password:** Set on first login

---

### Updating

```bash
docker compose pull
./docker-start.sh
```

### Stopping

```bash
docker compose down
```

### Manual GPU override (if auto-detect fails)

If `docker-start.sh` doesn't detect your GPU correctly, run the compose command directly:

```bash
# NVIDIA
docker compose -f docker-compose.yml -f docker-compose.nvidia.yml up -d

# Intel iGPU or Arc
docker compose -f docker-compose.yml -f docker-compose.intel.yml up -d

# AMD
docker compose -f docker-compose.yml -f docker-compose.amd.yml up -d

# CPU only
docker compose up -d
```

---

## Path 3: Developer / Manual

This path runs the backend and frontend directly on your machine without Docker. **Only use this if you are developing or modifying the source code.** For normal use, follow Path 2.

### Prerequisites

- Python 3.12+
- Node.js 20+

### Steps

1. **Clone the repo**

   ```bash
   git clone https://github.com/vonhex/Eyeris.git
   cd Eyeris
   ```

2. **Set up the Python environment**

   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```

3. **Set up the frontend**

   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. **Configure**

   ```bash
   cp .env.example .env
   nano .env    # fill in your settings
   ```

5. **Start**

   ```bash
   chmod +x start.sh
   ./start.sh
   ```

   This starts the FastAPI backend on port `8000` and the Vite dev server on port `5173`. Both run together in one terminal — press `Ctrl+C` to stop both.

   | URL | What |
   |---|---|
   | http://localhost:5173 | Frontend (Vite dev server with hot reload) |
   | http://localhost:8000 | Backend API |
   | http://localhost:8000/docs | Swagger / API docs |
