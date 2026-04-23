import subprocess

import psutil
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from fastapi import Query as QueryParam
from database import get_db
from models import Image, Tag, ImageTag, Category, ImageCategory
from schemas import StatsOut

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _read_sysfs(path: str, divisor: float = 1.0) -> float | None:
    try:
        return float(open(path).read().strip()) / divisor
    except Exception:
        return None


@router.get("/hardware")
def get_hardware_stats():
    """Live CPU + GPU utilisation, temperature and memory stats."""

    # ── CPU ──────────────────────────────────────────────────────────────────
    cpu_pct = psutil.cpu_percent(interval=0.2)
    cpu_freq = psutil.cpu_freq()
    vm = psutil.virtual_memory()

    # AMD k10temp — hwmon3/temp1 is Tdie
    cpu_temp = _read_sysfs("/sys/class/hwmon/hwmon3/temp1_input", 1000)

    # ── AMD iGPU (card1 / hwmon2) ────────────────────────────────────────────
    igpu_util   = _read_sysfs("/sys/class/drm/card1/device/gpu_busy_percent")
    igpu_temp   = _read_sysfs("/sys/class/hwmon/hwmon2/temp1_input", 1000)
    igpu_vram_used  = _read_sysfs("/sys/class/drm/card1/device/mem_info_vram_used")
    igpu_vram_total = _read_sysfs("/sys/class/drm/card1/device/mem_info_vram_total")
    igpu_freq   = _read_sysfs("/sys/class/hwmon/hwmon2/freq1_input", 1_000_000)  # Hz → MHz

    # ── AMD iGPU name (from lspci via PCI slot in uevent) ────────────────────
    igpu_name = "Radeon Graphics"
    try:
        for line in open("/sys/class/drm/card1/device/uevent").read().splitlines():
            if line.startswith("PCI_SLOT_NAME="):
                pci_slot = line.split("=", 1)[1].strip()
                out = subprocess.check_output(["lspci", "-s", pci_slot], timeout=3).decode()
                # "c7:00.0 Display controller: ... [Radeon 8060S Graphics]"
                if "[" in out and "]" in out:
                    import re
                    m = re.search(r'\[([^\]]+(?:Radeon|AMD)[^\]]*)\]', out)
                    if m:
                        igpu_name = m.group(1).split(" / ")[0]
                break
    except Exception:
        pass

    # ── NVIDIA GPU (nvidia-smi) ───────────────────────────────────────────────
    nvidia = {"name": "NVIDIA GPU", "util": None, "mem_util": None, "temp": None, "vram_used": None, "vram_total": None}
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,utilization.memory,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            timeout=3,
        ).decode().strip()
        parts = [p.strip() for p in out.split(",")]
        if len(parts) == 6:
            nvidia = {
                "name":     parts[0],
                "util":     float(parts[1]),
                "mem_util": float(parts[2]),
                "temp":     float(parts[3]),
                "vram_used":  float(parts[4]),   # MiB
                "vram_total": float(parts[5]),   # MiB
            }
    except Exception:
        pass

    return {
        "cpu": {
            "usage_pct":   round(cpu_pct, 1),
            "temp_c":      round(cpu_temp, 1) if cpu_temp is not None else None,
            "freq_mhz":    round(cpu_freq.current, 0) if cpu_freq else None,
            "ram_used_gb": round(vm.used / 1024**3, 2),
            "ram_total_gb": round(vm.total / 1024**3, 2),
            "ram_pct":     round(vm.percent, 1),
        },
        "igpu": {
            "name":        igpu_name,
            "usage_pct":   igpu_util,
            "temp_c":      round(igpu_temp, 1) if igpu_temp is not None else None,
            "vram_used_mb":  round(igpu_vram_used / 1024**2, 0) if igpu_vram_used else None,
            "vram_total_mb": round(igpu_vram_total / 1024**2, 0) if igpu_vram_total else None,
            "freq_mhz":    round(igpu_freq, 0) if igpu_freq else None,
        },
        "gpu": {
            "name":        nvidia["name"],
            "usage_pct":   nvidia["util"],
            "mem_usage_pct": nvidia["mem_util"],
            "temp_c":      nvidia["temp"],
            "vram_used_mb":  nvidia["vram_used"],
            "vram_total_mb": nvidia["vram_total"],
        },
    }


