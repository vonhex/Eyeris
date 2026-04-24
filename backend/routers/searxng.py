import os
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from config import settings
router = APIRouter(prefix="/api/searxng", tags=["searxng"])


def _validate_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")


@router.get("/search")
async def search_web(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    category: str = Query("images", pattern="^(images|videos)$")
):
    """Search images or videos via SearXNG."""
    params = {
        "q": q,
        "format": "json",
        "categories": category,
        "pageno": page,
        "safesearch": 0,
    }
    allowed_engines = {"startpage images", "bing images"} if category == "images" else {"google videos", "bing videos", "youtube"}
    if not settings.SEARXNG_URL:
        raise HTTPException(status_code=503, detail="SearXNG URL not configured")
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.get(f"{settings.SEARXNG_URL}/search", params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"SearXNG returned {e.response.status_code}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"SearXNG unreachable: {e}")

    data = resp.json()
    results = []
    for r in data.get("results", []):
        if r.get("engine") not in allowed_engines:
            continue
        if category == "images":
            img_src = r.get("img_src") or r.get("url")
            thumb = r.get("thumbnail_src") or r.get("thumbnail") or img_src
            if not img_src:
                continue
            results.append({
                "url": img_src,
                "page_url": r.get("url"),
                "thumbnail": thumb,
                "title": r.get("title", ""),
                "source": r.get("source", ""),
                "content": r.get("content", ""),
                "type": "image"
            })
        else:
            # Video results
            results.append({
                "url": r.get("url"),
                "thumbnail": r.get("thumbnail") or r.get("thumbnail_src"),
                "title": r.get("title", ""),
                "source": r.get("author") or r.get("source", ""),
                "content": r.get("content", ""),
                "length": r.get("length", ""),
                "iframe_src": r.get("iframe_src"),
                "type": "video"
            })

    return {"results": results, "query": q, "page": page, "category": category}


@router.get("/proxy")
async def proxy_image(url: str = Query(...)):
    """Proxy an external image URL through the backend to avoid CORS issues."""
    _validate_url(url)
    parsed = urlparse(url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible)"}
    # Many image hosts check Referer; set it to the parent page URL for sites that require it
    referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme in ("http", "https") else None
    if referer:
        headers["Referer"] = referer

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Remote returned {resp.status_code}")
    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return Response(content=resp.content, media_type=content_type)


class DownloadRequest(BaseModel):
    urls: list[str]
    share: str
    subfolder: str = "web-downloads"


@router.post("/download")
async def download_to_nas(body: DownloadRequest):
    """Download images from URLs and write them to a NAS share."""
    from services.smb_service import MOUNT_BASE

    if not body.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    share = body.share.strip()
    if not share:
        raise HTTPException(status_code=400, detail="No share specified")
    subfolder = body.subfolder.strip() or "web-downloads"

    for url in body.urls:
        _validate_url(url)

    dest_dir = os.path.join(MOUNT_BASE, share, subfolder)
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not create destination directory: {e}")

    EXT_MAP = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
    }
    VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

    saved = []
    errors = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for url in body.urls:
            try:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
                resp.raise_for_status()

                path_part = urlparse(url).path
                filename = os.path.basename(path_part) or "image"
                # Strip query params that may have crept into the filename
                filename = filename.split("?")[0]
                base, ext = os.path.splitext(filename)
                if ext.lower() not in VALID_EXTS:
                    ct = resp.headers.get("content-type", "").split(";")[0].strip()
                    ext = EXT_MAP.get(ct, ".jpg")
                    filename = (base or "image") + ext

                # Avoid collisions
                dest = os.path.join(dest_dir, filename)
                if os.path.exists(dest):
                    base2, ext2 = os.path.splitext(filename)
                    filename = f"{base2}_{int(time.time() * 1000)}{ext2}"
                    dest = os.path.join(dest_dir, filename)

                with open(dest, "wb") as f:
                    f.write(resp.content)

                saved.append(filename)
            except Exception as e:
                errors.append({"url": url, "error": str(e)})

    return {"saved": len(saved), "filenames": saved, "errors": errors}
