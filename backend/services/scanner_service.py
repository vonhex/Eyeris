import asyncio
import os
import httpx
from datetime import datetime, time as dtime

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Image, Tag, ImageTag, ScanJob, ImageTagBlock
from services.smb_service import list_images, read_file_bytes, move_file, delete_file, _local_path
from services.image_service import (
    process_image_bytes, compute_hash, parse_xmp_metadata, 
    generate_thumbnail, is_video, process_video_file
)
from services.search_service import index_image as es_index_image

# Module-level state for the background scanner
_scanner_task: asyncio.Task | None = None
_current_job_id: int | None = None
_stop_requested: bool = False
_user_stopped: bool = False  # persists after run_scan() resets _stop_requested
_paused: bool = False
_pause_event: asyncio.Event = asyncio.Event()
_pause_event.set()  # not paused initially (set = unblocked)
_trigger_event: asyncio.Event = asyncio.Event()


async def _load_metadata_from_aeye(rel_path: str) -> dict | None:
    """Fetch robust EXIF metadata from A-Eye via its API."""
    if not settings.AEYE_URL:
        return None

    # rel_path is something like "photos/IMG_1234.jpg"
    # A-Eye's photos_dir is usually mapped to the same NAS root
    url = f"{settings.AEYE_URL.rstrip('/')}/api/images/by-path/{rel_path.lstrip('/')}"
    
    auth = None
    if settings.AEYE_USER and settings.AEYE_PASS:
        auth = (settings.AEYE_USER, settings.AEYE_PASS)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=auth)
            if resp.status_code == 200:
                data = resp.json()
                # A-Eye schema: camera_model, exif_raw (json string in DB, dict in API)
                # Shooting data in A-Eye's raw EXIF:
                # Aperture (33437), Shutter (33434), ISO (34855), FocalLength (37386), LensModel (42036)
                raw = data.get("exif_raw") or {}
                
                # A-Eye might have pre-parsed these into columns or we can extract from raw
                # A-Eye actually stores camera_model, gps_lat, gps_lon, exif_date in columns
                return {
                    "camera_model": data.get("camera_model"),
                    "gps_lat": data.get("gps_lat"),
                    "gps_lon": data.get("gps_lon"),
                    "date_taken": data.get("exif_date"), # This is "YYYY-MM-DD" in A-Eye
                    "raw_exif": raw
                }
    except Exception as e:
        print(f"[A-Eye API] Failed to fetch metadata for {rel_path}: {e}")
    
    return None


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


_aeye_poll_task: asyncio.Task | None = None
_AEYE_POLL_INTERVAL = 300  # seconds between XMP sidecar checks


async def start_aeye_xmp_poll():
    """Start the silent background loop that auto-imports XMP sidecars written by A-Eye."""
    global _aeye_poll_task
    if _aeye_poll_task and not _aeye_poll_task.done():
        return
    _aeye_poll_task = asyncio.create_task(_aeye_xmp_poll_loop())


