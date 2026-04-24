"""
Real-time file watcher for NAS shares.

Uses watchfiles (inotify on Linux) to monitor the CIFS-mounted NAS paths
at /mnt/nas/{share}/ and immediately process new image files as they appear,
rather than waiting for the next periodic scan interval.

New file flow:
  1. inotify fires on file creation
  2. 3-second debounce (NAS writes can be multi-step)
  3. _discover_image: download → hash → dedup → thumbnail → metadata & XMP tags
"""

import asyncio
import os
from pathlib import Path

from config import settings

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".heic",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"
}
SKIP_DIRS = {"@Recycle", "@Recently-Snapshot", ".@__thumb", "#recycle", ".Trash-1000", "__MACOSX"}

# Filled at startup from config; avoids circular import at module level
_watch_paths: list[str] = []
_watcher_task: asyncio.Task | None = None


def init_watch_paths(shares: list[str]) -> list[str]:
    """Build the list of local mount paths that exist and can be watched."""
    paths = []
    base = settings.MOUNT_BASE
    
    if not shares or (len(shares) == 1 and not shares[0].strip()):
        # If no specific shares, watch the root mount point
        if os.path.isdir(base):
            paths.append(base)
    else:
        for share in shares:
            share = share.strip()
            if not share:
                continue
            p = os.path.join(base, share)
            if os.path.isdir(p):
                paths.append(p)
            else:
                print(f"[Watcher] Share not mounted at {p} — skipping")
    return paths


async def start_watcher():
    """Entry point: start the inotify watcher for all mounted NAS shares."""
    global _watcher_task
    if _watcher_task and not _watcher_task.done():
        return  # already running

    paths = init_watch_paths(settings.SMB_SHARES)
    if not paths:
        print("[Watcher] No mounted NAS shares found — file watching disabled")
        return

    _watcher_task = asyncio.create_task(_watch_loop(paths))
    print(f"[Watcher] Watching {len(paths)} path(s): {[os.path.basename(p) if os.path.basename(p) else p for p in paths]}")


async def _watch_loop(watch_paths: list[str]):
    """Main loop: monitor paths and batch-process new files with debounce."""
    try:
        import watchfiles
    except ImportError:
        print("[Watcher] watchfiles not installed — pip install watchfiles")
        return

    pending: dict[str, float] = {}  # path → time first seen
    DEBOUNCE_SECS = 3.0

    async def _drain():
        """Every second, flush files that have been pending for > DEBOUNCE_SECS."""
        while True:
            await asyncio.sleep(1)
            now = asyncio.get_event_loop().time()
            ready = [p for p, t in list(pending.items()) if now - t >= DEBOUNCE_SECS]
            for p in ready:
                del pending[p]
                asyncio.create_task(_handle_new_file(p))

    asyncio.create_task(_drain())

    try:
        async for changes in watchfiles.awatch(*watch_paths, poll_delay_ms=500):
            for change_type, path in changes:
                if change_type != watchfiles.Change.added:
                    continue
                p = Path(path)
                if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                if p.name.startswith(".") or p.name.startswith("._"):
                    continue
                if any(skip in p.parts for skip in SKIP_DIRS):
                    continue
                # Record first-seen time; reset timer if already pending
                pending[path] = asyncio.get_event_loop().time()
    except Exception as e:
        print(f"[Watcher] Watch loop error: {e}")


async def _handle_new_file(full_path: str):
    """Parse the path and hand off to the scanner."""
    try:
        p = Path(full_path)
        if not p.exists():
            return  # file already gone (temp file)

        mount_base = Path(settings.MOUNT_BASE)
        rel_to_mount = p.relative_to(mount_base)
        parts = rel_to_mount.parts
        
        shares = [s.strip() for s in settings.SMB_SHARES if s.strip()]
        
        if not shares:
            # Root mount point is being watched
            share = ""
            relative = str(rel_to_mount)
        else:
            if len(parts) < 2:
                return
            share = parts[0]
            relative = str(Path(*parts[1:]))

        file_size = p.stat().st_size

        print(f"[Watcher] New file: {share}/{relative} ({file_size // 1024} KB)")
        from services.scanner_service import discover_new_file
        await discover_new_file(share, relative, file_size)
    except Exception as e:
        print(f"[Watcher] Error handling {full_path}: {e}")
