import glob
import os
import re
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


def _find_hwmon_by_name(driver_name: str) -> str | None:
    """Return the first hwmon path whose 'name' file matches driver_name."""
    try:
        for entry in sorted(os.listdir("/sys/class/hwmon")):
            name_file = f"/sys/class/hwmon/{entry}/name"
            try:
                if open(name_file).read().strip() == driver_name:
                    return f"/sys/class/hwmon/{entry}"
            except Exception:
                continue
    except Exception:
        pass
    return None


def _get_pci_name(pci_slot: str) -> str | None:
    try:
        out = subprocess.check_output(["lspci", "-s", pci_slot], timeout=3).decode()
        m = re.search(r'\[([^\]]+)\]', out)
        if m:
            return m.group(1).split(" / ")[0]
        # Fallback: grab text after the last colon (Intel often lacks brackets)
        parts = out.split(":", 2)
        if len(parts) == 3:
            return parts[2].strip().split("(rev")[0].strip()
    except Exception:
        pass
    return None


def _discover_drm_cards() -> list[dict]:
    """Walk /sys/class/drm/cardN entries and return one dict per GPU."""
    cards = []
    for card_path in sorted(glob.glob("/sys/class/drm/card*")):
        card_name = os.path.basename(card_path)
        # Only cardN (integer suffix) — skip renderD128, card0-DP-1, etc.
        if not re.fullmatch(r'card\d+', card_name):
            continue
        vendor_path = f"{card_path}/device/vendor"
        if not os.path.exists(vendor_path):
            continue
        try:
            vendor = open(vendor_path).read().strip().lower()
        except Exception:
            continue

        card: dict = {"card": card_name, "card_path": card_path, "vendor": vendor}

        # GPU name via lspci
        try:
            for line in open(f"{card_path}/device/uevent").read().splitlines():
                if line.startswith("PCI_SLOT_NAME="):
                    pci_slot = line.split("=", 1)[1].strip()
                    name = _get_pci_name(pci_slot)
                    if name:
                        card["name"] = name
                    break
        except Exception:
            pass

        # hwmon dir attached to this card's device
        hwmon_dirs = glob.glob(f"{card_path}/device/hwmon/hwmon*")
        if hwmon_dirs:
            card["hwmon"] = hwmon_dirs[0]

        cards.append(card)
    return cards


def _amd_gpu_stats(card: dict) -> dict:
    cp = card["card_path"]
    hwmon = card.get("hwmon", "")
    return {
        "name":          card.get("name", "AMD GPU"),
        "vendor":        "amd",
        "usage_pct":     _read_sysfs(f"{cp}/device/gpu_busy_percent"),
        "temp_c":        _read_sysfs(f"{hwmon}/temp1_input", 1000) if hwmon else None,
        "vram_used_mb":  _mb(_read_sysfs(f"{cp}/device/mem_info_vram_used")),
        "vram_total_mb": _mb(_read_sysfs(f"{cp}/device/mem_info_vram_total")),
        "freq_mhz":      _round(_read_sysfs(f"{hwmon}/freq1_input", 1_000_000)) if hwmon else None,
        "mem_usage_pct": None,
    }


def _intel_gpu_stats(card: dict) -> dict:
    cp = card["card_path"]
    hwmon = card.get("hwmon", "")
    # Utilisation: some kernels expose gpu_busy_percent for i915 too
    util = _read_sysfs(f"{cp}/device/gpu_busy_percent")
    # Frequency: gt_cur_freq_mhz lives directly on the card sysfs dir on most systems
    freq = (_read_sysfs(f"{cp}/gt_cur_freq_mhz") or
            _read_sysfs(f"{cp}/device/gt_cur_freq_mhz"))
    temp = _read_sysfs(f"{hwmon}/temp1_input", 1000) if hwmon else None
    return {
        "name":          card.get("name", "Intel GPU"),
        "vendor":        "intel",
        "usage_pct":     util,
        "temp_c":        temp,
        "vram_used_mb":  None,
        "vram_total_mb": None,
        "freq_mhz":      _round(freq),
        "mem_usage_pct": None,
    }


