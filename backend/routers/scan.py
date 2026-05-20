import asyncio
import os
import shutil

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import ScanJob
from schemas import ScanJobOut
from services.scanner_service import (
    run_scan, run_phash_scan, run_full_resync, run_xmp_resync,
    get_current_job_id, is_scanning, is_paused,
    request_stop, request_pause, request_resume,
    start_background_scanner,
    get_schedule_status,
)

router = APIRouter(prefix="/api/scan", tags=["scan"])

# GPS backfill state
_gps_backfill_state: dict = {"running": False, "total": 0, "done": 0, "updated": 0}


@router.get("/status")
def scan_status(db: Session = Depends(get_db)):
    # Return current running job, or most recent job, plus pause/schedule state
    job_id = get_current_job_id()
    job = None
    if job_id:
        job = db.query(ScanJob).filter(ScanJob.id == job_id).first()
    if not job:
        job = db.query(ScanJob).order_by(ScanJob.id.desc()).first()

    job_data = ScanJobOut.model_validate(job).model_dump() if job else None
    return {
        "job": job_data,
        "paused": is_paused(),
        "schedule": get_schedule_status(),
    }


@router.post("/pause")
def pause_scan():
    if not is_scanning():
        return {"status": "error", "message": "No scan running"}
    request_pause()
    return {"status": "ok", "message": "Scan paused"}


@router.post("/resume")
def resume_scan():
    request_resume()
    return {"status": "ok", "message": "Scan resumed"}


@router.get("/history", response_model=list[ScanJobOut])
def scan_history(db: Session = Depends(get_db)):
    jobs = db.query(ScanJob).order_by(ScanJob.id.desc()).limit(20).all()
    return jobs


@router.post("/start")
async def start_scan():
    if is_scanning():
        return {"status": "ok", "message": "Scan already running"}
    # start_background_scanner resets _user_stopped and starts the periodic loop
    await start_background_scanner()
    return {"status": "ok", "message": "Scan started"}


@router.get("/gps-backfill-status")
def gps_backfill_status():
    return _gps_backfill_state


@router.get("/debug-gps/{image_id}")
async def debug_gps(image_id: int, db: Session = Depends(get_db)):
    """Read one image and return exactly what GPS data PIL sees in its EXIF."""
    from models import Image as ImageModel
    from services.smb_service import read_file_bytes
    from io import BytesIO

    img = db.query(ImageModel).filter(ImageModel.id == image_id).first()
    if not img:
        return {"error": "image not found"}

    try:
        parts = img.file_path.split("/", 1)
        share, rel = parts[0], parts[1] if len(parts) > 1 else ""
        data = await asyncio.to_thread(read_file_bytes, share, rel)
    except Exception as e:
        return {"error": f"could not read file: {e}", "file_path": img.file_path}

    try:
        import re as _re
        # Extract embedded XMP from JPEG APP1 segment
        xmp_match = _re.search(b'<x:xmpmeta.*?</x:xmpmeta>', data, _re.DOTALL)
        xmp_str = xmp_match.group(0).decode("utf-8", errors="replace") if xmp_match else None

        gps_in_xmp = {}
        if xmp_str:
            for tag in ("GPSLatitude", "GPSLongitude", "GPSLatitudeRef", "GPSLongitudeRef"):
                m = _re.search(rf'(?:exif:{tag}|{tag})[=\s>"\']+([^<\s"\']+)', xmp_str)
                if m:
                    gps_in_xmp[tag] = m.group(1)

        from services.image_service import extract_gps_from_bytes
        lat, lon = extract_gps_from_bytes(data)
        return {
            "file_path": img.file_path,
            "extracted_lat": lat,
            "extracted_lon": lon,
            "has_embedded_xmp": xmp_str is not None,
            "gps_in_xmp": gps_in_xmp,
            "xmp_snippet": xmp_str[:2000] if xmp_str else None,
        }
    except Exception as e:
        return {"error": f"debug error: {e}", "file_path": img.file_path}


@router.post("/backfill-gps")
async def backfill_gps(db: Session = Depends(get_db)):
    """Re-extract GPS coordinates from EXIF for all images that are missing them."""
    from models import Image as ImageModel

    if _gps_backfill_state["running"]:
        return {"status": "ok", "message": "GPS backfill already running"}

    images = db.query(ImageModel).filter(
        ImageModel.gps_lat.is_(None),
        ImageModel.is_video == False,
    ).all()

    if not images:
        return {"status": "ok", "updated": 0, "message": "No images need GPS backfill"}

    asyncio.create_task(_run_gps_backfill(images))
    return {"status": "ok", "message": f"GPS backfill started for {len(images)} images"}


