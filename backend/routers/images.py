import asyncio
import os
from datetime import datetime
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload, selectinload

from database import get_db
from models import Image, Tag, ImageTag, Category, ImageCategory, Face, ImageTagBlock
from schemas import (
    ImageSummary, ImageDetail, ImageListResponse, ImageTagOut, ImageCategoryOut,
    FaceOut, TagUpdateRequest, CategoryUpdateRequest,
)
from services.search_service import index_image as es_index_image
from services.llm_search import expand_query, search_images_db as llm_search_db
from config import settings

router = APIRouter(prefix="/api/images", tags=["images"])


def _image_to_summary(img: Image) -> ImageSummary:
    return ImageSummary(
        id=img.id,
        filename=img.filename,
        source_folder=img.source_folder,
        width=img.width,
        height=img.height,
        analyzed=img.analyzed,
        thumbnail_path=img.thumbnail_path,
        ai_description=img.ai_description,
        album=img.album,
        favorite=img.favorite,
        date_taken=img.date_taken,
        location_name=img.location_name,
        camera_model=img.camera_model,
        quality_flags=img.quality_flags,
        is_video=img.is_video,
        created_at=img.created_at,
        tags=[
            ImageTagOut(tag_id=it.tag.id, tag_name=it.tag.name)
            for it in img.tags
        ],
        categories=[
            ImageCategoryOut(
                category_id=ic.category.id, category_name=ic.category.name
            )
            for ic in img.categories
        ],
        faces=[
            FaceOut(id=f.id, person_name=f.person_name, description=f.description,
                    estimated_age=f.estimated_age, gender=f.gender, position=f.position)
            for f in img.faces
        ],
    )


