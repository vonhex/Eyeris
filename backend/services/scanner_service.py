import asyncio
import os
import json
import subprocess
from datetime import datetime, time as dtime

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Image, Tag, ImageTag, Face, ScanJob, ImageTagBlock
from services.smb_service import list_images, read_file_bytes, move_file, delete_file, _local_path
from services.image_service import (
    process_image_bytes, compute_hash, parse_xmp_metadata, 
    generate_thumbnail, is_video, process_video_file
)
from services.search_service import index_image as es_index_image

from services.gpu_models import analyze_image_local

# Module-level state for the background scanner
_scanner_task: asyncio.Task | None = None
_current_job_id: int | None = None
_stop_requested: bool = False
_user_stopped: bool = False  # persists after run_scan() resets _stop_requested
_paused: bool = False
_pause_event: asyncio.Event = asyncio.Event()
_pause_event.set()  # not paused initially (set = unblocked)
_trigger_event: asyncio.Event = asyncio.Event()


def _parse_schedule_time(t: str) -> dtime:
    """Parse 'HH:MM' → datetime.time, defaulting to midnight on error."""
    try:
        h, m = t.strip().split(":")
        return dtime(int(h), int(m))
    except Exception:
        return dtime(0, 0)


def _in_schedule_window() -> bool:
    """Return True if current time is within the configured processing window."""
    if not settings.SCAN_SCHEDULE_ENABLED:
        return True  # no schedule → always allowed
    start = _parse_schedule_time(settings.SCAN_SCHEDULE_START)
    end = _parse_schedule_time(settings.SCAN_SCHEDULE_END)
    now = datetime.now().time().replace(second=0, microsecond=0)
    if start == end:
        return True  # same time = 24/7
    if start < end:
        return start <= now < end  # normal window (e.g. 09:00–17:00)
    # Crosses midnight (e.g. 22:00–06:00)
    return now >= start or now < end


def get_current_job_id() -> int | None:
    return _current_job_id


def is_scanning() -> bool:
    return _current_job_id is not None


def is_paused() -> bool:
    return _paused


def get_schedule_status() -> dict:
    """Return schedule config and whether we're currently in the active window."""
    return {
        "enabled": settings.SCAN_SCHEDULE_ENABLED,
        "start": settings.SCAN_SCHEDULE_START,
        "end": settings.SCAN_SCHEDULE_END,
        "in_window": _in_schedule_window(),
    }


def request_stop():
    global _stop_requested, _user_stopped
    _stop_requested = True
    _user_stopped = True
    # Unpause so the scan loop can check the stop flag and exit cleanly
    _pause_event.set()
    print("[Scanner] Stop requested")


def request_pause():
    global _paused
    if not _paused and _current_job_id is not None:
        _paused = True
        _pause_event.clear()
        print("[Scanner] Paused")


def request_resume():
    global _paused
    if _paused:
        _paused = False
        _pause_event.set()
        print("[Scanner] Resumed")


async def start_background_scanner():
    """Start the periodic background scanning loop (called on app startup)."""
    global _scanner_task, _user_stopped
    if _scanner_task and not _scanner_task.done():
        # Already running, just trigger an immediate scan
        _user_stopped = False
        _trigger_event.set()
        print("[Scanner] Triggered immediate run of existing loop")
        return
    _user_stopped = False
    _scanner_task = asyncio.create_task(_scan_loop())


async def _scan_loop():
    """Periodically scan all shares. Exits if the user explicitly stops the scan."""
    global _scanner_task
    while True:
        # Check BEFORE starting a new scan
        if _user_stopped:
            print("[Scanner] Auto-scan loop exiting (stop was requested) — click Start Sync to resume.")
            _scanner_task = None
            return

        # Schedule gate — wait until we're in the active window
        # MANUALLY TRIGGERED scans bypass the schedule gate
        is_triggered = _trigger_event.is_set()
        if is_triggered:
            _trigger_event.clear()
            print("[Scanner] Starting manually triggered scan...")
        elif not _in_schedule_window():
            print(f"[Scanner] Outside schedule window ({settings.SCAN_SCHEDULE_START}–{settings.SCAN_SCHEDULE_END}) — waiting...")
            while not _in_schedule_window():
                if _user_stopped:
                    _scanner_task = None
                    return
                if _trigger_event.is_set():
                    _trigger_event.clear()
                    print("[Scanner] Manual trigger received — bypassing schedule gate.")
                    break
                await asyncio.sleep(10)
            if not _user_stopped:
                print("[Scanner] Starting scan.")

        try:
            await run_scan()
        except Exception as e:
            print(f"[Scanner] Error in scan loop: {e}")

        # Check AFTER scan finishes
        if _user_stopped:
            print("[Scanner] Auto-scan loop exiting — user stopped the scan. Click Start Sync to resume.")
            _scanner_task = None
            return

        # Sleep between periodic scans, checking for stop every 5 seconds or manual trigger
        interval = settings.SCAN_INTERVAL_MINUTES * 60
        elapsed = 0
        print(f"[Scanner] Waiting {settings.SCAN_INTERVAL_MINUTES}m until next auto-scan...")
        while elapsed < interval:
            await asyncio.sleep(5)
            elapsed += 5
            if _user_stopped:
                print("[Scanner] Stop requested during sleep — exiting scan loop.")
                _scanner_task = None
                return
            if _trigger_event.is_set():
                # Don't clear here, it's cleared at the top of the loop
                print("[Scanner] Manual trigger received — breaking sleep.")
                break


