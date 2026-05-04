import logging
import os
import threading

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db, SessionLocal
from models import Image, Tag, ImageTag, Face

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

# Module-level face-describe job state
_face_job: dict = {"running": False, "total": 0, "done": 0, "errors": 0}
_face_job_lock = threading.Lock()


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
    with _job_lock:
        _job.update({"running": True, "total": len(image_ids), "done": 0, "errors": 0, "current": ""})

    db = SessionLocal()
    try:
        images = db.query(Image).filter(Image.id.in_(image_ids)).all()
        with _aeye_client() as client:
            for img in images:
                with _job_lock:
                    _job["current"] = img.filename or str(img.id)
                try:
                    # Always use /analyze-image (thumbnail bytes) so A-Eye returns tags
                    # synchronously. /analyze-path only enqueues in A-Eye's own pipeline
                    # and never sends results back to Eyeris.
                    _send_thumbnail(client, img, base, db)
                    # commit each item so results appear immediately
                    db.commit()
                    with _job_lock:
                        _job["done"] += 1
                except Exception as exc:
                    logger.warning("A-Eye: failed on image %s: %s", img.id, exc)
                    with _job_lock:
                        _job["errors"] += 1
        logger.info("A-Eye: completed %d / %d items", _job["done"], len(images))
    except Exception as exc:
        logger.error("A-Eye background worker error: %s", exc)
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


@router.get("/face-describe-status")
def face_describe_status():
    """Return current face-describe job progress."""
    with _face_job_lock:
        return dict(_face_job)


