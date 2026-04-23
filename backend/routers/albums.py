from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import Image, ImageTag, ImageCategory, Tag
from schemas import AlbumOut, ImageListResponse, ImageSummary, ImageTagOut, ImageCategoryOut

router = APIRouter(prefix="/api/albums", tags=["albums"])
@router.get("", response_model=list[AlbumOut])
def list_albums(db: Session = Depends(get_db)):
    """List all albums (from metadata) and prominent tags (as virtual albums)."""
    # 1. Get explicit albums from metadata
    album_query = db.query(
        Image.album.label("name"),
        func.count(Image.id).label("image_count"),
        func.min(Image.id).label("first_image_id"),
    ).filter(Image.album.isnot(None), Image.album != "").group_by(Image.album)

    results = album_query.all()

    # Convert to list of dicts for modification
    albums = [
        {"name": r.name, "image_count": r.image_count, "first_image_id": r.first_image_id, "type": "metadata"}
        for r in results
    ]

    # 2. Get prominent tags to treat as "Virtual Albums"
    # We look for tags that have at least 10 images and aren't tiny generic ones
    tag_query = db.query(
        Tag.name,
        func.count(ImageTag.image_id).label("image_count"),
        func.min(ImageTag.image_id).label("first_image_id"),
    ).join(ImageTag).group_by(Tag.id).having(func.count(ImageTag.image_id) >= 10)

    tag_results = tag_query.all()

    # Avoid duplicating existing album names
    existing_names = {a["name"].lower() for a in albums}

    for tr in tag_results:
        if tr.name.lower() not in existing_names:
            albums.append({
                "name": tr.name,
                "image_count": tr.image_count,
                "first_image_id": tr.first_image_id,
                "type": "tag"
            })

    # Sort by count descending
    albums.sort(key=lambda x: x["image_count"], reverse=True)

    return [
        AlbumOut(
            album=a["name"],
            image_count=a["image_count"],
            first_image_id=a["first_image_id"]
        )
        for a in albums
    ]

@router.get("/{album_name}", response_model=ImageListResponse)
def get_album_images(
    album_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get all images in a specific album (matching metadata or tag)."""
    # 1. Build the base query for both metadata album or tag match
    base_q = db.query(Image.id).outerjoin(Image.tags).outerjoin(ImageTag.tag).filter(
        (Image.album == album_name) | (Tag.name == album_name)
    ).distinct()

    total = db.query(func.count()).select_from(base_q.subquery()).scalar() or 0

    image_ids = (
        base_q
        .order_by(
            case((Image.date_taken.is_(None), 1), else_=0),
            Image.date_taken.desc(),
            Image.created_at.desc(),
        )
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
        )
        .filter(Image.id.in_(ids))
        .all()
    )

    id_order = {id_: idx for idx, id_ in enumerate(ids)}
    images.sort(key=lambda img: id_order.get(img.id, 999999))

    return ImageListResponse(
        images=[
            ImageSummary(
                id=img.id,
                filename=img.filename,
                source_folder=img.source_folder,
                width=img.width,
                height=img.height,
                analyzed=img.analyzed,
                ai_description=img.ai_description,
                album=img.album,
                date_taken=img.date_taken,
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
            )
            for img in images
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