async def _aeye_xmp_poll_loop():
    """Every 5 minutes, quietly check untagged images for XMP sidecars written by A-Eye.

    Runs silently — no ScanJob is created, no UI progress shown.
    Only active when AEYE_URL is configured.
    """
    while True:
        await asyncio.sleep(_AEYE_POLL_INTERVAL)
        if not settings.AEYE_URL:
            continue
        db = SessionLocal()
        try:
            images = (
                db.query(Image)
                .filter(~Image.tags.any(), Image.is_video == False)
                .all()
            )
            if not images:
                db.close()
                continue

            imported = 0
            for img in images:
                tags_before = len(img.tags)
                try:
                    await _load_xmp_for_image(db, img)
                    db.flush()
                    if len(img.tags) > tags_before:
                        imported += 1
                except Exception as e:
                    print(f"[A-Eye Poll] XMP check error for {img.file_path}: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass

            if imported:
                db.commit()
                print(f"[A-Eye Poll] Auto-imported XMP tags for {imported} image(s)")
            else:
                db.rollback()
        except Exception as e:
            print(f"[A-Eye Poll] Loop error: {e}")
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()


async def start_background_scanner():
    """Start the periodic background scanning loop (called on app startup)."""
    global _scanner_task, _user_stopped, _paused
    if _scanner_task and not _scanner_task.done():
        # Already running, just trigger an immediate scan
        _user_stopped = False
        _trigger_event.set()
        print("[Scanner] Triggered immediate run of existing loop")
        return
    _user_stopped = False
    _paused = False
    _pause_event.set()  # clear any leftover pause state
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


async def _auto_send_to_aeye():
    """After a scan, auto-send any untagged images to A-Eye if configured."""
    if not settings.AEYE_URL:
        return
    db = SessionLocal()
    try:
        images = db.query(Image).filter(~Image.tags.any(), Image.is_video == False).all()
        if not images:
            return
        image_ids = [img.id for img in images]
    finally:
        db.close()

    import threading
    from routers.aeye import _job, _job_lock, _run_analyze_untagged
    with _job_lock:
        if _job["running"]:
            print(f"[Scanner] A-Eye job already running — skipping auto-send of {len(image_ids)} untagged images")
            return

    base = settings.AEYE_URL.rstrip("/")
    print(f"[Scanner] Auto-sending {len(image_ids)} untagged images to A-Eye")
    t = threading.Thread(target=_run_analyze_untagged, args=(image_ids, base), daemon=True)
    t.start()


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

        if not _stop_requested:
            asyncio.create_task(_auto_send_to_aeye())

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

    if not os.path.isdir(settings.MOUNT_BASE):
        print(f"[Scanner] Mount not found: {settings.MOUNT_BASE}. Skipping scan.")
        return

    all_image_infos = await asyncio.to_thread(list_images, "")
    print(f"[Scanner] Total images found: {len(all_image_infos)}")

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
        except Exception as e:
            db.rollback()  # Crucial: clear the failed transaction state
            print(f"[Scanner] Skipping {img_info['filename']} due to error: {e}")
        
        if discovered % 10 == 0 or discovered == total:
            db.commit() # Batch commit every 10 images
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
        if dupe.file_path != file_path:
            old_parts = dupe.file_path.split("/", 1)
            old_local = _local_path(old_parts[0], old_parts[1] if len(old_parts) > 1 else "")
            if not os.path.exists(old_local):
                # Original gone — destructive rename, update path and load XMP
                print(f"[Scanner] Rename detected: {dupe.file_path} → {file_path}")
                dupe.file_path = file_path
                dupe.filename = img_info["filename"]
                dupe.source_folder = img_info["share"]
                if file_size:
                    dupe.file_size = file_size
                db.flush()
                await _load_xmp_for_image(db, dupe)
            else:
                # Both files exist — A-EYE created a renamed copy alongside the original.
                # Try to load XMP from the new path (A-EYE puts XMP next to the renamed file).
                await _load_xmp_for_image(db, dupe, xmp_base_path=file_path)
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
        lens_model=meta.get("lens_model"),
        aperture=meta.get("aperture"),
        shutter_speed=meta.get("shutter_speed"),
        iso=meta.get("iso"),
        focal_length=meta.get("focal_length"),
    )

    # Attempt to enrich with robust metadata from A-Eye API
    aeye_meta = await _load_metadata_from_aeye(img_info["relative_path"])
    if aeye_meta:
        if aeye_meta.get("camera_model"):
            new_img.camera_model = aeye_meta["camera_model"]
        if aeye_meta.get("gps_lat") is not None:
            new_img.gps_lat = aeye_meta["gps_lat"]
        if aeye_meta.get("gps_lon") is not None:
            new_img.gps_lon = aeye_meta["gps_lon"]
        
        # Extract shooting data from A-Eye's raw EXIF if local extraction was shallow
        raw = aeye_meta.get("raw_exif") or {}
        
        # Aperture (33437)
        if not new_img.aperture and "EXIF FNumber" in raw:
            try:
                # exifread format is usually "2.8" or "14/5"
                val = raw["EXIF FNumber"]
                if "/" in val:
                    n, d = map(float, val.split("/"))
                    new_img.aperture = round(n/d, 1)
                else:
                    new_img.aperture = float(val)
            except Exception: pass
            
        # Shutter (33434)
        if not new_img.shutter_speed and "EXIF ExposureTime" in raw:
            new_img.shutter_speed = raw["EXIF ExposureTime"]
            
        # ISO (34855)
        if not new_img.iso and "EXIF ISOSpeedRatings" in raw:
            try:
                new_img.iso = int(raw["EXIF ISOSpeedRatings"])
            except Exception: pass
            
        # Focal Length (37386)
        if not new_img.focal_length and "EXIF FocalLength" in raw:
            try:
                val = raw["EXIF FocalLength"]
                if "/" in val:
                    n, d = map(float, val.split("/"))
                    new_img.focal_length = round(n/d, 1)
                else:
                    new_img.focal_length = float(val)
            except Exception: pass
            
        # Lens Model (42036)
        if not new_img.lens_model and "EXIF LensModel" in raw:
            new_img.lens_model = raw["EXIF LensModel"]

    db.add(new_img)
    db.flush()

    # Load XMP tags if present
    await _load_xmp_for_image(db, new_img)



