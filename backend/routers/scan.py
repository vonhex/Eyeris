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


@router.post("/gpu-rescan")
async def gpu_rescan():
    """Trigger a full re-sync of all image metadata and XMP tags."""
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


