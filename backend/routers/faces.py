import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Face, Image

router = APIRouter(prefix="/api/faces", tags=["faces"])


@router.get("")
def list_faces(
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=200),
    person: str | None = None,
    db: Session = Depends(get_db),
):
    """List all faces, optionally filtered by person name."""
    query = db.query(Face).join(Face.image)
    if person:
        query = query.filter(Face.person_name == person)

    total = query.count()
    faces = (
        query.order_by(Face.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "faces": [
            {
                "id": f.id,
                "image_id": f.image_id,
                "person_name": f.person_name,
                "description": f.description,
                "estimated_age": f.estimated_age,
                "gender": f.gender,
                "position": f.position,
                "image_filename": f.image.filename if f.image else None,
            }
            for f in faces
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{face_id}/crop")
def get_face_crop(face_id: int, db: Session = Depends(get_db)):
    """Serve the face-crop thumbnail for a given face."""
    face = db.query(Face).filter(Face.id == face_id).first()
    if not face or not face.crop_path:
        raise HTTPException(status_code=404, detail="Crop not found")
    full = os.path.join(settings.THUMBNAIL_DIR, face.crop_path)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="Crop file missing")
    return FileResponse(full, media_type="image/jpeg")


@router.put("/{face_id}/name")
def update_face_name(face_id: int, body: dict, db: Session = Depends(get_db)):
    """Assign a person name to a single face."""
    face = db.query(Face).filter(Face.id == face_id).first()
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")
    face.person_name = (body.get("name") or "").strip() or None
    db.commit()
    return {"status": "ok"}