@router.get("", response_model=ImageListResponse)
def list_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=200),
    folder: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    search: str | None = None,
    analyzed_only: bool = False,
    cluster_id: int | None = None,
    favorite: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    location: str | None = None,
    camera: str | None = None,
    quality_issue: str | None = None,  # "blur" | "overexposed" | "underexposed" | "any"
    has_gps: bool | None = None,
    untagged: bool | None = None,
    is_video: bool = Query(False),
    sort: str | None = Query(None, pattern="^(date_taken|date_added|filename)_(asc|desc)$|^random$"),
    db: Session = Depends(get_db),
):
    # LLM-powered natural language search
    if search:
        try:
            expanded = asyncio.run(expand_query(search))
            print(f"[Search] '{search}' → expanded: {expanded}")
            result = llm_search_db(
                db=db, query=search, expanded=expanded,
                folder=folder, tag=tag, category=category,
                page=page, page_size=page_size,
                analyzed_only=analyzed_only,
                favorite=favorite,
                is_video=is_video,
            )
            if result["ids"]:
                images = (
                    db.query(Image)
                    .options(
                        joinedload(Image.tags).joinedload(ImageTag.tag),
                        joinedload(Image.categories).joinedload(ImageCategory.category),
                    )
                    .filter(Image.id.in_(result["ids"]))
                    .all()
                )
                id_order = {id_: idx for idx, id_ in enumerate(result["ids"])}
                images.sort(key=lambda img: id_order.get(img.id, 999999))
                return ImageListResponse(
                    images=[_image_to_summary(img) for img in images],
                    total=result["total"],
                    page=page,
                    page_size=page_size,
                )
            return ImageListResponse(images=[], total=0, page=page, page_size=page_size)
        except Exception as e:
            print(f"[Search] LLM search error, falling back to SQL LIKE: {e}")

    id_query = db.query(Image.id)

    if folder:
        if "/" in folder:
            # It's a subfolder path, match by prefix
            id_query = id_query.filter(Image.file_path.like(f"{folder}/%"))
        else:
            # It's a root share name
            id_query = id_query.filter(Image.source_folder == folder)
    if analyzed_only:
        id_query = id_query.filter(Image.analyzed == True)
    if favorite is not None:
        id_query = id_query.filter(Image.favorite == favorite)
    
    id_query = id_query.filter(Image.is_video == is_video)

    if date_from:
        id_query = id_query.filter(Image.date_taken >= date_from)
    if date_to:
        id_query = id_query.filter(Image.date_taken <= date_to)
    if search:
        id_query = id_query.outerjoin(Image.tags).outerjoin(ImageTag.tag).filter(
            (Image.filename.ilike(f"%{search}%")) |
            (Image.ai_description.ilike(f"%{search}%")) |
            (Tag.name.ilike(f"%{search}%"))
        )
    if tag:
        id_query = id_query.join(Image.tags).join(ImageTag.tag).filter(Tag.name == tag.lower())
    if category:
        id_query = id_query.join(Image.categories).join(ImageCategory.category).filter(Category.name == category)
    if cluster_id is not None:
        person_img_ids = db.query(Face.image_id).filter(Face.cluster_id == cluster_id).subquery()
        id_query = id_query.filter(Image.id.in_(db.query(person_img_ids.c.image_id)))
    if location:
        id_query = id_query.filter(Image.location_name.ilike(f"%{location}%"))
    if camera:
        id_query = id_query.filter(Image.camera_model.ilike(f"%{camera}%"))
    if has_gps is True:
        id_query = id_query.filter(Image.gps_lat.isnot(None))
    elif has_gps is False:
        id_query = id_query.filter(Image.gps_lat.is_(None))
    if quality_issue:
        from sqlalchemy import text as _text
        if quality_issue == "any":
            id_query = id_query.filter(
                Image.quality_flags.ilike('%"blur": true%') |
                Image.quality_flags.ilike('%"overexposed": true%') |
                Image.quality_flags.ilike('%"underexposed": true%')
            )
        elif quality_issue in ("blur", "overexposed", "underexposed"):
            id_query = id_query.filter(
                Image.quality_flags.ilike(f'%"{quality_issue}": true%')
            )
    if untagged:
        id_query = id_query.filter(~Image.tags.any())

    total = id_query.distinct().count()

    if sort == "random":
        sort_field, sort_dir = "random", None
    else:
        sort_field, sort_dir = (sort.rsplit("_", 1) if sort else (None, None))
    if sort_field == "random":
        ordering = [func.rand()]
    elif sort_field == "date_added":
        col = Image.created_at
        order = col.asc() if sort_dir == "asc" else col.desc()
        ordering = [order]
    elif sort_field == "filename":
        col = Image.filename
        order = col.asc() if sort_dir == "asc" else col.desc()
        ordering = [order]
    elif sort_field == "date_taken":
        col = Image.date_taken
        order = col.asc() if sort_dir == "asc" else col.desc()
        ordering = [case((col.is_(None), 1), else_=0), order]
    else:
        ordering = [
            case((Image.date_taken.is_(None), 1), else_=0),
            Image.date_taken.desc(),
            Image.created_at.desc(),
        ]

    image_ids = (
        id_query.distinct()
        .order_by(*ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    ids = [row[0] for row in image_ids]

    if not ids:
        return ImageListResponse(images=[], total=total, page=page, page_size=page_size)

    images = (
        db.query(Image)
        .options(
            selectinload(Image.tags).joinedload(ImageTag.tag),
            selectinload(Image.categories).joinedload(ImageCategory.category),
            selectinload(Image.faces),
        )
        .filter(Image.id.in_(ids))
        .all()
    )

    id_order = {id_: idx for idx, id_ in enumerate(ids)}
    images.sort(key=lambda img: id_order.get(img.id, 999999))

    return ImageListResponse(
        images=[_image_to_summary(img) for img in images],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/ids")
def list_image_ids(
    folder: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    search: str | None = None,
    cluster_id: int | None = None,
    favorite: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    untagged: bool | None = None,
    is_video: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Return all image IDs matching the current filters (no pagination). Used for Select All."""
    q = db.query(Image.id)
    if folder:
        if "/" in folder:
            q = q.filter(Image.file_path.like(f"{folder}/%"))
        else:
            q = q.filter(Image.source_folder == folder)
    if favorite is not None:
        q = q.filter(Image.favorite == favorite)
    
    q = q.filter(Image.is_video == is_video)

    if date_from:
        q = q.filter(Image.date_taken >= date_from)
    if date_to:
        q = q.filter(Image.date_taken <= date_to)
    if search:
        q = q.outerjoin(Image.tags).outerjoin(ImageTag.tag).filter(
            (Image.filename.ilike(f"%{search}%")) |
            (Image.ai_description.ilike(f"%{search}%")) |
            (Tag.name.ilike(f"%{search}%"))
        )
    if tag:
        q = q.join(Image.tags).join(ImageTag.tag).filter(Tag.name == tag.lower())
    if category:
        q = q.join(Image.categories).join(ImageCategory.category).filter(Category.name == category)
    if cluster_id is not None:
        person_img_ids = db.query(Face.image_id).filter(Face.cluster_id == cluster_id).subquery()
        q = q.filter(Image.id.in_(db.query(person_img_ids.c.image_id)))
    if untagged:
        q = q.filter(~Image.tags.any())
    ids = [row[0] for row in q.distinct().all()]
    return {"ids": ids}


@router.get("/duplicates")
def get_duplicates(threshold: int = 8, db: Session = Depends(get_db)):
    """
    Find visually similar images using perceptual hashing.
    threshold: max Hamming distance to consider a duplicate (default 8, range 0-20).
    Falls back to exact hash matching if no perceptual hashes exist yet.
    """
    import numpy as np

    rows = (
        db.query(Image.id, Image.perceptual_hash)
        .filter(Image.perceptual_hash.isnot(None))
        .all()
    )

    if not rows:
        # Fallback: exact file hash duplicates
        dup_hashes = (
            db.query(Image.file_hash, func.count(Image.id).label("cnt"))
            .filter(Image.file_hash.isnot(None))
            .group_by(Image.file_hash)
            .having(func.count(Image.id) > 1)
            .order_by(func.count(Image.id).desc())
            .all()
        )
        if not dup_hashes:
            return {"groups": [], "total_groups": 0, "mode": "hash"}
        groups = []
        for row in dup_hashes:
            imgs = (
                db.query(Image)
                .filter(Image.file_hash == row.file_hash)
                .order_by(Image.file_size.desc())
                .all()
            )
            groups.append({"hash": row.file_hash, "images": [_image_to_summary(i) for i in imgs]})
        return {"groups": groups, "total_groups": len(groups), "mode": "hash"}

    # Convert hex pHash strings to uint64 integers for fast numpy comparison
    ids = np.array([r.id for r in rows], dtype=np.int32)
    try:
        hashes = np.array([int(r.perceptual_hash, 16) for r in rows], dtype=np.uint64)
    except Exception:
        return {"groups": [], "total_groups": 0, "mode": "phash"}

    # Lookup table for fast popcount (Hamming weight) of each byte
    popcount_table = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)

    # Find duplicate pairs using chunked pairwise Hamming distance
    n = len(hashes)
    chunk = 512
    uf_parent = list(range(n))

    def find(x):
        while uf_parent[x] != x:
            uf_parent[x] = uf_parent[uf_parent[x]]
            x = uf_parent[x]
        return x

    def union(a, b):
        uf_parent[find(a)] = find(b)

    for i in range(0, n, chunk):
        blk = hashes[i:i + chunk]
        xor = (blk[:, None] ^ hashes[None, :]).view(np.uint8).reshape(len(blk), n, 8)
        dists = popcount_table[xor].sum(axis=2)  # (chunk, n) Hamming distances
        pairs = np.argwhere(dists <= threshold)
        for ci, j in pairs:
            gi = i + ci
            if gi < j:
                union(gi, j)

    # Group by union-find root
    from collections import defaultdict
    groups_map = defaultdict(list)
    for idx in range(n):
        groups_map[find(idx)].append(idx)

    dup_groups = {root: idxs for root, idxs in groups_map.items() if len(idxs) > 1}
    if not dup_groups:
        return {"groups": [], "total_groups": 0, "mode": "phash"}

    # Load image records for duplicate groups
    all_dup_ids = [ids[idx] for idxs in dup_groups.values() for idx in idxs]
    img_map = {
        img.id: img for img in
        db.query(Image)
        .options(
            selectinload(Image.tags).joinedload(ImageTag.tag),
            selectinload(Image.categories).joinedload(ImageCategory.category),
            selectinload(Image.faces),
        )
        .filter(Image.id.in_(all_dup_ids.copy()))
        .all()
    }

    groups = []
    for root, idxs in sorted(dup_groups.items(), key=lambda x: -len(x[1])):
        group_imgs = sorted(
            [img_map[ids[idx]] for idx in idxs if ids[idx] in img_map],
            key=lambda img: (-(img.file_size or 0)),
        )
        if len(group_imgs) > 1:
            groups.append({
                "hash": rows[root].perceptual_hash,
                "images": [_image_to_summary(img) for img in group_imgs],
            })

    return {"groups": groups, "total_groups": len(groups), "mode": "phash"}


@router.get("/{image_id}", response_model=ImageDetail)
def get_image(image_id: int, db: Session = Depends(get_db)):
    img = (
        db.query(Image)
        .options(
            selectinload(Image.tags).joinedload(ImageTag.tag),
            selectinload(Image.categories).joinedload(ImageCategory.category),
            selectinload(Image.faces),
        )
        .filter(Image.id == image_id)
        .first()
    )
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    return ImageDetail(
        id=img.id,
        file_path=img.file_path,
        filename=img.filename,
        source_folder=img.source_folder,
        file_size=img.file_size,
        file_hash=img.file_hash,
        width=img.width,
        height=img.height,
        orientation_corrected=img.orientation_corrected,
        analyzed=img.analyzed,
        thumbnail_path=img.thumbnail_path,
        ai_description=img.ai_description,
        album=img.album,
        favorite=img.favorite,
        date_taken=img.date_taken,
        location_name=img.location_name,
        camera_model=img.camera_model,
        gps_lat=img.gps_lat,
        gps_lon=img.gps_lon,
        quality_flags=img.quality_flags,
        is_video=img.is_video,
        lens_model=img.lens_model,
        aperture=img.aperture,
        shutter_speed=img.shutter_speed,
        iso=img.iso,
        focal_length=img.focal_length,
        created_at=img.created_at,
        updated_at=img.updated_at,
        tags=[
            ImageTagOut(tag_id=it.tag.id, tag_name=it.tag.name)
            for it in img.tags
        ],
        categories=[
            ImageCategoryOut(
                category_id=ic.category.id, category_name=ic.category.name
            )
            for ic in img.categories
        ],
        faces=[
            FaceOut(id=f.id, person_name=f.person_name, description=f.description,
                    estimated_age=f.estimated_age, gender=f.gender, position=f.position)
            for f in img.faces
        ],
    )


@router.get("/{image_id}/thumbnail")
def get_thumbnail(image_id: int):
    from database import SessionLocal
    db = SessionLocal()
    try:
        img = db.query(Image).filter(Image.id == image_id).first()
        if not img or not img.thumbnail_path:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        path = os.path.join(settings.THUMBNAIL_DIR, img.thumbnail_path)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Thumbnail file missing")
    finally:
        db.close()

    return FileResponse(path, media_type="image/jpeg")


@router.get("/{image_id}/file")
async def get_full_image(image_id: int):
    # Use a short-lived session to fetch the image and close it immediately
    # before returning FileResponse, to avoid holding connections open during streaming.
    from database import SessionLocal
    db = SessionLocal()
    try:
        img = db.query(Image).filter(Image.id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")
        file_path = img.file_path
        filename = img.filename
    finally:
        db.close()

    from services.smb_service import _local_path
    parts = file_path.split("/", 1)
    share = parts[0]
    rel_path = parts[1] if len(parts) > 1 else ""
    local_path = _local_path(share, rel_path)

    if not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="File not found on NAS")

    ext = filename.rsplit(".", 1)[-1].lower()
    media_types = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
        "tiff": "image/tiff", "tif": "image/tiff", "heic": "image/heic",
        "mp4": "video/mp4", "mkv": "video/x-matroska", "mov": "video/quicktime",
        "avi": "video/x-msvideo", "wmv": "video/x-ms-wmv", "webm": "video/webm",
        "m4v": "video/x-m4v"
    }
    content_type = media_types.get(ext, "application/octet-stream")

    # Only attempt orientation correction for certain image types
    if ext in ("jpg", "jpeg", "png", "webp"):
        from fastapi.responses import Response
        from PIL import Image as PILImage
        from services.image_service import correct_orientation
        from io import BytesIO

        try:
            with open(local_path, "rb") as f:
                data = f.read()
            img_pil = PILImage.open(BytesIO(data))
            img_pil, corrected = correct_orientation(img_pil)
            if corrected:
                buf = BytesIO()
                fmt = "JPEG" if ext in ("jpg", "jpeg") else ext.upper()
                if img_pil.mode in ("RGBA", "P", "LA") and fmt == "JPEG":
                    img_pil = img_pil.convert("RGB")
                img_pil.save(buf, format=fmt, quality=95)
                return Response(content=buf.getvalue(), media_type=content_type)
        except Exception:
            pass

    return FileResponse(local_path, media_type=content_type)
@router.delete("/{image_id}")
async def delete_image(image_id: int, db: Session = Depends(get_db)):
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    parts = img.file_path.split("/", 1)
    share = parts[0]
    rel_path = parts[1] if len(parts) > 1 else ""

    import asyncio
    from services.smb_service import delete_file
    try:
        await asyncio.to_thread(delete_file, share, rel_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete from NAS: {e}")

    if img.thumbnail_path:
        thumb_path = os.path.join(settings.THUMBNAIL_DIR, img.thumbnail_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)

    db.query(ImageTag).filter(ImageTag.image_id == image_id).delete()
    db.query(ImageCategory).filter(ImageCategory.image_id == image_id).delete()
    db.query(Face).filter(Face.image_id == image_id).delete()
    db.delete(img)
    db.commit()

    return {"status": "ok", "message": "Image deleted"}


class BulkIdsRequest(BaseModel):
    ids: list[int]


@router.post("/bulk-download")
async def bulk_download_images(body: BulkIdsRequest, db: Session = Depends(get_db)):
    import zipfile
    import tempfile
    from services.smb_service import read_file_bytes

    images = db.query(Image).filter(Image.id.in_(body.ids)).all()
    if not images:
        raise HTTPException(status_code=404, detail="No images found")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
            seen_names = {}
            for img in images:
                parts = img.file_path.split("/", 1)
                share = parts[0]
                rel_path = parts[1] if len(parts) > 1 else ""
                try:
                    data = read_file_bytes(share, rel_path)
                except Exception:
                    continue
                name = img.filename
                if name in seen_names:
                    seen_names[name] += 1
                    base, ext = os.path.splitext(name)
                    name = f"{base}_{seen_names[name]}{ext}"
                else:
                    seen_names[name] = 0
                zf.writestr(name, data)
    except Exception as e:
        os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"Failed to create zip: {e}")

    from starlette.background import BackgroundTask
    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename="images.zip",
        background=BackgroundTask(os.unlink, tmp.name),
    )


class BulkDeleteRequest(BulkIdsRequest):
    pass


@router.post("/bulk-delete")
async def bulk_delete_images(body: BulkDeleteRequest, db: Session = Depends(get_db)):
    import asyncio
    from services.smb_service import delete_file

    deleted = 0
    errors = []

    for image_id in body.ids:
        img = db.query(Image).filter(Image.id == image_id).first()
        if not img:
            continue

        parts = img.file_path.split("/", 1)
        share = parts[0]
        rel_path = parts[1] if len(parts) > 1 else ""

        try:
            await asyncio.to_thread(delete_file, share, rel_path)
        except Exception as e:
            errors.append(f"{img.filename}: {e}")
            continue

        if img.thumbnail_path:
            thumb_path = os.path.join(settings.THUMBNAIL_DIR, img.thumbnail_path)
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

        db.query(ImageTag).filter(ImageTag.image_id == image_id).delete()
        db.query(ImageCategory).filter(ImageCategory.image_id == image_id).delete()
        db.query(Face).filter(Face.image_id == image_id).delete()
        db.delete(img)
        deleted += 1

    db.commit()
    return {"status": "ok", "deleted": deleted, "errors": errors}


class BulkTagRequest(BaseModel):
    ids: list[int]
    add: list[str] = []
    remove: list[str] = []


@router.post("/bulk-tags")
def bulk_update_tags(body: BulkTagRequest, db: Session = Depends(get_db)):
    """Add and/or remove tags from multiple images at once."""
    add_tag_objs = []
    for tag_name in body.add:
        tag_name = tag_name.strip().lower()
        if not tag_name:
            continue
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            db.flush()
        add_tag_objs.append(tag)

    remove_tag_ids = []
    for tag_name in body.remove:
        tag_name = tag_name.strip().lower()
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if tag:
            remove_tag_ids.append(tag.id)

    add_names = {t.name for t in add_tag_objs}
    remove_names = {n.strip().lower() for n in body.remove if n.strip()}

    for image_id in body.ids:
        # Block removed tags, unblock re-added ones
        for name in remove_names:
            if not db.query(ImageTagBlock).filter_by(image_id=image_id, tag_name=name).first():
                db.add(ImageTagBlock(image_id=image_id, tag_name=name))
        for name in add_names:
            db.query(ImageTagBlock).filter_by(image_id=image_id, tag_name=name).delete()

        for tag in add_tag_objs:
            exists = db.query(ImageTag).filter(
                ImageTag.image_id == image_id, ImageTag.tag_id == tag.id
            ).first()
            if not exists:
                db.add(ImageTag(image_id=image_id, tag_id=tag.id))
        if remove_tag_ids:
            db.query(ImageTag).filter(
                ImageTag.image_id == image_id,
                ImageTag.tag_id.in_(remove_tag_ids),
            ).delete(synchronize_session=False)

    db.commit()
    return {"status": "ok", "updated": len(body.ids)}


@router.put("/{image_id}/favorite")
def set_favorite(image_id: int, body: dict, db: Session = Depends(get_db)):
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    if "favorite" in body:
        img.favorite = bool(body["favorite"])
    else:
        img.favorite = not img.favorite
    db.commit()
    return {"status": "ok", "favorite": img.favorite}


@router.put("/{image_id}/tags")
def update_tags(image_id: int, body: TagUpdateRequest, db: Session = Depends(get_db)):
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    # Track which tags were explicitly removed so scanner won't re-add them
    old_tag_names = {
        it.tag.name for it in
        db.query(ImageTag).filter(ImageTag.image_id == image_id)
        .join(ImageTag.tag).all()
    }
    new_tag_names = {t.strip().lower() for t in body.tags if t.strip()}
    removed = old_tag_names - new_tag_names
    added = new_tag_names - old_tag_names

    # Block removed tags, unblock re-added ones
    for name in removed:
        if not db.query(ImageTagBlock).filter_by(image_id=image_id, tag_name=name).first():
            db.add(ImageTagBlock(image_id=image_id, tag_name=name))
    for name in added:
        db.query(ImageTagBlock).filter_by(image_id=image_id, tag_name=name).delete()

    db.query(ImageTag).filter(ImageTag.image_id == image_id).delete()

    for tag_name in new_tag_names:
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            db.flush()
        db.add(ImageTag(image_id=image_id, tag_id=tag.id))

    db.commit()
    return {"status": "ok"}


@router.put("/{image_id}/category")
def update_category(image_id: int, body: CategoryUpdateRequest, db: Session = Depends(get_db)):
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    db.query(ImageCategory).filter(ImageCategory.image_id == image_id).delete()

    cat_name = body.category.strip()
    category = db.query(Category).filter(Category.name == cat_name).first()
    if not category:
        category = Category(name=cat_name)
        db.add(category)
        db.flush()

    db.add(ImageCategory(image_id=image_id, category_id=category.id))
    db.commit()
    return {"status": "ok"}
