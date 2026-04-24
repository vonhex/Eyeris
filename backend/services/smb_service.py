import os
import shutil
from io import BytesIO

from config import settings

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".heic",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"
}

def _local_path(share: str, relative_path: str = "") -> str:
    """Build a local filesystem path from share + relative path."""
    base = settings.MOUNT_BASE
    if relative_path:
        return os.path.join(base, share, relative_path)
    return os.path.join(base, share)


def list_images(share: str, subdir: str = "") -> list[dict]:
    """List all image files in a share using the local CIFS mount."""
    mount_path = _local_path(share)
    if not os.path.isdir(mount_path):
        print(f"[NAS] Mount not found: {mount_path}")
        return []

    print(f"[NAS] Listing {share}...")
    # Directories to skip during listing
    SKIP_DIRS = {"@Recycle", "@Recently-Snapshot", ".@__thumb", "#recycle", ".Trash-1000", "__MACOSX", ".thumbnails", "Thumbnails"}

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
            rel_path = os.path.relpath(full, mount_path).replace("\\", "/")
            try:
                size = os.path.getsize(full)
            except Exception:
                size = 0
            results.append({
                "share": share,
                "relative_path": rel_path,
                "filename": name,
                "file_size": size,
            })
    return results


def read_file_bytes(share: str, relative_path: str) -> bytes:
    """Read the full contents of a file from the NAS."""
    path = _local_path(share, relative_path)
    with open(path, "rb") as f:
        return f.read()


def read_file_stream(share: str, relative_path: str) -> BytesIO:
    """Read a file into a BytesIO stream."""
    return BytesIO(read_file_bytes(share, relative_path))


def delete_file(share: str, relative_path: str):
    """Delete a file from the NAS."""
    path = _local_path(share, relative_path)
    os.remove(path)


def move_file(src_share: str, src_path: str, dst_share: str, dst_path: str):
    """Move a file between shares (or within a share) on the NAS."""
    src = _local_path(src_share, src_path)
    dst = _local_path(dst_share, dst_path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
