from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Category, ImageCategory
from schemas import CategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    results = (
        db.query(Category, func.count(ImageCategory.image_id).label("image_count"))
        .outerjoin(ImageCategory)
        .group_by(Category.id)
        .order_by(func.count(ImageCategory.image_id).desc())
        .all()
    )
    return [
        CategoryOut(id=cat.id, name=cat.name, parent_id=cat.parent_id, image_count=count)
        for cat, count in results
    ]
