import os
from contextlib import asynccontextmanager

from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import engine, Base
from routers import images, tags, categories, scan, stats, albums, faces, settings as settings_router, searxng, auth
from services.scanner_service import start_background_scanner
from services.watcher_service import start_watcher
from config import settings

# auto_error=False so requests without Authorization header don't immediately 401
# (allows falling back to ?token= query param for <img src> requests)
security = HTTPBearer(auto_error=False)


def _verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = Query(default=None),
):
    """Verify JWT from Authorization header or ?token= query param."""
    import jwt as pyjwt

    raw = credentials.credentials if credentials else token
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")

    secret_key = settings.SECRET_KEY
    if not secret_key:
        # Fallback for the very first request if auto_setup happened in background
        from routers.auth import _read_env
        secret_key = _read_env().get("EYERIS_SECRET_KEY", "")

    try:
        payload = pyjwt.decode(raw, secret_key, algorithms=["HS256"])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Startup: create tables and start scanner
    Base.metadata.create_all(bind=engine)
    print("[Startup] Database tables created/verified")

    # Auto-setup: if no password hash yet, generate one with default password
    from routers.auth import _is_setup_complete, auto_setup as _auto_setup
    if not _is_setup_complete():
        try:
            result = _auto_setup()  # sync I/O, FastAPI handles it in thread pool
            print(f"[Startup] Auto-created account (password: {result.get('password')})")
        except HTTPException:
            pass  # already set up by another process/thread
        except Exception as e:
            print(f"[Startup] Auto-setup: {e}")

    # Migrate faces table — add new columns if missing
    try:
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(engine)
        face_cols = {c["name"] for c in inspector.get_columns("faces")}
        with engine.begin() as conn:
            if "cluster_id" not in face_cols:
                conn.execute(text("ALTER TABLE faces ADD COLUMN cluster_id INT NULL"))
                print("[Startup] Added faces.cluster_id")
            if "face_bbox" not in face_cols:
                conn.execute(text("ALTER TABLE faces ADD COLUMN face_bbox VARCHAR(100) NULL"))
                print("[Startup] Added faces.face_bbox")
            if "embedding" not in face_cols:
                conn.execute(text("ALTER TABLE faces ADD COLUMN embedding LONGTEXT NULL"))
                print("[Startup] Added faces.embedding")
            if "crop_path" not in face_cols:
                conn.execute(text("ALTER TABLE faces ADD COLUMN crop_path VARCHAR(512) NULL"))
                print("[Startup] Added faces.crop_path")
            # Add missing indexes (speeds up People page cluster queries)
            face_indexes = {idx["name"] for idx in inspector.get_indexes("faces")}
            if "ignored" not in face_cols:
                conn.execute(text("ALTER TABLE faces ADD COLUMN ignored TINYINT(1) NOT NULL DEFAULT 0"))
                print("[Startup] Added faces.ignored")
            
            is_sqlite = "sqlite" in str(engine.url)
            if "ix_faces_cluster_id" not in face_indexes:
                if is_sqlite:
                    conn.execute(text("CREATE INDEX ix_faces_cluster_id ON faces (cluster_id)"))
                else:
                    conn.execute(text("ALTER TABLE faces ADD INDEX ix_faces_cluster_id (cluster_id)"))
                print("[Startup] Added index ix_faces_cluster_id")
            if "ix_faces_crop_path" not in face_indexes:
                if is_sqlite:
                    conn.execute(text("CREATE INDEX ix_faces_crop_path ON faces (crop_path)"))
                else:
                    conn.execute(text("ALTER TABLE faces ADD INDEX ix_faces_crop_path (crop_path(255))"))
                print("[Startup] Added index ix_faces_crop_path")
    except Exception as e:
        print(f"[Startup] Face migration: {e}")
    try:
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(engine)
        img_cols = {c["name"] for c in inspector.get_columns("images")}
        with engine.begin() as conn:
            is_sqlite = "sqlite" in str(engine.url)
            if "favorite" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN favorite TINYINT(1) NOT NULL DEFAULT 0"))
                print("[Startup] Added images.favorite")
            if "perceptual_hash" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN perceptual_hash VARCHAR(64) NULL"))
                print("[Startup] Added images.perceptual_hash")
            if "gps_lat" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN gps_lat DOUBLE NULL"))
                print("[Startup] Added images.gps_lat")
            if "gps_lon" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN gps_lon DOUBLE NULL"))
                print("[Startup] Added images.gps_lon")
            if "camera_model" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN camera_model VARCHAR(255) NULL"))
                print("[Startup] Added images.camera_model")
            if "location_name" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN location_name VARCHAR(255) NULL"))
                if is_sqlite:
                    conn.execute(text("CREATE INDEX ix_images_location_name ON images (location_name)"))
                else:
                    conn.execute(text("ALTER TABLE images ADD INDEX ix_images_location_name (location_name)"))
                print("[Startup] Added images.location_name")
            if "quality_flags" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN quality_flags TEXT NULL"))
                print("[Startup] Added images.quality_flags")
            if "is_video" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_video TINYINT(1) NOT NULL DEFAULT 0"))
                if is_sqlite:
                    conn.execute(text("CREATE INDEX ix_images_is_video ON images (is_video)"))
                else:
                    conn.execute(text("ALTER TABLE images ADD INDEX ix_images_is_video (is_video)"))
                print("[Startup] Added images.is_video")
            
            # Backfill is_video based on filename extensions
            v_exts = "('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.m4v')"
            for ext in [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"]:
                res = conn.execute(text(f"UPDATE images SET is_video = 1 WHERE filename LIKE '%{ext}' AND is_video = 0"))
                if res.rowcount > 0:
                    print(f"[Startup] Backfilled is_video=1 for {res.rowcount} {ext} files")
    except Exception as e:
        print(f"[Startup] Image migration: {e}")

    # Backfill location_name for images that have GPS coords but no location yet
    try:
        import asyncio as _asyncio
        from database import SessionLocal as _SessionLocal
        from models import Image as _Image
        import reverse_geocode as _rg

        async def _backfill_locations():
            db = _SessionLocal()
            try:
                rows = (
                    db.query(_Image.id, _Image.gps_lat, _Image.gps_lon)
                    .filter(_Image.gps_lat.isnot(None), _Image.location_name.is_(None))
                    .all()
                )
                if not rows:
                    return
                print(f"[Startup] Backfilling location names for {len(rows)} images…")
                coords = [(r.gps_lat, r.gps_lon) for r in rows]
                results = _rg.search(coords)
                for row, geo in zip(rows, results):
                    city = geo.get("city", "")
                    country = geo.get("country", "")
                    name = ", ".join(filter(None, [city, country]))
                    if name:
                        db.query(_Image).filter(_Image.id == row.id).update({"location_name": name})
                db.commit()
                print(f"[Startup] Location backfill complete.")
            except Exception as e:
                print(f"[Startup] Location backfill error: {e}")
            finally:
                db.close()

        _asyncio.create_task(_backfill_locations())
    except Exception as e:
        print(f"[Startup] Location backfill setup error: {e}")

    await start_background_scanner()
    print("[Startup] Background scanner started")
    await start_watcher()
    print("[Startup] File watcher started")
    yield
    # Shutdown
    print("[Shutdown] App shutting down")


app = FastAPI(
    title="Image Catalog",
    description="AI-powered image categorization from NAS storage",
    version="1.1.11",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Route registration — auth routes are public, all others require JWT token
app.include_router(auth.router)

for _router in [images.router, tags.router, categories.router, scan.router,
                stats.router, albums.router, faces.router, settings_router.router, searxng.router]:
    app.include_router(_router, dependencies=[Depends(_verify_token)])


@app.get("/api/health")
def health():
    return {"status": "ok"}


FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

# Serve React frontend in production
if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        # Serve index.html for all non-API routes (SPA client-side routing)
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