def _run_describe_faces(cluster_ids: list[int], base: str) -> None:
    """Background worker: send one representative crop per cluster to A-Eye for description."""
    with _face_job_lock:
        _face_job.update({"running": True, "total": len(cluster_ids), "done": 0, "errors": 0})

    db = SessionLocal()
    try:
        with _aeye_client() as client:
            for cluster_id in cluster_ids:
                face = (
                    db.query(Face)
                    .filter(Face.cluster_id == cluster_id, Face.crop_path.isnot(None))
                    .first()
                )
                if not face or not face.crop_path:
                    with _face_job_lock:
                        _face_job["done"] += 1
                    continue

                crop_full = os.path.join(settings.THUMBNAIL_DIR, face.crop_path)
                if not os.path.exists(crop_full):
                    with _face_job_lock:
                        _face_job["done"] += 1
                    continue

                try:
                    with open(crop_full, "rb") as f:
                        crop_bytes = f.read()
                    resp = client.post(
                        f"{base}/api/analyze-image",
                        files={"file": (face.crop_path, crop_bytes, "image/jpeg")},
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    description = (result.get("description") or "").strip()
                    if description:
                        face.description = description
                    db.commit()
                except Exception as exc:
                    logger.warning("A-Eye face describe: failed on cluster %s: %s", cluster_id, exc)
                    with _face_job_lock:
                        _face_job["errors"] += 1

                with _face_job_lock:
                    _face_job["done"] += 1

        logger.info("A-Eye face describe: completed %d / %d clusters", _face_job["done"], len(cluster_ids))
    except Exception as exc:
        logger.error("A-Eye face describe worker error: %s", exc)
    finally:
        db.close()
        with _face_job_lock:
            _face_job["running"] = False


@router.post("/describe-faces")
def describe_faces(db: Session = Depends(get_db)):
    """Queue one representative crop per cluster for A-Eye face description."""
    if not settings.AEYE_URL:
        raise HTTPException(400, "A-Eye URL is not configured — set it in Settings")

    with _face_job_lock:
        if _face_job["running"]:
            return {"queued": 0, "message": "Face describe job already running", "status": dict(_face_job)}

    # All distinct cluster_ids that have a crop_path
    rows = (
        db.query(Face.cluster_id)
        .filter(Face.cluster_id.isnot(None), Face.crop_path.isnot(None))
        .distinct()
        .all()
    )
    cluster_ids = [r.cluster_id for r in rows]

    if not cluster_ids:
        return {"queued": 0, "message": "No clusters with crop images found"}

    base = settings.AEYE_URL.rstrip("/")
    t = threading.Thread(target=_run_describe_faces, args=(cluster_ids, base), daemon=True)
    t.start()

    return {"queued": len(cluster_ids)}


# ---------------------------------------------------------------------------
# LLM face rescan — use A-Eye's /analyze-faces endpoint (bypasses template)
# ---------------------------------------------------------------------------

_JACCARD_THRESHOLD = 0.40  # word-overlap to consider two descriptions the same person


def _jaccard(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _cluster_descriptions(faces: list) -> list:
    """Assign cluster_ids to Face objects by Jaccard word-overlap on descriptions.

    Modifies Face.cluster_id in-place and returns the list.
    Uses a simple greedy union-find: each face joins the first existing cluster
    whose representative description exceeds the threshold.
    """
    # (cluster_id, representative_description)
    clusters: list[tuple[int, str]] = []
    next_id = 1

    for face in faces:
        desc = (face.description or "").strip()
        if not desc:
            face.cluster_id = next_id
            clusters.append((next_id, desc))
            next_id += 1
            continue

        matched = None
        for cid, rep in clusters:
            if _jaccard(desc, rep) >= _JACCARD_THRESHOLD:
                matched = cid
                break

        if matched is not None:
            face.cluster_id = matched
        else:
            face.cluster_id = next_id
            clusters.append((next_id, desc))
            next_id += 1

    return faces


def _run_llm_face_rescan(image_ids: list[int], base: str) -> None:
    """Background worker: LLM-based face detection via A-Eye /analyze-faces."""
    with _face_job_lock:
        _face_job.update({"running": True, "total": len(image_ids), "done": 0, "errors": 0})

    db = SessionLocal()
    try:
        # Clear all non-pinned faces first
        db.query(Face).filter(Face.pinned == False).delete(synchronize_session=False)
        db.commit()
        logger.info("LLM face rescan: cleared non-pinned faces, processing %d images", len(image_ids))

        images = db.query(Image).filter(Image.id.in_(image_ids), Image.is_video == False).all()
        new_faces: list[Face] = []

        with _aeye_client() as client:
            for img in images:
                with _face_job_lock:
                    _face_job["done"] += 1

                if not img.thumbnail_path:
                    continue
                thumb_full = os.path.join(settings.THUMBNAIL_DIR, img.thumbnail_path)
                if not os.path.exists(thumb_full):
                    continue

                try:
                    with open(thumb_full, "rb") as f:
                        thumb_bytes = f.read()

                    resp = client.post(
                        f"{base}/api/analyze-faces",
                        files={"file": (img.thumbnail_path, thumb_bytes, "image/jpeg")},
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    face_list = result.get("faces") or []

                    for entry in face_list:
                        desc = (entry.get("description") or "").strip()
                        if not desc:
                            continue
                        face = Face(
                            image_id=img.id,
                            description=desc,
                            crop_path=img.thumbnail_path,
                        )
                        db.add(face)
                        new_faces.append(face)

                    if face_list:
                        img.face_count = len(face_list)
                    db.flush()

                except Exception as exc:
                    logger.warning("LLM face rescan: failed on image %s: %s", img.id, exc)
                    with _face_job_lock:
                        _face_job["errors"] += 1

        # Flush so all new Face rows get IDs, then cluster by description similarity
        db.flush()
        if new_faces:
            # Offset cluster IDs above any pinned clusters
            from sqlalchemy import func as _func
            pinned_max = db.query(_func.max(Face.cluster_id)).filter(Face.pinned == True).scalar() or 0
            _cluster_descriptions(new_faces)
            for face in new_faces:
                if face.cluster_id is not None:
                    face.cluster_id += pinned_max

        db.commit()
        logger.info("LLM face rescan: complete — %d faces found across %d images",
                    len(new_faces), _face_job["done"])
    except Exception as exc:
        logger.error("LLM face rescan worker error: %s", exc)
    finally:
        db.close()
        with _face_job_lock:
            _face_job["running"] = False


@router.post("/llm-face-rescan")
def llm_face_rescan(db: Session = Depends(get_db)):
    """Clear non-pinned faces and re-detect people in all images via A-Eye LLM."""
    if not settings.AEYE_URL:
        raise HTTPException(400, "A-Eye URL is not configured — set it in Settings")

    with _face_job_lock:
        if _face_job["running"]:
            return {"queued": 0, "message": "A face job is already running", "status": dict(_face_job)}

    image_ids = [r.id for r in db.query(Image.id).filter(Image.is_video == False).all()]
    if not image_ids:
        return {"queued": 0, "message": "No images found"}

    base = settings.AEYE_URL.rstrip("/")
    t = threading.Thread(target=_run_llm_face_rescan, args=(image_ids, base), daemon=True)
    t.start()

    return {"queued": len(image_ids), "message": f"LLM face rescan started for {len(image_ids)} images"}
