import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import engine, Base
from routers import images, tags, categories, scan, stats, albums, faces, settings as settings_router, searxng, aeye
from services.scanner_service import start_background_scanner
from services.watcher_service import start_watcher
from services.search_service import ensure_index as es_ensure_index

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables and start scanner
    Base.metadata.create_all(bind=engine)
    print("[Startup] Database tables created/verified")

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
            if "ix_faces_cluster_id" not in face_indexes:
                conn.execute(text("ALTER TABLE faces ADD INDEX ix_faces_cluster_id (cluster_id)"))
                print("[Startup] Added index ix_faces_cluster_id")
            if "ix_faces_crop_path" not in face_indexes:
                conn.execute(text("ALTER TABLE faces ADD INDEX ix_faces_crop_path (crop_path(255))"))
                print("[Startup] Added index ix_faces_crop_path")
    except Exception as e:
        print(f"[Startup] Face migration: {e}")
    try:
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(engine)
        img_cols = {c["name"] for c in inspector.get_columns("images")}
        with engine.begin() as conn:
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
                conn.execute(text("ALTER TABLE images ADD INDEX ix_images_location_name (location_name)"))
                print("[Startup] Added images.location_name")
            if "quality_flags" not in img_cols:
                conn.execute(text("ALTER TABLE images ADD COLUMN quality_flags TEXT NULL"))
                print("[Startup] Added images.quality_flags")
    except Exception as e:
        print(f"[Startup] Image migration: {e}")
    try:
        es_ensure_index()
        print("[Startup] Elasticsearch index ready")
    except Exception as e:
        print(f"[Startup] Elasticsearch not available: {e}")
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
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(images.router)
app.include_router(tags.router)
app.include_router(categories.router)
app.include_router(scan.router)
app.include_router(stats.router)
app.include_router(albums.router)
app.include_router(faces.router)
app.include_router(settings_router.router)
app.include_router(searxng.router)
app.include_router(aeye.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/reindex")
def reindex():
    """Reindex all images in Elasticsearch."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        count = es_reindex_all(db)
        return {"status": "ok", "indexed": count}
    finally:
        db.close()


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