@router.get("", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    total_images = db.query(func.count(Image.id)).scalar() or 0
    analyzed_images = db.query(func.count(Image.id)).filter(Image.analyzed == True).scalar() or 0
    total_tags = db.query(func.count(Tag.id)).scalar() or 0
    total_categories = db.query(func.count(Category.id)).scalar() or 0

    # Images by folder
    folder_counts = (
        db.query(Image.source_folder, func.count(Image.id))
        .group_by(Image.source_folder)
        .all()
    )
    images_by_folder = {folder: count for folder, count in folder_counts}

    # Top tags
    top_tags_raw = (
        db.query(Tag.name, func.count(ImageTag.image_id).label("count"))
        .join(ImageTag)
        .group_by(Tag.id)
        .order_by(func.count(ImageTag.image_id).desc())
        .limit(20)
        .all()
    )
    top_tags = [{"name": name, "count": count} for name, count in top_tags_raw]

    # Images by category
    cat_counts = (
        db.query(Category.name, func.count(ImageCategory.image_id).label("count"))
        .join(ImageCategory)
        .group_by(Category.id)
        .order_by(func.count(ImageCategory.image_id).desc())
        .all()
    )
    images_by_category = [{"name": name, "count": count} for name, count in cat_counts]

    phash_count = db.query(func.count(Image.id)).filter(Image.perceptual_hash.isnot(None)).scalar() or 0

    # Count duplicate groups using phash if available, else 0 (fast — just counts rows with same hash prefix)
    dup_count = 0
    if phash_count > 0:
        dup_count = (
            db.query(Image.perceptual_hash)
            .filter(Image.perceptual_hash.isnot(None))
            .group_by(Image.perceptual_hash)
            .having(func.count(Image.id) > 1)
            .count()
        )

    return StatsOut(
        total_images=total_images,
        analyzed_images=analyzed_images,
        total_tags=total_tags,
        total_categories=total_categories,
        images_by_folder=images_by_folder,
        top_tags=top_tags,
        images_by_category=images_by_category,
        phash_count=phash_count,
        duplicate_groups=dup_count,
    )


@router.get("/locations")
def get_locations(db: Session = Depends(get_db)):
    """Return location names with image counts, sorted by count descending."""
    rows = (
        db.query(Image.location_name, func.count(Image.id).label("count"))
        .filter(Image.location_name.isnot(None), Image.location_name != "")
        .group_by(Image.location_name)
        .order_by(func.count(Image.id).desc())
        .limit(100)
        .all()
    )
    return [{"name": r[0], "count": r[1]} for r in rows]


@router.get("/cameras")
def get_cameras(db: Session = Depends(get_db)):
    """Return camera models with image counts, sorted by count descending."""
    rows = (
        db.query(Image.camera_model, func.count(Image.id).label("count"))
        .filter(Image.camera_model.isnot(None), Image.camera_model != "")
        .group_by(Image.camera_model)
        .order_by(func.count(Image.id).desc())
        .limit(50)
        .all()
    )
    return [{"name": r[0], "count": r[1]} for r in rows]


@router.get("/quality")
def get_quality_summary(db: Session = Depends(get_db)):
    """Return counts of images with each quality issue."""
    from sqlalchemy import text
    blur = db.execute(text(
        "SELECT COUNT(*) FROM images WHERE quality_flags LIKE '%\"blur\": true%'"
    )).scalar() or 0
    overexposed = db.execute(text(
        "SELECT COUNT(*) FROM images WHERE quality_flags LIKE '%\"overexposed\": true%'"
    )).scalar() or 0
    underexposed = db.execute(text(
        "SELECT COUNT(*) FROM images WHERE quality_flags LIKE '%\"underexposed\": true%'"
    )).scalar() or 0
    return {"blur": blur, "overexposed": overexposed, "underexposed": underexposed}


@router.get("/folders")
def get_folders(db: Session = Depends(get_db)):
    """Get folder breakdown (including subfolders) with counts and sample image."""
    from sqlalchemy import text
    
    # Extract everything before the last slash
    sql = text("""
        SELECT 
            SUBSTRING(file_path, 1, LENGTH(file_path) - LOCATE('/', REVERSE(file_path))) as folder_path,
            COUNT(*) as total,
            SUM(CASE WHEN analyzed = 1 THEN 1 ELSE 0 END) as analyzed_count,
            MIN(id) as sample_image_id
        FROM images
        GROUP BY folder_path
        ORDER BY folder_path ASC
    """)
    
    results = db.execute(sql).fetchall()
    
    return [
        {
            "folder": r.folder_path,
            "total": r.total,
            "analyzed": int(r.analyzed_count or 0),
            "sample_image_id": r.sample_image_id,
        }
        for r in results if r.folder_path
    ]
