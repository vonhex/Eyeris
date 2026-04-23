from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Tag, ImageTag
from schemas import TagOut

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
    query = db.query(Tag, func.count(ImageTag.image_id).label("image_count")).outerjoin(ImageTag)

    results = (
        query
        .group_by(Tag.id)
        .order_by(func.count(ImageTag.image_id).desc())
        .all()
    )
    return [
        TagOut(id=tag.id, name=tag.name, image_count=count)
        for tag, count in results
    ]