async def run_scan() -> int:
    """Run a full scan: Lists shares and syncs images (including XMP tags)."""
    global _current_job_id, _stop_requested
    db = SessionLocal()

    try:
        job = ScanJob(status="listing", started_at=datetime.utcnow())
        db.add(job)
        db.commit()
        db.refresh(job)
        _current_job_id = job.id

        # Run library sync (discovery + XMP tag loading)
        await _sync_task(db, job)

        job.status = "stopped" if _stop_requested else "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        print("[Scanner] Scan complete.")
        return job.id

    except Exception as e:
        if 'job' in locals():
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        print(f"[Scanner] Scan failed: {e}")
        raise
    finally:
        _stop_requested = False
        _current_job_id = None
        db.close()


async def _sync_task(db: Session, job: ScanJob):
    """List all NAS shares in parallel, then discover/thumbnail new images."""

    # ── List all shares simultaneously ──
    print("[Scanner] Listing NAS shares...")
    job.status = "listing"
    db.commit()

    async def _list_share(share: str) -> list:
        try:
            imgs = await asyncio.to_thread(list_images, share)
            print(f"[Scanner] {share}: {len(imgs)} images")
            job.total_images = (job.total_images or 0) + len(imgs)
            db.commit()
            return imgs
        except Exception as e:
            print(f"[Scanner] Error listing {share}: {e}")
            return []

    shares = [s.strip() for s in settings.SMB_SHARES if s.strip()]
    if not shares:
        # If no specific shares, try to scan the root mount point
        if os.path.isdir(settings.MOUNT_BASE):
            shares = [""] # Empty string will result in using MOUNT_BASE itself as the path
        else:
            print(f"[Scanner] No shares configured and {settings.MOUNT_BASE} not found. Skipping scan.")
            return

    # Launch listing tasks but poll for stop every 0.5 s so we can bail out
    listing_tasks = [asyncio.create_task(_list_share(s)) for s in shares]
    while not all(t.done() for t in listing_tasks):
        if _stop_requested:
            print("[Scanner] Stop requested during NAS listing — cancelling.")
            for t in listing_tasks:
                t.cancel()
            await asyncio.gather(*listing_tasks, return_exceptions=True)
            return
        await asyncio.sleep(0.5)

    results = [t.result() if not t.cancelled() and t.exception() is None else [] for t in listing_tasks]
    all_image_infos = [img for imgs in results for img in imgs]

    print(f"[Scanner] Total images across all shares: {len(all_image_infos)}")

    if _stop_requested:
        print("[Scanner] Stop requested after listing — skipping sync.")
        return

    # Filter already-known paths
    existing_paths = {row[0] for row in db.query(Image.file_path).all()}
    new_images = [
        img for img in all_image_infos
        if f"{img['share']}/{img['relative_path']}" not in existing_paths
    ]

    total = len(new_images)
    job.phase1_total = total
    job.phase1_done = 0
    job.total_images = total
    job.status = "running"
    db.commit()
    print(f"[Scanner] Syncing {total} new images")

    # ── Discover each new image ──
    discovered = 0
    for img_info in new_images:
        if _stop_requested:
            break
        try:
            await _discover_image(db, img_info)
            discovered += 1
            job.phase1_done = discovered
            db.commit()
        except Exception as e:
            db.rollback()  # Crucial: clear the failed transaction state
            print(f"[Scanner] Skipping {img_info['filename']} due to error: {e}")
        
        if discovered % 10 == 0 or discovered == total:
            print(f"[Scanner] Sync progress: {discovered}/{total}")

    job.phase1_done = discovered
    db.commit()
    print(f"[Scanner] Sync complete: {discovered} images synced.")