def _nvidia_gpus() -> list[dict]:
    """Query all NVIDIA GPUs via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,utilization.memory,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            timeout=5,
        ).decode().strip()
    except Exception:
        return []

    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 6:
            continue
        try:
            gpus.append({
                "name":          parts[0],
                "vendor":        "nvidia",
                "usage_pct":     float(parts[1]),
                "mem_usage_pct": float(parts[2]),
                "temp_c":        float(parts[3]),
                "vram_used_mb":  float(parts[4]),
                "vram_total_mb": float(parts[5]),
                "freq_mhz":      None,
            })
        except ValueError:
            continue
    return gpus


def _mb(val: float | None) -> float | None:
    return round(val / 1024 ** 2, 0) if val is not None else None


def _round(val: float | None) -> float | None:
    return round(val, 0) if val is not None else None


@router.get("/hardware")
def get_hardware_stats():
    """Live CPU + GPU utilisation, temperature and memory stats."""

    # ── CPU ──────────────────────────────────────────────────────────────────
    cpu_pct = psutil.cpu_percent(interval=0.2)
    cpu_freq = psutil.cpu_freq()
    vm = psutil.virtual_memory()

    # Discover CPU temp hwmon dynamically (k10temp=AMD, coretemp=Intel)
    cpu_temp = None
    for driver in ("k10temp", "coretemp"):
        hwmon = _find_hwmon_by_name(driver)
        if hwmon:
            cpu_temp = _read_sysfs(f"{hwmon}/temp1_input", 1000)
            if cpu_temp is not None:
                break

    # ── GPUs ─────────────────────────────────────────────────────────────────
    gpus: list[dict] = []

    # NVIDIA — nvidia-smi is the most reliable source
    gpus.extend(_nvidia_gpus())

    # AMD + Intel — discovered via DRM sysfs
    for card in _discover_drm_cards():
        vendor = card["vendor"]
        if vendor == "0x1002":      # AMD
            gpus.append(_amd_gpu_stats(card))
        elif vendor == "0x8086":    # Intel
            gpus.append(_intel_gpu_stats(card))
        # 0x10de = NVIDIA — already handled by nvidia-smi above

    return {
        "cpu": {
            "usage_pct":    round(cpu_pct, 1),
            "temp_c":       round(cpu_temp, 1) if cpu_temp is not None else None,
            "freq_mhz":     round(cpu_freq.current, 0) if cpu_freq else None,
            "ram_used_gb":  round(vm.used / 1024 ** 3, 2),
            "ram_total_gb": round(vm.total / 1024 ** 3, 2),
            "ram_pct":      round(vm.percent, 1),
        },
        "gpus": gpus,
    }


@router.get("", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    total_images = db.query(func.count(Image.id)).scalar() or 0
    analyzed_images = db.query(func.count(Image.id)).filter(Image.analyzed == True).scalar() or 0
    total_tags = db.query(func.count(Tag.id)).scalar() or 0
    total_categories = db.query(func.count(Category.id)).scalar() or 0

    folder_counts = (
        db.query(Image.source_folder, func.count(Image.id))
        .group_by(Image.source_folder)
        .all()
    )
    images_by_folder = {folder: count for folder, count in folder_counts}

    top_tags_raw = (
        db.query(Tag.name, func.count(ImageTag.image_id).label("count"))
        .join(ImageTag)
        .group_by(Tag.id)
        .order_by(func.count(ImageTag.image_id).desc())
        .limit(20)
        .all()
    )
    top_tags = [{"name": name, "count": count} for name, count in top_tags_raw]

    cat_counts = (
        db.query(Category.name, func.count(ImageCategory.image_id).label("count"))
        .join(ImageCategory)
        .group_by(Category.id)
        .order_by(func.count(ImageCategory.image_id).desc())
        .all()
    )
    images_by_category = [{"name": name, "count": count} for name, count in cat_counts]

    phash_count = db.query(func.count(Image.id)).filter(Image.perceptual_hash.isnot(None)).scalar() or 0

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
    # Fetch all paths and analyzed status to group in Python
    # (Cross-compatible way to find unique folders without complex dialect-specific SQL)
    rows = db.query(Image.file_path, Image.analyzed, Image.id).all()
    
    folders_map = {}
    for fp, analyzed, img_id in rows:
        # Extract folder part (e.g., "photos/2023/vacation/img.jpg" -> "photos/2023/vacation")
        folder_path = os.path.dirname(fp)
        if not folder_path:
            continue
            
        if folder_path not in folders_map:
            folders_map[folder_path] = {
                "folder": folder_path,
                "total": 0,
                "analyzed": 0,
                "sample_image_id": img_id,
            }
        
        folders_map[folder_path]["total"] += 1
        if analyzed:
            folders_map[folder_path]["analyzed"] += 1
            
    # Sort by folder path alphabetically
    sorted_folders = sorted(folders_map.values(), key=lambda x: x["folder"])
    return sorted_folders
