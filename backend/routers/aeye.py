import logging
import os
import threading

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db, SessionLocal
from models import Image, Tag, ImageTag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aeye", tags=["aeye"])

_TIMEOUT = 300.0  # match A-Eye's internal generate timeout (vision inference can be slow)

# Module-level job state — updated by the background thread, polled by /status
_job: dict = {
    "running": False,
    "total": 0,
    "done": 0,
    "errors": 0,
    "current": "",   # filename of item currently being processed
}
_job_lock = threading.Lock()


def _aeye_client() -> httpx.Client:
    auth = (settings.AEYE_USER, settings.AEYE_PASS) if settings.AEYE_USER else None
    return httpx.Client(timeout=_TIMEOUT, auth=auth)


def _aeye_path(file_path: str) -> str:
    """Strip the SMB share prefix to get A-Eye's relative path.

    Eyeris: ShareName/folder/img.jpg  →  A-Eye: folder/img.jpg
    """
    parts = file_path.split("/", 1)
    return parts[1] if len(parts) == 2 else file_path


def _apply_aeye_result(db: Session, img: Image, result: dict) -> int:
    """Save description + tags from an A-Eye /analyze-image response to the DB.

    Returns the number of new tags applied.
    """
    description = (result.get("description") or "").strip()
    tags_raw = result.get("tags") or []

    if description and not img.ai_description:
        img.ai_description = description
        img.analyzed = True

    # Models repeat tags now and then ("night, city, night"). The session does not
    # autoflush, so a repeat would add the same image_tags row twice and fail the commit.
    names = list(dict.fromkeys(t.strip().lower() for t in tags_raw if t and t.strip()))

    added = 0
    for name in names:
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        already = db.query(ImageTag).filter(
            ImageTag.image_id == img.id, ImageTag.tag_id == tag.id
        ).first()
        if not already:
            db.add(ImageTag(image_id=img.id, tag_id=tag.id))
            added += 1

    return added


def _send_thumbnail(client: httpx.Client, img: Image, base: str, db: Session) -> bool:
    """POST the video thumbnail to A-Eye's /analyze-image and apply results. Returns True on success."""
    if not img.thumbnail_path:
        return False
    thumb_full = os.path.join(settings.THUMBNAIL_DIR, img.thumbnail_path)
    if not os.path.exists(thumb_full):
        return False
    with open(thumb_full, "rb") as f:
        thumb_bytes = f.read()
    resp = client.post(
        f"{base}/api/analyze-image",
        files={"file": (img.thumbnail_path, thumb_bytes, "image/jpeg")},
    )
    resp.raise_for_status()
    result = resp.json()
    added = _apply_aeye_result(db, img, result)
    logger.info("A-Eye thumbnail result for video %s: %d tags, description=%s",
                img.id, added, bool(result.get("description")))
    return True


@router.get("/status")
def aeye_status():
    """Return current A-Eye job progress."""
    with _job_lock:
        return dict(_job)


@router.post("/analyze")
def analyze_images(body: dict, db: Session = Depends(get_db)):
    """Send specific images (or video thumbnails) to A-Eye for AI analysis."""
    if not settings.AEYE_URL:
        raise HTTPException(400, "A-Eye URL is not configured — set it in Settings")

    image_ids = body.get("image_ids", [])
    if not image_ids:
        raise HTTPException(422, "image_ids required")

    images = db.query(Image).filter(Image.id.in_(image_ids)).all()
    base = settings.AEYE_URL.rstrip("/")

    sent, errors = 0, []
    with _aeye_client() as client:
        for img in images:
            img_id = img.id
            try:
                if img.is_video:
                    _send_thumbnail(client, img, base, db)
                else:
                    rel = _aeye_path(img.file_path)
                    resp = client.post(f"{base}/api/analyze-path", json={"path": rel})
                    resp.raise_for_status()
                db.commit()
                sent += 1
            except Exception as exc:
                db.rollback()
                logger.warning("A-Eye: failed to send image %s: %s", img_id, exc)
                reason = (f"A-Eye returned HTTP {exc.response.status_code}"
                          if isinstance(exc, httpx.HTTPStatusError) else "Could not reach A-Eye")
                errors.append({"id": img_id, "error": reason})

    db.commit()
    return {"sent": sent, "errors": errors}


def _run_analyze_untagged(image_ids: list[int], base: str) -> None:
    """Background worker: send untagged images/videos to A-Eye. Runs in a thread."""
    with _job_lock:
        _job.update({"running": True, "total": len(image_ids), "done": 0, "errors": 0, "current": ""})

    db = SessionLocal()
    try:
        with _aeye_client() as client:
            # Load each item fresh by id: one failed item rolls the session back, and
            # objects loaded before that would all need reloading anyway.
            for image_id in image_ids:
                try:
                    img = db.get(Image, image_id)
                    if img is None:  # deleted since the job was queued
                        continue
                    with _job_lock:
                        _job["current"] = img.filename or str(img.id)
                    # Always use /analyze-image (thumbnail bytes) so A-Eye returns tags
                    # synchronously. /analyze-path only enqueues in A-Eye's own pipeline
                    # and never sends results back to Eyeris.
                    _send_thumbnail(client, img, base, db)
                    # commit each item so results appear immediately
                    db.commit()
                    with _job_lock:
                        _job["done"] += 1
                except Exception as exc:
                    # Without the rollback the session stays failed and every later
                    # item raises too, which used to end the whole job silently.
                    db.rollback()
                    logger.warning("A-Eye: failed on image %s: %s", image_id, exc)
                    with _job_lock:
                        _job["errors"] += 1
        logger.info("A-Eye: completed %d / %d items", _job["done"], len(image_ids))
    except Exception:
        logger.exception("A-Eye background worker error")
    finally:
        db.close()
        with _job_lock:
            _job.update({"running": False, "current": ""})


@router.post("/analyze-untagged")
def analyze_untagged(db: Session = Depends(get_db)):
    """Queue all untagged images and videos for A-Eye analysis and return immediately."""
    if not settings.AEYE_URL:
        raise HTTPException(400, "A-Eye URL is not configured — set it in Settings")

    with _job_lock:
        if _job["running"]:
            return {
                "queued": 0,
                "message": "A-Eye job already running",
                "status": dict(_job),
            }

    images = db.query(Image).filter(~Image.tags.any()).all()

    if not images:
        return {"queued": 0, "message": "No untagged items found"}

    image_ids = [img.id for img in images]
    base = settings.AEYE_URL.rstrip("/")

    t = threading.Thread(target=_run_analyze_untagged, args=(image_ids, base), daemon=True)
    t.start()

    return {"queued": len(image_ids), "message": f"Sending {len(image_ids)} items to A-Eye in the background"}