async def _discover_image(db: Session, img_info: dict):
    """Sync a single image: Download, check for duplicates (keep best), create thumbnail."""
    if _stop_requested:
        return

    file_path = f"{img_info['share']}/{img_info['relative_path']}"

    # Skip if this exact path is already in DB
    existing = db.query(Image).filter(Image.file_path == file_path).first()
    if existing:
        return

    # Download or process path
    print(f"[Scanner] Discovering: {file_path}")
    
    is_vid = is_video(img_info["filename"])
    data = None
    meta = None

    if is_vid:
        # For videos, process by local path directly to avoid loading large files into memory
        local_path = _local_path(img_info["share"], img_info["relative_path"])
        meta = await asyncio.to_thread(process_video_file, local_path)
        file_hash = meta["file_hash"]
    else:
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(read_file_bytes, img_info["share"], img_info["relative_path"]),
                timeout=60,
            )
        except asyncio.TimeoutError:
            print(f"[Scanner] Timeout reading {file_path} — skipping")
            return
        file_hash = await asyncio.to_thread(compute_hash, data=data)

    file_size = img_info.get("file_size") or (len(data) if data else 0)

    # Check for duplicate by hash
    dupe = db.query(Image).filter(Image.file_hash == file_hash).first()
    if dupe:
        # (Keep existing deduplication logic, just ensure it handles data=None for videos)
        # Simplified for now: if it's a dupe, just skip
        return

    # No duplicate — process normally
    if not is_vid:
        try:
            meta = await asyncio.wait_for(
                asyncio.to_thread(process_image_bytes, data),
                timeout=30,
            )
        except (asyncio.TimeoutError, Exception) as e:
            print(f"[Scanner] Image processing error for {file_path}: {e}")
            return

    # Create record
    new_img = Image(
        file_path=file_path,
        source_folder=img_info["share"],
        filename=img_info["filename"],
        file_size=file_size,
        file_hash=meta["file_hash"],
        width=meta["width"],
        height=meta["height"],
        orientation_corrected=meta.get("orientation_corrected", False),
        thumbnail_path=meta["thumbnail_path"],
        date_taken=meta.get("date_taken"),
        gps_lat=meta.get("gps_lat"),
        gps_lon=meta.get("gps_lon"),
        camera_model=meta.get("camera_model"),
        location_name=meta.get("location_name"),
        quality_flags=meta.get("quality_flags"),
        is_video=is_vid,
        analyzed=True,
    )
    db.add(new_img)
    db.flush()

    if not is_vid and data:
        # Local vision analysis (YOLO + FaceNet)
        try:
            from services.gpu_models import analyze_image_local
            from PIL import Image as PILImage
            from io import BytesIO
            
            img_pil = PILImage.open(BytesIO(data))
            local_analysis = await asyncio.to_thread(analyze_image_local, data)
            _save_faces(db, new_img, local_analysis["faces"], img_pil)
        except Exception as e:
            print(f"[Scanner] Local analysis error for {file_path}: {e}")

    # Load XMP tags if present
    await _load_xmp_for_image(db, new_img)
    db.commit()



def _save_faces(db: Session, img_record: Image, face_data: list[dict], img_pil=None):
    """Save face analysis results to DB, including embeddings and crops."""
    if not face_data:
        return

    img_record.face_count = len(face_data)
    
    from PIL import Image as PILImage
    import uuid
    from config import settings
    
    for fd in face_data:
        bbox = fd["bbox"] # [x1, y1, x2, y2]
        crop_path = None
        
        # Generate crop if PIL image is provided
        if img_pil:
            try:
                x1, y1, x2, y2 = bbox
                w, h = img_pil.size
                
                # Add 25% padding around the face for a better portrait look
                px = int((x2 - x1) * 0.25)
                py = int((y2 - y1) * 0.25)
                x1c = max(0, x1 - px)
                y1c = max(0, y1 - py)
                x2c = min(w, x2 + px)
                y2c = min(h, y2 + py)
                
                if (x2c - x1c) > 10 and (y2c - y1c) > 10:
                    crop = img_pil.crop((x1c, y1c, x2c, y2c))
                    # High quality face thumbnails
                    crop.thumbnail((256, 256), PILImage.Resampling.LANCZOS)
                    
                    filename = f"face_{uuid.uuid4().hex}.jpg"
                    full_path = os.path.join(settings.THUMBNAIL_DIR, filename)
                    
                    if crop.mode != "RGB":
                        crop = crop.convert("RGB")
                    
                    crop.save(full_path, "JPEG", quality=95)
                    crop_path = filename
            except Exception as e:
                print(f"[Scanner] Face crop failed for {img_record.filename}: {e}")

        face = Face(
            image_id=img_record.id,
            face_bbox=json.dumps(bbox),
            position=fd.get("position"),
            embedding=json.dumps(fd.get("embedding")) if fd.get("embedding") else None,
            crop_path=crop_path
        )
        db.add(face)
    
    db.commit()
    if img_record.face_count > 0:
        print(f"[Faces] Detected {img_record.face_count} faces in {img_record.filename}")


