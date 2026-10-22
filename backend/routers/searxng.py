import asyncio
import ipaddress
import os
import re
import socket
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
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
                or addr.is_multicast or addr.is_unspecified)


async def _ensure_public_host(url: str) -> None:
    """Refuse URLs whose host resolves to a private, loopback, link-local or reserved address.

    Stops the proxy/download endpoints from being used to reach the LAN, the host
    itself or cloud metadata services (SSRF). Applied to every request, redirects included.
    """
    _validate_url(url)
    host = urlparse(url).hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Host could not be resolved")
    if not infos or not all(_is_public_ip(info[4][0]) for info in infos):
        raise HTTPException(status_code=400, detail="Only public internet addresses are allowed")


async def _check_request(request: httpx.Request) -> None:
    await _ensure_public_host(str(request.url))


def _public_client(timeout: float) -> httpx.AsyncClient:
    """httpx client that validates the target of every request, including each redirect hop."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                             event_hooks={"request": [_check_request]})


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_filename(name: str) -> str:
    name = _SAFE_NAME.sub("_", os.path.basename(name)).strip(" .")
    return name[:150] or "image"


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
            print(f"[SearXNG] Search request failed: {e}")
            raise HTTPException(status_code=502, detail="SearXNG unreachable")

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
async def proxy_image(url: str = Query(...), token: str = Query(None)):
    """Proxy an external image URL through the backend to avoid CORS issues."""
    await _ensure_public_host(url)
    parsed = urlparse(url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible)"}
    # Many image hosts check Referer; set it to the parent page URL for sites that require it
    referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme in ("http", "https") else None
    if referer:
        headers["Referer"] = referer

    async with _public_client(timeout=15) as client:
        try:
            resp = await client.get(url, headers=headers)
        except HTTPException:
            raise
        except Exception as e:
            print(f"[SearXNG] Proxy fetch failed for {url}: {e}")
            raise HTTPException(status_code=502, detail="Failed to fetch image")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Remote returned {resp.status_code}")
    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return Response(content=resp.content, media_type=content_type)


from typing import Optional

class DownloadRequest(BaseModel):
    urls: list[str]
    subfolder: Optional[str] = "web-downloads"


@router.post("/download")
async def download_to_nas(body: DownloadRequest):
    """Download images from URLs and write them to a folder within MOUNT_BASE."""
    from config import settings
    import traceback

    try:
        if not body.urls:
            raise HTTPException(status_code=400, detail="No URLs provided")
        
        subfolder = (body.subfolder or "web-downloads").strip() or "web-downloads"

        for url in body.urls:
            await _ensure_public_host(url)

        # Confine the destination to the library (refuses ../ and absolute escapes)
        library = os.path.realpath(settings.MOUNT_BASE)
        dest_dir = os.path.realpath(os.path.join(library, subfolder.lstrip("/\\")))
        if not dest_dir.startswith(library + os.sep):
            raise HTTPException(status_code=400, detail="Subfolder must stay inside the library")
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            print(f"[SearXNG] Failed to create directory {dest_dir}: {e}")
            raise HTTPException(status_code=500, detail="Could not create destination directory")

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

        async with _public_client(timeout=30) as client:
            for url in body.urls:
                try:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
                    resp.raise_for_status()

                    path_part = urlparse(url).path
                    # Strip query params, then keep only safe filename characters
                    filename = _safe_filename(os.path.basename(path_part).split("?")[0])
                    base, ext = os.path.splitext(filename)
                    if ext.lower() not in VALID_EXTS:
                        ct = resp.headers.get("content-type", "").split(";")[0].strip()
                        ext = EXT_MAP.get(ct, ".jpg")
                        filename = (base or "image") + ext

                    # Avoid collisions
                    if os.path.exists(os.path.join(dest_dir, filename)):
                        base2, ext2 = os.path.splitext(filename)
                        filename = f"{base2}_{int(time.time() * 1000)}{ext2}"
                    dest = os.path.realpath(os.path.join(dest_dir, filename))
                    if not dest.startswith(dest_dir + os.sep):
                        raise HTTPException(status_code=400, detail="Invalid filename")

                    with open(dest, "wb") as f:
                        f.write(resp.content)

                    saved.append(filename)
                except Exception as e:
                    print(f"[SearXNG] Download failed for {url}: {e}")
                    reason = e.detail if isinstance(e, HTTPException) else (
                        f"HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else "download failed")
                    errors.append({"url": url, "error": reason})

        return {"saved": len(saved), "filenames": saved, "errors": errors}
    except HTTPException:
        raise  # deliberate refusals (bad subfolder, private address): no traceback
    except Exception as e:
        print(f"[SearXNG] Global download error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Download failed")
