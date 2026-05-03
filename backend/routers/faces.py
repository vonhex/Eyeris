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

def _do_cluster_faces(db: Session, threshold: float = 0.82) -> int:
    """
    Cluster faces with embeddings using hierarchical clustering (average linkage).
    Returns the number of clusters created.
    Threshold: cosine similarity >= threshold means same person.

    Faces with bounding boxes smaller than MIN_FACE_PX in either dimension are
    excluded — tiny crops produce degenerate FaceNet embeddings that collapse
    into one giant spurious cluster.

    Pinned faces (from manual merges/names) are preserved and not re-clustered.
    New cluster IDs are offset so they don't collide with pinned cluster IDs.
    """
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    MIN_FACE_PX = 60

    # Only cluster non-pinned faces
    faces = db.query(Face).filter(
        Face.embedding.isnot(None), Face.ignored.is_(False), Face.pinned == False
    ).all()
    if len(faces) < 1:
        return 0

    embs = []
    valid = []
    for f in faces:
        try:
            # Skip faces with tiny bounding boxes
            if f.face_bbox:
                bbox = json.loads(f.face_bbox)
                if len(bbox) == 4:
                    w = bbox[2] - bbox[0]
                    h = bbox[3] - bbox[1]
                    if w < MIN_FACE_PX or h < MIN_FACE_PX:
                        continue
            e = json.loads(f.embedding)
            if len(e) == 512:
                embs.append(e)
                valid.append(f)
        except Exception:
            pass

    if not embs:
        return 0

    arr = np.array(embs, dtype=np.float32)
    # L2-normalise for cosine distance
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr = arr / (norms + 1e-8)

    n = len(arr)

    # Compute offset so new IDs don't collide with pinned cluster IDs
    offset = (db.query(func.max(Face.cluster_id)).filter(Face.pinned == True).scalar() or 0) + 1

    # Clear cluster assignments on non-pinned faces only
    db.query(Face).filter(Face.ignored.is_(False), Face.pinned == False).update({"cluster_id": None})
    db.flush()

    if n < 2:
        for face in valid:
            face.cluster_id = offset
        db.commit()
        return 1

    # Compute cosine distance matrix (1 - similarity)
    # We use (1 - sims) because fcluster/linkage use distance, not similarity.
    # The max distance is (1 - threshold).
    dist_threshold = 1.0 - threshold

    # For very large datasets, compute distance in chunks to avoid O(N^2) memory crash
    # However, 'linkage' itself needs the full condensed matrix.
    # 9k faces = ~40 million pairs = ~160MB in float32. Manageable.

    # Efficiently compute cosine distance matrix
    sims = arr @ arr.T
    # Clip for safety and convert to distance
    dists = 1.0 - np.clip(sims, -1.0, 1.0)

    # Fill diagonal with 0s (self-similarity)
    np.fill_diagonal(dists, 0)

    # Convert to condensed distance matrix for scipy
    condensed_dists = squareform(dists, checks=False)

    # Perform Agglomerative Clustering with Average Linkage
    # This means a face is added to a cluster if its average distance to existing
    # members is within the threshold.
    Z = linkage(condensed_dists, method='average')

    # Form clusters
    cluster_labels = fcluster(Z, dist_threshold, criterion='distance')

    # Assign new cluster labels offset to avoid collision with pinned IDs
    for i, face in enumerate(valid):
        face.cluster_id = int(cluster_labels[i]) + offset

    db.commit()
    return int(np.max(cluster_labels))


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
        func.max(Face.pinned).label("pinned"),
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
                "pinned": bool(row.pinned),
                "description": sample.description if sample else None,
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
def run_clustering(body: dict | None = None, db: Session = Depends(get_db)):
    """Re-cluster all faces that have embeddings."""
    threshold = 0.82
    if body and "threshold" in body:
        try:
            threshold = float(body["threshold"])
        except ValueError:
            pass
    
    count = _do_cluster_faces(db, threshold=threshold)
    return {"status": "ok", "clusters": count, "threshold": threshold}


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

    # Pin all faces in the target cluster so they survive regroup
    db.query(Face).filter(Face.cluster_id == target_id).update({"pinned": True})

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
        .update({"person_name": name, "pinned": True})
    )
    db.commit()
    if updated == 0:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return {"status": "ok", "updated": updated}


@router.delete("/cluster/{cluster_id}/pin")
def unpin_cluster(cluster_id: int, db: Session = Depends(get_db)):
    """Remove the pinned flag from a cluster so regroup can reassign it."""
    updated = db.query(Face).filter(Face.cluster_id == cluster_id).update({"pinned": False})
    db.commit()
    return {"status": "ok", "unpinned": updated}


@router.post("/cluster/merge-by-description")
def merge_by_description(db: Session = Depends(get_db)):
    """Auto-merge clusters whose representative faces share >=60% meaningful words in description."""
    STOPWORDS = {
        "a", "an", "the", "of", "with", "and", "in", "is", "are", "has",
        "wearing", "photo", "photograph", "image", "shows", "close", "up", "closeup",
    }

    def meaningful_words(text: str) -> set:
        words = set(text.lower().split())
        return words - STOPWORDS

    # Find all clusters that have a crop with a description
    desc_rows = (
        db.query(Face.cluster_id, Face.description)
        .filter(
            Face.cluster_id.isnot(None),
            Face.description.isnot(None),
            Face.crop_path.isnot(None),
        )
        .distinct(Face.cluster_id)
        .all()
    )

    if not desc_rows:
        return {"merged_groups": 0, "faces_reassigned": 0}

    # Build {cluster_id: set_of_words}
    cluster_words = {}
    for row in desc_rows:
        words = meaningful_words(row.description)
        if words:
            cluster_words[row.cluster_id] = words

    cluster_ids = list(cluster_words.keys())
    n = len(cluster_ids)

    # Union-Find for grouping similar clusters
    parent = {cid: cid for cid in cluster_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = cluster_ids[i], cluster_ids[j]
            wa, wb = cluster_words[a], cluster_words[b]
            if not wa or not wb:
                continue
            intersection = len(wa & wb)
            smaller = min(len(wa), len(wb))
            if smaller > 0 and intersection / smaller >= 0.6:
                union(a, b)

    # Build groups: root -> list of cluster_ids
    groups: dict = {}
    for cid in cluster_ids:
        root = find(cid)
        groups.setdefault(root, []).append(cid)

    # Only merge groups of 2+
    merged_groups = 0
    faces_reassigned = 0
    for root, members in groups.items():
        if len(members) < 2:
            continue

        # Target = cluster with the most faces
        counts = {}
        for cid in members:
            counts[cid] = db.query(func.count(Face.id)).filter(Face.cluster_id == cid).scalar() or 0
        target_id = max(counts, key=lambda c: counts[c])

        for src_id in members:
            if src_id == target_id:
                continue
            n_updated = db.query(Face).filter(Face.cluster_id == src_id).update(
                {"cluster_id": target_id}
            )
            faces_reassigned += n_updated

        # Pin all faces in target cluster
        db.query(Face).filter(Face.cluster_id == target_id).update({"pinned": True})
        merged_groups += 1

    db.commit()
    return {"merged_groups": merged_groups, "faces_reassigned": faces_reassigned}


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
