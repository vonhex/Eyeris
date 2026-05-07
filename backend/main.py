import logging
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

# Suppress access log noise for high-frequency polling endpoints
class _SuppressPollingEndpoints(logging.Filter):
    _MUTED = {"/api/scan/status", "/api/health"}
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(ep in msg for ep in self._MUTED)

logging.getLogger("uvicorn.access").addFilter(_SuppressPollingEndpoints())

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import engine, Base
from routers import images, tags, categories, scan, stats, albums, faces, settings as settings_router, searxng, auth, aeye
from services.scanner_service import start_background_scanner, start_aeye_xmp_poll
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

    # Apply persisted settings from the JSON backup (survives container recreation
    # even when the .env file is not volume-mounted on the host)
    try:
        from routers.settings import apply_json_settings
        apply_json_settings()
        print("[Startup] Applied persisted settings from JSON store")
    except Exception as e:
        print(f"[Startup] Settings JSON load: {e}")

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
            
            face_indexes = {idx["name"] for idx in inspector.get_indexes("faces")}
            if "ignored" not in face_cols:
                conn.execute(text("ALTER TABLE faces ADD COLUMN ignored TINYINT(1) NOT NULL DEFAULT 0"))
                print("[Startup] Added faces.ignored")
            if "pinned" not in face_cols:
                conn.execute(text("ALTER TABLE faces ADD COLUMN pinned TINYINT(1) NOT NULL DEFAULT 0"))
                print("[Startup] Added faces.pinned")
            
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
            
            # Additional shooting and analysis columns
            for col, definition in [
                ("lens_model", "VARCHAR(255) NULL"),
                ("aperture", "FLOAT NULL"),
                ("shutter_speed", "VARCHAR(32) NULL"),
                ("iso", "INT NULL"),
                ("focal_length", "FLOAT NULL"),
                ("flash", "VARCHAR(100) NULL"),
                ("sentiment", "VARCHAR(50) NULL"),
                ("sentiment_score", "FLOAT NULL"),
            ]:
                if col not in img_cols:
                    conn.execute(text(f"ALTER TABLE images ADD COLUMN {col} {definition}"))
                    print(f"[Startup] Added images.{col}")

    except Exception as e:
        print(f"[Startup] Image migration: {e}")

    # Start background services
    asyncio.create_task(start_background_scanner())
    asyncio.create_task(start_aeye_xmp_poll())
    asyncio.create_task(start_watcher())
    
    yield
    print("[Shutdown] App shutting down")


app = FastAPI(
    title="Eyeris API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(images.router, prefix="/api/images", tags=["images"], dependencies=[Depends(_verify_token)])
app.include_router(tags.router, prefix="/api/tags", tags=["tags"], dependencies=[Depends(_verify_token)])
app.include_router(categories.router, prefix="/api/categories", tags=["categories"], dependencies=[Depends(_verify_token)])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"], dependencies=[Depends(_verify_token)])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"], dependencies=[Depends(_verify_token)])
app.include_router(albums.router, prefix="/api/albums", tags=["albums"], dependencies=[Depends(_verify_token)])
app.include_router(faces.router, prefix="/api/faces", tags=["faces"], dependencies=[Depends(_verify_token)])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"], dependencies=[Depends(_verify_token)])
app.include_router(searxng.router, prefix="/api/searxng", tags=["searxng"], dependencies=[Depends(_verify_token)])
app.include_router(aeye.router, prefix="/api/aeye", tags=["aeye"], dependencies=[Depends(_verify_token)])

# Thumbnails
app.mount("/thumbnails", StaticFiles(directory=settings.THUMBNAIL_DIR), name="thumbnails")

# Static frontend (production)
frontend_path = os.path.join(settings.REPO_ROOT, "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {"message": "Eyeris API is running. Frontend build not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
