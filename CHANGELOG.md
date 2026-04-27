# Changelog

All notable changes to Eyeris are documented here.

---

## [1.2.0] — 2026-04-27

### Added
- **Image zoom (desktop):** mouse-wheel to zoom up to 8×, click-drag to pan when zoomed, double-click to toggle 2.5× zoom, Escape to reset. Zoom level shown in an overlay.
- **Mobile full-screen viewer:** image detail page opens as a full-screen overlay on phones. Pinch-to-zoom, double-tap to reset zoom, horizontal swipe left/right to navigate between images.
- **Mobile swipe-up bottom sheet:** swipe up from the bottom of the image to reveal all metadata, tags, categories, download, and delete controls. Draggable between peek and fully-open states with snap behaviour.
- **Scroll-to-top button:** floating ↑ button appears in the bottom-right corner on any page after scrolling 300 px. Smooth-scrolls back to the top.

---

## [1.1.16] — 2026-04-26

### Added
- **EXIF shooting data:** aperture, shutter speed, ISO, focal length, and lens model extracted on ingest and stored in the database. Displayed in the image detail panel as a photo-style exposure line (e.g. `f/2.8 · 1/125s · ISO 400 · 35mm`).
- Startup migration adds the five new columns automatically — no manual DB changes needed.

---

## [1.1.15] — 2026-04-25

### Added
- **Ollama → llama.cpp proxy** (`ollama-proxy.py`): FastAPI service on port 11434 that translates the Ollama wire protocol to the OpenAI-compatible llama.cpp API, allowing A-EYE to use a remote llama.cpp server (e.g. Strix Halo with Qwen 35B) instead of a local Ollama instance.

### Fixed
- Scan starting in paused state when the previous run was paused — `_paused` flag is now reset in `start_background_scanner()`.

---

## [1.1.14] — 2026-04-24

### Added
- **XMP re-sync endpoint** (`POST /api/scan/xmp-resync`): re-reads XMP sidecar files for all images without re-running GPU models. Useful after A-EYE processes a batch.
- **Untagged image count** shown on the Dashboard.
- Duplicate detection now handles the A-EYE rename pattern: when both the original and the AI-renamed file exist on the NAS, the XMP sidecar from the renamed copy is loaded into the original's record.

### Fixed
- NAS recycle-bin and trash directories (`.Trash-1000`, `$RECYCLE.BIN`, `RECYCLER`, `.Trashes`, etc.) are now excluded from scans.
- Scan progress label and stale count display cleaned up.

---

## [1.1.13] and earlier

Internal development — no public changelog kept.
