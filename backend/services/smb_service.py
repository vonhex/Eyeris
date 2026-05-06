import os
import shutil
from io import BytesIO
from pathlib import Path

from config import settings

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".heic",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"
}

def _local_path(share: str, relative_path: str = "") -> str:
    """Build a local filesystem path from share + relative path.
    Since we scan MOUNT_BASE directly now, share + relative_path is simply joined
    onto MOUNT_BASE.
    """
    base = settings.MOUNT_BASE
    if share and relative_path:
        return os.path.join(base, share, relative_path)
    if share:
        return os.path.join(base, share)
    if relative_path:
        return os.path.join(base, relative_path)
    return base


def list_images(share: str = "", subdir: str = "") -> list[dict]:
    """List all image files in a directory using the local mount point."""
    mount_path = _local_path(share, subdir)
    if not os.path.isdir(mount_path):
        print(f"[NAS] Mount not found: {mount_path}")
        return []

    # Directories to skip during listing
    SKIP_DIRS = {
        "@Recycle", "#recycle",           # QNAP / Synology recycle bins
        "@Recently-Snapshot",             # QNAP snapshots
        ".@__thumb", "@eaDir", "eaDir",   # QNAP metadata / thumbnails
        ".Trash-1000", ".Trash-0",        # Linux trash
        "$RECYCLE.BIN", "RECYCLER",       # Windows recycle bin
        "__MACOSX", ".Trashes",           # macOS
        ".thumbnails", "Thumbnails",      # generic thumbnail caches
    }

    results = []
    for dirpath, dirnames, filenames in os.walk(mount_path):
        # Prune skipped directories so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        
        for name in filenames:
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            # The share/rel_path logic is preserved for DB compatibility
            # rel_path = path relative to MOUNT_BASE
            rel_to_base = os.path.relpath(full, settings.MOUNT_BASE).replace("\\", "/")
            
            # Split into share (first component) and relative_path (the rest)
            parts = rel_to_base.split("/", 1)
            img_share = parts[0]
            img_rel = parts[1] if len(parts) > 1 else ""

            try:
                size = os.path.getsize(full)
            except Exception:
                size = 0
            results.append({
                "share": img_share,
                "relative_path": img_rel,
                "filename": name,
                "file_size": size,
            })
    return results


def read_file_bytes(share: str, relative_path: str) -> bytes:
    """Read the full contents of a file from the mount."""
    path = _local_path(share, relative_path)
    with open(path, "rb") as f:
        return f.read()


def read_file_stream(share: str, relative_path: str) -> BytesIO:
    """Read a file into a BytesIO stream."""
    return BytesIO(read_file_bytes(share, relative_path))


def delete_file(share: str, relative_path: str):
    """Delete a file from the mount."""
    path = _local_path(share, relative_path)
    os.remove(path)


def move_file(src_share: str, src_path: str, dst_share: str, dst_path: str):
    """Move a file between shares (or within a share) on the mount."""
    src = _local_path(src_share, src_path)
    dst = _local_path(dst_share, dst_path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