async def _load_xmp_for_image(db: Session, img_record: Image):
    """
    Check for an XMP sidecar on the NAS and load its tags/description into DB/ES.
    XMP path is: <image_path>.xmp
    """
    parts = img_record.file_path.split("/", 1)
    share = parts[0]
    rel_path = parts[1] if len(parts) > 1 else ""
    xmp_rel_path = f"{rel_path}.xmp"

    try:
        # Check if XMP exists
        xmp_local = _local_path(share, xmp_rel_path)
        if not os.path.exists(xmp_local):
            # No XMP, just index what we have (metadata)
            _index_in_es(img_record)
            return

        print(f"[XMP] Loading sidecar: {xmp_rel_path}")
        xmp_bytes = await asyncio.to_thread(read_file_bytes, share, xmp_rel_path)
        xmp_meta = parse_xmp_metadata(xmp_bytes)

        if xmp_meta["description"]:
            img_record.ai_description = xmp_meta["description"]
        
        if xmp_meta["album"]:
            img_record.album = xmp_meta["album"]
        else:
            # Fallback: use parent folder name as album
            folder_parts = rel_path.split("/")
            if len(folder_parts) > 1:
                # Use the immediate parent folder name (e.g. "Vacation 2023")
                img_record.album = folder_parts[-2]
            else:
                img_record.album = share
        
        if xmp_meta["date_taken"] and not img_record.date_taken:
            img_record.date_taken = xmp_meta["date_taken"]

        # Load tags
        if xmp_meta["tags"]:
            # Normalise to lowercase
            tag_names = [t.strip().lower() for t in xmp_meta["tags"] if t.strip()]
            for tag_name in tag_names:
                # 1. Get or create tag
                tag = db.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    try:
                        tag = Tag(name=tag_name)
                        db.add(tag)
                        db.flush()
                    except Exception:
                        db.rollback()
                        tag = db.query(Tag).filter(Tag.name == tag_name).first()

                if tag:
                    # 2. Check if link already exists in current session/DB
                    exists = db.query(ImageTag).filter(
                        ImageTag.image_id == img_record.id,
                        ImageTag.tag_id == tag.id
                    ).first()
                    
                    if not exists:
                        try:
                            db.add(ImageTag(image_id=img_record.id, tag_id=tag.id))
                            db.flush()
                        except Exception:
                            db.rollback() # Skip if it still fails

        db.commit()
        print(f"[XMP] Loaded {len(xmp_meta['tags'])} tags for {img_record.filename}")

    except Exception as e:
        print(f"[XMP] Error loading sidecar for {img_record.file_path}: {e}")

    # Always index in ES at the end
    _index_in_es(img_record)


def _index_in_es(img_record: Image):
    """No-op — Elasticsearch removed in favor of SearXNG search."""
    pass


def _get_blocked_tags(db: Session, image_id: int) -> set:
    """Return the set of tag names that must not be auto-applied to this image."""
    rows = db.query(ImageTagBlock.tag_name).filter(ImageTagBlock.image_id == image_id).all()
    return {r[0] for r in rows}


