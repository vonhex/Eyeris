import os
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from config import settings
SEARXNG_PREFS = "eJx1WEuv47oN_jXNxmhwb6do0UVWBbptgXv3Bi3RNsey6KNHEp9fX8qPWIozi5MZf5QoiuLjkxQE7NgR-tvFgO0idHiDGPhiWIHBG9pL-lQ8TgYD3jrmzuClhTsptrVDz-aO7nahUabWk-PnfPvTRbyMGHrWt__9948_Lx5a9AhO9bffLqHHEW-eksaLKIgm-Fp0WXzUAZrbf8B4vGimQzuDfF7ZdZd1Wu3DbDZDFdqArgZDnR3l_9t80HewCnW9rbuiXxHdXJOtAwVRsILriGSCWt0xyySDKqwb6TkMOPubxhbE1kt0pm7ZjRAC2e42OQxhvmjy0BhZD21HVvz54x-_bYrrDi06MH_5279fYHUnjezrev1XRP_qoKtrz4rAVCNqAgFBtdFmg8QPDVZeDmSo68Xlb-iq9_OMCqImkY3Rk0oiM4mllSEbn9UEakjqRG1IMuuhTkey6JiGaiTn2NV1S2Zdc5JzqOQ36XaYCSxIZGjYFaXNrks8aKANtfRknwPgAql8S-5Jd3GHIpRTTIAfckc2YLWCcTp20wDpWA4RoFo1ZppXeABqdxOTGVNyeDGbDKW_zJWNHHc5xHYf9Cc0Oe7lvgU5nXdDQfUxYAk1UQ0YNsOaqSnWC5q67vA0T2glOzxmqy-Bc1VKXXWuWfXYDpxikSX9XEIce--wzX0s2EPfSfIwW3XG6e3zvOcEFltW0TlROuczNeK3JOrrwDT6AIH8YZPGO4ENEguZ7gRKQOXLad1Vko1kKdAiyRaROEdX9bHZfJisUIbPqYiyWdLH4ikKNIQiCLScRvrr-DN69kQmO514JiucleEPhGTOYdWaZiNMMlx-k90j_9zDdR8lhQhnLHYX5pGt5B0eo35_Zoa22nHa_h5M4k0degijFOd8mCE1uBxwKOWE2_AAh5UmJ3UyVczV260jOxDkmdzOc-blDum7l6qbI5aiP8JCvgPzpq-TMg3N8XGcq2KNDbrukKHEPY_7N7N2CDpfaGldpes37HRUG-5VzwZcniObZDIwp-rnDw_mkpEljXKF0i3Qpcr-Hss9NA7Sz2Z4DymAVyNXAJ_7lp0o8VfandMvC24fZKqJfXjtrI-d9KGuBbWPyJAqBbrH4D-IvHSCVxugUTeHB2nsYh4LZCHbogSlk4yc8wFfNOcV9Cf5ng99g8QW-MyFBsdxruQUx5hyO5nx1hDXEdFL2fuFLHnhV7KkWcLrg5jkFNxcpQTylFu0CbiVybYTRpIfnuRXdy8qhuHGB7y63YEmKtJFgQbpl5rtL_bwEvfg-wDdhxHabrqFYYGa4PVJqaZLZlZGit2BPqX8RX0k2MjfPeU2j4-xMTlgU5DKX3Zydtozy84Ah39GkHzHPXhZzx7zvsPGwLj32dSvQArGEXxHWu2yKTZScWCr629yk1KhxLbzya1PsLgGs0BLkA9SuYLU0L2QJlAW5Oy0VxJEfm_Ak24wX3ESLig0cVMg7EmSGn3erSZKSdrAnCmlJwhw7hW74FR9JhZu46Wo67ThfRNCNM9d7AV-UP8S7Qt8mlaUQ_G-8Ib7vvvlLCrNI5Bd9VdpDt3zgJZREpqFl-Zpp3VfEVzB2xbgbOvXQ_p-MS4BpXEr9Hnq2YcOhOtWjTR5n5MOiT5N4ZRUDoWJuWMtR10fpEoWfd9xCKk5SS1nzBrL6slx9hSKHiyXiLb34VTyPU4E-1G-DPbcccFfF-C83xU-7XeFH6ikh7-24TkKTS7TX0iXGlh4Y2v4sbNvP8Qm2hC3bx-llkf_ymu53Kjo_XWa5U63VxYFWs_XvVjvDGCiv0rPxBPuUUqFcPxPPdUnyjel-2O-_R0so-CAz54RCjBmpIiHWdJVOs6QauSejnKlJC2Uxa2NYIdDUiK2QXEGOboZEIqWGK2Xhu_7nAzDmrcZZ16QD7R5xZeTOQ5ohp65nC5A6YWZY4hNXmlfyIteAxnhgKmSZsPuNBbXwwc1RfFMLLhhHvw7WCyfgK_IZbgnUALOqTM6oVqa-S_gIxIETgYvFT0n5umas8RSqeHO81vUJDSFnmTc9eTvXHhKoFz4dlHORUu8HGHzYNM6aXFm6subA6nwzbawbZyFXAtXroKT67WRPqFz8e8_fvzzeWjWUaPNi8y3TdGdqeOfiMMZOcfZhhdHuDDUiQyHYw0L95TyGRFIwFnfChfqVuhchWMzdzjubGhCdG9xu1RgWX9I984HNnlIQ3mBTN9nY1wU9pJrfLDTloYsgPhJA1vpbJWfLdt5zC5F_t4lEpAplNtHSLeh5Iq3NhGfj-UN4DX2Lneo5XEje0oY5V5ahGQI7krZUQpjuReBsQDncF3h88PBAhfeFxZ0UM41B_v4ekUIf88eDaahu3acdXkv1Eg5YdtfMXOLbALlviFkcn2kWfCLcLDijavbbiDHVrZLULmX43FsMlFm-htDvT7wPWTllPhkl-s8_iEc1iyVl12telTDa9F9rgKjomQPr_VXurn0V4m-sBieePM2NGlxy3WqTm92TpLvvuWSaWtZkdMIKYh1ytSL9Atxxe3_r9Pwjw=="

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
    if not settings.SEARXNG_URL:
        raise HTTPException(status_code=503, detail="SearXNG URL not configured")
    async with httpx.AsyncClient(timeout=20, cookies={"preferences": SEARXNG_PREFS}) as client:
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
        if category == "images":
            img_src = r.get("img_src") or r.get("url")
            thumb = r.get("thumbnail_src") or r.get("thumbnail") or img_src
            if not img_src:
                continue
            results.append({
                "url": img_src,
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
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
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
