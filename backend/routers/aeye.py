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

    added = 0
    for tag_name in tags_raw:
        name = tag_name.strip().lower()
        if not name:
            continue
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
            try:
                if img.is_video:
                    _send_thumbnail(client, img, base, db)
                else:
                    rel = _aeye_path(img.file_path)
                    resp = client.post(f"{base}/api/analyze-path", json={"path": rel})
                    resp.raise_for_status()
                sent += 1
            except Exception as exc:
                errors.append({"id": img.id, "error": str(exc)})

    db.commit()
    return {"sent": sent, "errors": errors}


def _run_analyze_untagged(image_ids: list[int], base: str) -> None:
    """Background worker: send untagged images/videos to A-Eye. Runs in a thread."""
    db = SessionLocal()
    try:
        images = db.query(Image).filter(Image.id.in_(image_ids)).all()
        sent = 0
        with _aeye_client() as client:
            for img in images:
                try:
                    if img.is_video:
                        _send_thumbnail(client, img, base, db)
                    else:
                        rel = _aeye_path(img.file_path)
                        resp = client.post(f"{base}/api/analyze-path", json={"path": rel})
                        resp.raise_for_status()
                    sent += 1
                except Exception as exc:
                    logger.warning("A-Eye: failed on image %s: %s", img.id, exc)
        db.commit()
        logger.info("A-Eye: sent %d / %d items", sent, len(images))
    except Exception as exc:
        logger.error("A-Eye background worker error: %s", exc)
    finally:
        db.close()


@router.post("/analyze-untagged")
def analyze_untagged(db: Session = Depends(get_db)):
    """Queue all untagged images and videos for A-Eye analysis and return immediately."""
    if not settings.AEYE_URL:
        raise HTTPException(400, "A-Eye URL is not configured — set it in Settings")

    images = db.query(Image).filter(~Image.tags.any()).all()

    if not images:
        return {"queued": 0, "message": "No untagged items found"}

    image_ids = [img.id for img in images]
    base = settings.AEYE_URL.rstrip("/")

    t = threading.Thread(target=_run_analyze_untagged, args=(image_ids, base), daemon=True)
    t.start()

    return {"queued": len(image_ids), "message": f"Sending {len(image_ids)} items to A-Eye in the background"}
