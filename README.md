<p align="center">
  <img src="eyeris-logo.png" alt="Eyeris" width="250" />
</p>

<p align="center">
  <a href="https://github.com/vonhex/Eyeris/releases/latest"><img src="https://img.shields.io/github/v/release/vonhex/Eyeris?style=flat-square" alt="Latest Release"></a>
  <a href="https://github.com/vonhex/Eyeris/pkgs/container/eyeris"><img src="https://img.shields.io/badge/Docker-ghcr.io-blue?style=flat-square&logo=docker" alt="Docker"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Noncommercial-orange?style=flat-square" alt="License"></a>
</p>

<p align="center">Self-hosted AI photo manager. Your Pictures. Fast. Easy. Simple.</p>

> [!WARNING]
> **Eyeris is designed for use on a trusted local network only.** It has no brute-force protection on the login endpoint, no multi-user access control, and image URLs embed session tokens that appear in server logs. Do not expose it directly to the internet. If you need remote access, use a VPN or put it behind Cloudflare Access — not a plain public tunnel.

---

## How do I install it?

| Who it's for | Method | Guide |
|---|---|---|
| **Unraid users** | Manual install via template — see the wiki | [Unraid →](https://github.com/vonhex/Eyeris/wiki/Installation#path-1-unraid) |
| **Everyone else** (Linux / Windows / macOS with Docker) | Run `./docker-start.sh` — auto-detects your GPU | [Docker →](https://github.com/vonhex/Eyeris/wiki/Installation#path-2-docker) |
| **Developers** | Run `./start.sh` — Python + Node directly, no Docker | [Dev →](https://github.com/vonhex/Eyeris/wiki/Installation#path-3-developer--manual) |

> Not sure? **Use the Docker path.** It works on any OS and handles everything automatically.

---

## Quick Start (Docker)

```bash
# 1. Clone the repo
git clone https://github.com/vonhex/Eyeris.git
cd Eyeris

# 2. Run the start script — it will create .env and tell you what to fill in
chmod +x docker-start.sh
./docker-start.sh

# 3. Edit .env with your NAS credentials (SMB_HOST, SMB_USERNAME, etc.)
nano .env

# 4. Run again — auto-detects your GPU, pulls the image, starts the container
./docker-start.sh
```

Open **http://localhost:8000** — default username is `eyeris`, password is set on first run.

> **NVIDIA users:** Install [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on your host first. The script handles the rest.

---

## Features

### Gallery & Browsing
- Infinite-scroll gallery with thumbnails, favorites, and multi-select bulk actions
- Filter by tag, category, album, folder, camera, location, date range, GPS, or quality issue
- Sort by date taken, date added, filename, or random
- Video support (MP4, MKV, MOV, AVI, WebM and more) with thumbnail preview

### Image Viewer
- **Desktop:** mouse-wheel zoom (up to 8×), click-drag to pan, double-click to toggle zoom, keyboard ← → to navigate
- **Mobile:** full-screen view, pinch-to-zoom, horizontal swipe to navigate between images, swipe-up bottom sheet to reveal metadata and editing controls
- Scroll-to-top button appears site-wide when scrolling long pages

### AI Analysis
- **Gemma 4 vision** (via llama.cpp): rich descriptions, tags, categories, albums, and sentiment
- **SigLIP** zero-shot tag classification against ~300 candidates — runs locally on GPU during scan
- **NudeNet** NSFW detection with automatic NAS quarantine
- **YOLOv8 + FaceNet** face detection and 512-d embeddings for People clustering

### Metadata & EXIF
- Date taken, GPS location with OpenStreetMap link, reverse-geocoded city/country
- Camera make/model, lens model, aperture, shutter speed, ISO, focal length
- XMP sidecar support (reads tags and descriptions written by tools like A-EYE)

### Organisation
- Tag editor per image + bulk tag editor across selections
- Category and album assignment
- People page: face clusters with optional name labels
- Duplicate detection via perceptual hash

### System
- Two-phase async scan pipeline with live progress bar
- File-watcher for near-real-time new image detection
- Hardware stats dashboard (CPU, RAM, GPU temp/VRAM)
- Settings page with runtime `.env` editing

---

## Screenshots

### Gallery & Search
![Gallery](docs/screenshots/gallery.png)

### AI Tag Cloud
![Tags](docs/screenshots/tags.png)

### System Dashboard
![Dashboard](docs/screenshots/dashboard.png)

### Blurry Photo Detection
![Blurry](docs/screenshots/blurry.png)

---

## License

[PolyForm Noncommercial License 1.0.0](LICENSE) — free to use and modify, not for commercial use or resale. For commercial licensing contact lucashjantzen@gmail.com.