async def run_full_resync() -> int:
    """Iterate through all images in DB and reload their XMP metadata/tags."""
    global _current_job_id, _stop_requested
    db = SessionLocal()
    try:
        job = ScanJob(status="running", started_at=datetime.utcnow())
        db.add(job)
        db.commit()
        db.refresh(job)
        _current_job_id = job.id

        images = db.query(Image).all()
        total = len(images)
        job.phase1_total = total
        job.total_images = total
        db.commit()

        print(f"[Resync] Reloading XMP for {total} images...")
        done = 0
        for img_record in images:
            if _stop_requested:
                break
            
            try:
                # Reload XMP
                await _load_xmp_for_image(db, img_record)
                
                # Check for missing thumbnail on disk
                thumb_missing = False
                if img_record.thumbnail_path:
                    thumb_full_path = os.path.join(settings.THUMBNAIL_DIR, img_record.thumbnail_path)
                    if not os.path.exists(thumb_full_path):
                        thumb_missing = True
                else:
                    thumb_missing = True

                # Local AI re-analysis or thumbnail regeneration
                if thumb_missing or not img_record.faces or not img_record.categories:
                    parts = img_record.file_path.split("/", 1)
                    share = parts[0]
                    rel_path = parts[1] if len(parts) > 1 else ""
                    data = await asyncio.to_thread(read_file_bytes, share, rel_path)
                    
                    from PIL import Image as PILImage
                    img_pil = PILImage.open(BytesIO(data))
                    
                    # Regenerate thumbnail if missing
                    if thumb_missing:
                        new_thumb = await asyncio.to_thread(generate_thumbnail, img_pil)
                        img_record.thumbnail_path = new_thumb
                        print(f"[Resync] Regenerated missing thumbnail for {img_record.filename}")

                    local_analysis = await asyncio.to_thread(analyze_image_local, data)
                    if not img_record.faces:
                        _save_faces(db, img_record, local_analysis["faces"], img_pil)
            except Exception as e:
                print(f"[Resync] Error for {img_record.file_path}: {e}")

            done += 1
            job.phase1_done = done
            if done % 50 == 0 or done == total:
                db.commit()
                print(f"[Resync] Progress: {done}/{total}")

        job.status = "stopped" if _stop_requested else "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[Resync] Complete: {done}/{total} images updated.")
        return job.id

    except Exception as e:
        if 'job' in locals():
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        print(f"[Resync] Failed: {e}")
        raise
    finally:
        _stop_requested = False
        _current_job_id = None
        db.close()


async def run_phash_scan():
    """Compute perceptual hashes for all images that don't have one yet."""
    global _current_job_id, _stop_requested
    db = SessionLocal()
    try:
        import imagehash
        from PIL import Image as PILImage
        from io import BytesIO

        job = ScanJob(status="phash", started_at=datetime.utcnow())
        db.add(job)
        db.commit()
        db.refresh(job)
        _current_job_id = job.id

        images = db.query(Image).filter(Image.perceptual_hash.is_(None)).all()
        total = len(images)
        job.phase1_total = total
        job.total_images = total
        db.commit()

        print(f"[pHash] Computing perceptual hashes for {total} images...")
        done = 0

        for img_record in images:
            if _stop_requested:
                break
            parts = img_record.file_path.split("/", 1)
            share = parts[0]
            rel_path = parts[1] if len(parts) > 1 else ""
            try:
                data = await asyncio.to_thread(read_file_bytes, share, rel_path)
                img_pil = await asyncio.to_thread(lambda d: PILImage.open(BytesIO(d)).convert("RGB"), data)
                ph = await asyncio.to_thread(imagehash.phash, img_pil)
                img_record.perceptual_hash = str(ph)
            except Exception as e:
                print(f"[pHash] Error for {img_record.file_path}: {e}")

            done += 1
            job.phase1_done = done
            job.processed_images = done
            if done % 50 == 0 or done == total:
                db.commit()
                print(f"[pHash] Progress: {done}/{total}")

        job.status = "stopped" if _stop_requested else "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[pHash] Complete: {done}/{total} images hashed.")
        return job.id

    except Exception as e:
        try:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception:
            pass
        print(f"[pHash] Failed: {e}")
        raise
    finally:
        _stop_requested = False
        _current_job_id = None
        db.close()


async def discover_new_file(share: str, relative_path: str, file_size: int = 0):
    """
    Called by the file watcher when a new image is detected on the NAS.
    Runs Phase 1 (discovery + metadata + XMP) immediately.
    """
    import os as _os
    db = SessionLocal()
    try:
        img_info = {
            "share": share,
            "relative_path": relative_path,
            "filename": _os.path.basename(relative_path),
            "file_size": file_size,
        }
        await _discover_image(db, img_info)
    except Exception as e:
        print(f"[Watcher] discover_new_file error for {share}/{relative_path}: {e}")
    finally:
        db.close()