async def _run_gps_backfill(images):
    from database import SessionLocal
    from models import Image as ImageModel
    from services.image_service import extract_gps_from_bytes
    from services.smb_service import read_file_bytes

    _gps_backfill_state["running"] = True
    _gps_backfill_state["total"] = len(images)
    _gps_backfill_state["done"] = 0
    _gps_backfill_state["updated"] = 0

    for img in images:
        try:
            parts = img.file_path.split("/", 1)
            share = parts[0]
            rel = parts[1] if len(parts) > 1 else ""
            data = await asyncio.to_thread(read_file_bytes, share, rel)
            lat, lon = extract_gps_from_bytes(data)
            if lat is not None and lon is not None:
                location_name = None
                try:
                    import reverse_geocode
                    result = reverse_geocode.search([(lat, lon)])
                    if result:
                        city = result[0].get("city", "")
                        country = result[0].get("country", "")
                        location_name = ", ".join(filter(None, [city, country]))
                except Exception:
                    pass
                db = SessionLocal()
                try:
                    record = db.query(ImageModel).filter(ImageModel.id == img.id).first()
                    if record:
                        record.gps_lat = lat
                        record.gps_lon = lon
                        if location_name and not record.location_name:
                            record.location_name = location_name
                        db.commit()
                        _gps_backfill_state["updated"] += 1
                finally:
                    db.close()
        except Exception as e:
            print(f"[GPS backfill] Failed for image {img.id}: {e}")
        finally:
            _gps_backfill_state["done"] += 1

    print(f"[GPS backfill] Complete — updated {_gps_backfill_state['updated']} images")
    _gps_backfill_state["running"] = False


@router.post("/resync")
async def resync():
    """Trigger a full re-sync of all image metadata, XMP tags, and missing thumbnails."""
    if is_scanning():
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="A scan is already running. Stop it first.")
    asyncio.create_task(run_full_resync())
    return {"status": "ok", "message": "Full re-sync started"}


@router.post("/xmp-resync")
async def xmp_resync_scan():
    """Re-read XMP sidecar files for all images that currently have no tags."""
    if is_scanning():
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="A scan is already running. Stop it first.")
    asyncio.create_task(run_xmp_resync())
    return {"status": "ok", "message": "XMP re-sync started"}


@router.post("/phash")
async def phash_scan():
    """Compute perceptual hashes for all images (for visual duplicate detection)."""
    if is_scanning():
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="A scan is already running. Stop it first.")
    asyncio.create_task(run_phash_scan())
    return {"status": "ok", "message": "Perceptual hash scan started"}


@router.post("/stop")
async def stop_scan():
    request_stop()
    return {"status": "ok", "message": "Stop requested"}


@router.post("/reset")
def reset_database(db: Session = Depends(get_db)):
    """Delete ALL images, tags, faces and scan history for a fresh start."""
    if is_scanning():
        return {"status": "error", "message": "Stop the scan before resetting"}

    # Delete all thumbnail files (including face crops)
    try:
        thumb_dir = settings.THUMBNAIL_DIR
        if os.path.isdir(thumb_dir):
            for entry in os.listdir(thumb_dir):
                entry_path = os.path.join(thumb_dir, entry)
                if os.path.isfile(entry_path):
                    os.remove(entry_path)
                elif os.path.isdir(entry_path):
                    shutil.rmtree(entry_path)
    except Exception as e:
        print(f"[Reset] Thumbnail cleanup error: {e}")

    # Truncate all tables — disable FK checks so order doesn't matter
    from sqlalchemy import text
    is_sqlite = "sqlite" in str(db.get_bind().url)

    try:
        if is_sqlite:
            db.execute(text("PRAGMA foreign_keys = OFF"))
        else:
            db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

        # Check once if sqlite_sequence exists (only present when AUTOINCREMENT is used)
        has_seq = False
        if is_sqlite:
            has_seq = bool(db.execute(text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            )).scalar())

        for tbl in ("faces", "image_tags", "image_categories", "images", "tags", "categories", "scan_jobs"):
            if is_sqlite:
                db.execute(text(f"DELETE FROM {tbl}"))
                if has_seq:
                    db.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{tbl}'"))
            else:
                db.execute(text(f"TRUNCATE TABLE {tbl}"))

        if is_sqlite:
            db.execute(text("PRAGMA foreign_keys = ON"))
        else:
            db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        db.commit()
    except Exception as e:
        db.rollback()
        try:
            if is_sqlite:
                db.execute(text("PRAGMA foreign_keys = ON"))
            else:
                db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        except:
            pass
        print(f"[Reset] DB reset error: {e}")
        return {"status": "error", "message": str(e)}

    print("[Reset] Database cleared")
    return {"status": "ok", "message": "Database reset complete"}


