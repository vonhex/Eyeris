import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Image

router = APIRouter(prefix="/api/aeye", tags=["aeye"])

_TIMEOUT = 10.0


def _aeye_client() -> httpx.Client:
    auth = (settings.AEYE_USER, settings.AEYE_PASS) if settings.AEYE_USER else None
    return httpx.Client(timeout=_TIMEOUT, auth=auth)


def _aeye_path(file_path: str) -> str:
    """Strip the SMB share prefix from an Eyeris file_path to get the A-Eye relative path.

    Eyeris stores paths as  ShareName/folder/img.jpg
    A-Eye stores paths as   folder/img.jpg  (relative to its /photos volume)
    Both volumes point at the same NAS directory.
    """
    parts = file_path.split("/", 1)
    return parts[1] if len(parts) == 2 else file_path


@router.post("/analyze")
def analyze_images(body: dict, db: Session = Depends(get_db)):
    """Send specific images to A-Eye for AI analysis."""
    if not settings.AEYE_URL:
        raise HTTPException(400, "A-Eye URL is not configured — set it in Settings")

    image_ids = body.get("image_ids", [])
    if not image_ids:
        raise HTTPException(422, "image_ids required")

    images = db.query(Image).filter(Image.id.in_(image_ids), Image.is_video == False).all()
    base = settings.AEYE_URL.rstrip("/")

    sent, errors = 0, []
    with _aeye_client() as client:
        for img in images:
            rel = _aeye_path(img.file_path)
            try:
                resp = client.post(f"{base}/analyze-path", json={"path": rel})
                resp.raise_for_status()
                sent += 1
            except Exception as exc:
                errors.append({"id": img.id, "error": str(exc)})

    return {"sent": sent, "errors": errors}


@router.post("/analyze-untagged")
def analyze_untagged(db: Session = Depends(get_db)):
    """Send all untagged non-video images to A-Eye for AI analysis."""
    if not settings.AEYE_URL:
        raise HTTPException(400, "A-Eye URL is not configured — set it in Settings")

    images = (
        db.query(Image)
        .filter(Image.is_video == False, ~Image.tags.any())
        .all()
    )

    if not images:
        return {"sent": 0, "errors": [], "message": "No untagged images found"}

    base = settings.AEYE_URL.rstrip("/")
    sent, errors = 0, []
    with _aeye_client() as client:
        for img in images:
            rel = _aeye_path(img.file_path)
            try:
                resp = client.post(f"{base}/analyze-path", json={"path": rel})
                resp.raise_for_status()
                sent += 1
            except Exception as exc:
                errors.append({"id": img.id, "error": str(exc)})

    return {"sent": sent, "total": len(images), "errors": errors}