async def _load_xmp_for_image(db: Session, img_record: Image, xmp_base_path: str | None = None):
    """
    Check for an XMP sidecar on the NAS and load its tags/description into DB/ES.
    xmp_base_path: use this path instead of img_record.file_path to locate the XMP
                   (e.g. when A-EYE creates a renamed copy alongside the original).
    """
    base = xmp_base_path or img_record.file_path
    parts = base.split("/", 1)
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
            tag_names = [t.strip().lower() for t in xmp_meta["tags"] if t.strip()]
            staged_tags: set[str] = set()  # prevent duplicates within this XMP file
            for tag_name in tag_names:
                if tag_name in staged_tags:
                    continue
                staged_tags.add(tag_name)

                # Get or create tag
                tag = db.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.add(tag)
                    db.flush()  # get tag.id before checking link

                # Check if link already exists in DB
                if tag.id:
                    exists = db.query(ImageTag).filter(
                        ImageTag.image_id == img_record.id,
                        ImageTag.tag_id == tag.id
                    ).first()
                    if not exists:
                        db.add(ImageTag(image_id=img_record.id, tag_id=tag.id))

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

                if thumb_missing:
                    parts = img_record.file_path.split("/", 1)
                    share = parts[0]
                    rel_path = parts[1] if len(parts) > 1 else ""
                    data = await asyncio.to_thread(read_file_bytes, share, rel_path)
                    from PIL import Image as PILImage
                    img_pil = PILImage.open(BytesIO(data))
                    new_thumb = await asyncio.to_thread(generate_thumbnail, img_pil)
                    img_record.thumbnail_path = new_thumb
                    print(f"[Resync] Regenerated missing thumbnail for {img_record.filename}")
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


async def run_xmp_resync() -> int:
    """Re-read XMP sidecars for all images that currently have no tags."""
    global _current_job_id, _stop_requested
    db = SessionLocal()
    try:
        job = ScanJob(status="running", started_at=datetime.utcnow())
        db.add(job)
        db.commit()
        db.refresh(job)
        _current_job_id = job.id

        images = db.query(Image).filter(~Image.tags.any(), Image.is_video == False).all()
        total = len(images)
        job.phase1_total = total
        job.total_images = total
        db.commit()

        print(f"[XMP Resync] Re-reading XMP sidecars for {total} untagged images...")
        done = 0
        for img_record in images:
            if _stop_requested:
                break
            try:
                await _load_xmp_for_image(db, img_record)
            except Exception as e:
                print(f"[XMP Resync] Error for {img_record.file_path}: {e}")

            done += 1
            job.phase1_done = done
            if done % 100 == 0 or done == total:
                db.commit()
                print(f"[XMP Resync] Progress: {done}/{total}")

        job.status = "stopped" if _stop_requested else "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[XMP Resync] Complete: {done}/{total} images processed.")
        return job.id
    except Exception as e:
        if 'job' in locals():
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        print(f"[XMP Resync] Failed: {e}")
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
