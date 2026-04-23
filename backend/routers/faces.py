import os
import json

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, exists
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Face, Image
from schemas import FaceOut

router = APIRouter(prefix="/api/faces", tags=["faces"])


# ---------------------------------------------------------------------------
# Clustering helper
# ---------------------------------------------------------------------------

def _do_cluster_faces(db: Session, threshold: float = 0.65) -> int:
    """
    Cluster faces with embeddings using cosine similarity (union-find).
    Returns the number of clusters created.
    Threshold: cosine similarity >= threshold means same person.
    """
    faces = db.query(Face).filter(Face.embedding.isnot(None), Face.ignored.is_(False)).all()
    if len(faces) < 1:
        return 0

    embs = []
    valid = []
    for f in faces:
        try:
            embs.append(json.loads(f.embedding))
            valid.append(f)
        except Exception:
            pass

    if not embs:
        return 0

    arr = np.array(embs, dtype=np.float32)
    # L2-normalise so dot product == cosine similarity
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr = arr / (norms + 1e-8)

    n = len(arr)
    parent = list(range(n))

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: int, b: int):
        parent[find(a)] = find(b)

    # Pairwise similarity — process in chunks to be memory-friendly
    chunk = 500
    for i in range(0, n, chunk):
        sims = arr[i : i + chunk] @ arr.T  # (chunk_size, n)
        for ci, row in enumerate(sims):
            gi = i + ci
            for j in range(gi + 1, n):
                if row[j] >= threshold:
                    union(gi, j)

    root_to_cid: dict[int, int] = {}
    cid = 0
    for i, face in enumerate(valid):
        root = find(i)
        if root not in root_to_cid:
            root_to_cid[root] = cid
            cid += 1
        face.cluster_id = root_to_cid[root]

    db.commit()
    return cid


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
                "cluster_id": f.cluster_id,
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


@router.get("/people")
def list_people(db: Session = Depends(get_db)):
    """
    Return face clusters for the People tab.
    Each cluster entry has: cluster_id, person_name, face_count, sample_face_id, sample_image_id, has_crop.
    Also returns metadata: has_embeddings, unclustered_count.
    """
    # Aggregate clusters
    cluster_q = db.query(
        Face.cluster_id,
        func.count(Face.id).label("face_count"),
        func.min(Face.id).label("sample_face_id"),
        func.min(Face.image_id).label("sample_image_id"),
    ).filter(Face.cluster_id.isnot(None)).group_by(Face.cluster_id).order_by(func.count(Face.id).desc())

    clusters_raw = cluster_q.all()

    if not clusters_raw:
        result = []
    else:
        # Batch-fetch one crop-sample face per cluster (avoids N queries)
        crop_sample_rows = (
            db.query(Face.cluster_id, func.min(Face.id).label("face_id"))
            .filter(Face.cluster_id.isnot(None), Face.crop_path.isnot(None))
            .group_by(Face.cluster_id)
            .all()
        )
        crop_sample_id_by_cluster = {r.cluster_id: r.face_id for r in crop_sample_rows}

        # Load all crop-sample face objects in one query
        crop_face_ids = list(crop_sample_id_by_cluster.values())
        crop_faces_by_id = (
            {f.id: f for f in db.query(Face).filter(Face.id.in_(crop_face_ids)).all()}
            if crop_face_ids else {}
        )

        # Load fallback faces (sample_face_id) in one query for clusters without crop
        fallback_ids = [
            row.sample_face_id for row in clusters_raw
            if row.cluster_id not in crop_sample_id_by_cluster
        ]
        fallback_faces_by_id = (
            {f.id: f for f in db.query(Face).filter(Face.id.in_(fallback_ids)).all()}
            if fallback_ids else {}
        )

        # Batch-fetch best person name per cluster (avoids N queries)
        name_rows = (
            db.query(Face.cluster_id, Face.person_name, func.count(Face.id).label("cnt"))
            .filter(Face.cluster_id.isnot(None), Face.person_name.isnot(None))
            .group_by(Face.cluster_id, Face.person_name)
            .all()
        )
        best_names: dict = {}
        for nr in name_rows:
            if nr.cluster_id not in best_names or nr.cnt > best_names[nr.cluster_id][1]:
                best_names[nr.cluster_id] = (nr.person_name, nr.cnt)
        cluster_names = {cid: v[0] for cid, v in best_names.items()}

        result = []
        for row in clusters_raw:
            crop_face_id = crop_sample_id_by_cluster.get(row.cluster_id)
            if crop_face_id:
                sample = crop_faces_by_id.get(crop_face_id)
            else:
                sample = fallback_faces_by_id.get(row.sample_face_id)

            result.append({
                "cluster_id": row.cluster_id,
                "person_name": cluster_names.get(row.cluster_id),
                "face_count": row.face_count,
                "sample_face_id": sample.id if sample else row.sample_face_id,
                "sample_image_id": row.sample_image_id,
                "has_crop": bool(sample and sample.crop_path),
            })

    has_embeddings = db.query(Face.id).filter(Face.embedding.isnot(None), Face.ignored.is_(False)).first() is not None
    unclustered_count = (
        db.query(func.count(Face.id))
        .filter(Face.cluster_id.is_(None), Face.embedding.isnot(None), Face.ignored.is_(False))
        .scalar()
        or 0
    )

    return {
        "clusters": result,
        "has_embeddings": has_embeddings,
        "unclustered_count": unclustered_count,
    }


