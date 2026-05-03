import os

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from fastapi import Query as QueryParam
from database import get_db
from models import Image, Tag, ImageTag, Category, ImageCategory
from schemas import StatsOut

router = APIRouter(prefix="/api/stats", tags=["stats"])





@router.get("", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    total_videos = db.query(func.count(Image.id)).filter(Image.is_video == True).scalar() or 0
    total_images = (db.query(func.count(Image.id)).scalar() or 0) - total_videos
    # "Has AI content" = has a description OR at least one tag
    tagged_images = db.query(func.count(Image.id)).filter(Image.tags.any()).scalar() or 0
    described_images = (
        db.query(func.count(Image.id))
        .filter(Image.ai_description.isnot(None), Image.ai_description != "")
        .scalar() or 0
    )
    analyzed_images = db.query(func.count(Image.id)).filter(
        (Image.ai_description.isnot(None) & (Image.ai_description != "")) | Image.tags.any()
    ).scalar() or 0
    total_tags = db.query(func.count(Tag.id)).scalar() or 0
    total_categories = db.query(func.count(Category.id)).scalar() or 0

    folder_counts = (
        db.query(Image.source_folder, func.count(Image.id))
        .filter(Image.is_video == False)
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
    untagged_images = db.query(func.count(Image.id)).filter(~Image.tags.any(), Image.is_video == False).scalar() or 0
    untagged_videos = db.query(func.count(Image.id)).filter(~Image.tags.any(), Image.is_video == True).scalar() or 0

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
        total_videos=total_videos,
        analyzed_images=analyzed_images,
        tagged_images=tagged_images,
        described_images=described_images,
        total_tags=total_tags,
        total_categories=total_categories,
        images_by_folder=images_by_folder,
        top_tags=top_tags,
        images_by_category=images_by_category,
        phash_count=phash_count,
        duplicate_groups=dup_count,
        untagged_images=untagged_images,
        untagged_videos=untagged_videos,
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
    rows = db.query(Image.file_path, Image.analyzed, Image.id, Image.is_video).all()

    folders_map = {}
    for fp, analyzed, img_id, is_vid in rows:
        folder_path = os.path.dirname(fp)
        if not folder_path:
            continue

        if folder_path not in folders_map:
            folders_map[folder_path] = {
                "folder": folder_path,
                "total": 0,
                "analyzed": 0,
                "sample_image_id": None,
            }

        if not is_vid:
            folders_map[folder_path]["total"] += 1
            if analyzed:
                folders_map[folder_path]["analyzed"] += 1
            # Use the first non-video image as the folder thumbnail
            if folders_map[folder_path]["sample_image_id"] is None:
                folders_map[folder_path]["sample_image_id"] = img_id

    # Exclude folders that contain only videos (no images)
    image_folders = [f for f in folders_map.values() if f["total"] > 0]
    return sorted(image_folders, key=lambda x: x["folder"])