@router.get("/unknown")
def list_unknown_faces(
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List faces that have no cluster assignment."""
    query = db.query(Face).filter(Face.cluster_id.is_(None), Face.embedding.isnot(None))
    total = query.count()
    faces = query.order_by(Face.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "faces": [
            {
                "id": f.id,
                "image_id": f.image_id,
                "has_crop": bool(f.crop_path),
                "person_name": f.person_name,
                "estimated_age": f.estimated_age,
                "gender": f.gender,
            }
            for f in faces
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/cluster")
def run_clustering(db: Session = Depends(get_db)):
    """Re-cluster all faces that have embeddings."""
    count = _do_cluster_faces(db)
    return {"status": "ok", "clusters": count}


@router.post("/cluster/merge")
def merge_clusters(body: dict, db: Session = Depends(get_db)):
    """Merge one or more source clusters into a target cluster."""
    source_ids = body.get("source_cluster_ids", [])
    target_id = body.get("target_cluster_id")
    if target_id is None or not source_ids:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="source_cluster_ids and target_cluster_id required")

    # Inherit the target cluster's person name
    name_row = (
        db.query(Face.person_name)
        .filter(Face.cluster_id == target_id, Face.person_name.isnot(None))
        .first()
    )
    target_name = name_row.person_name if name_row else None

    updated = 0
    for src_id in source_ids:
        if src_id == target_id:
            continue
        n = db.query(Face).filter(Face.cluster_id == src_id).update(
            {"cluster_id": target_id, "person_name": target_name}
        )
        updated += n

    db.commit()
    return {"status": "ok", "merged_faces": updated, "target_cluster_id": target_id}


@router.delete("/cluster/{cluster_id}")
def delete_cluster(cluster_id: int, db: Session = Depends(get_db)):
    """Mark all faces in a cluster as ignored and clear their cluster assignment."""
    updated = (
        db.query(Face)
        .filter(Face.cluster_id == cluster_id)
        .update({"cluster_id": None, "ignored": True})
    )
    db.commit()
    if updated == 0:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return {"status": "ok", "ignored_faces": updated}


@router.post("/clusters/delete")
def delete_clusters(body: dict, db: Session = Depends(get_db)):
    """Mark all faces in multiple clusters as ignored."""
    cluster_ids = body.get("cluster_ids", [])
    if not cluster_ids:
        raise HTTPException(status_code=422, detail="cluster_ids required")
    updated = (
        db.query(Face)
        .filter(Face.cluster_id.in_(cluster_ids))
        .update({"cluster_id": None, "ignored": True}, synchronize_session=False)
    )
    db.commit()
    return {"status": "ok", "ignored_faces": updated, "deleted_clusters": len(cluster_ids)}


@router.put("/cluster/{cluster_id}/name")
def name_cluster(cluster_id: int, body: dict, db: Session = Depends(get_db)):
    """Assign a person name to every face in a cluster."""
    name = (body.get("name") or "").strip() or None
    updated = (
        db.query(Face)
        .filter(Face.cluster_id == cluster_id)
        .update({"person_name": name})
    )
    db.commit()
    if updated == 0:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return {"status": "ok", "updated": updated}


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
