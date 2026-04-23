import httpx
from fastapi import APIRouter

from config import settings

router = APIRouter(prefix="/api/aeye", tags=["aeye"])

TIMEOUT = httpx.Timeout(8.0, connect=3.0)

_cached_token: str | None = None


async def _get_token(client: httpx.AsyncClient, url: str) -> str | None:
    global _cached_token
    if not settings.AEYE_USERNAME or not settings.AEYE_PASSWORD:
        return None
    try:
        r = await client.post(
            f"{url}/api/login",
            json={"username": settings.AEYE_USERNAME, "password": settings.AEYE_PASSWORD},
        )
        if r.status_code == 200:
            data = r.json()
            token = data.get("access_token") or data.get("token")
            _cached_token = token
            return token
    except Exception:
        pass
    return None


async def _authed_get(client: httpx.AsyncClient, url: str, path: str):
    global _cached_token
    headers = {}
    if _cached_token:
        headers["Authorization"] = f"Bearer {_cached_token}"
    r = await client.get(f"{url}{path}", headers=headers)
    if r.status_code == 401:
        # Token expired or invalid — re-login
        token = await _get_token(client, url)
        if token:
            r = await client.get(f"{url}{path}", headers={"Authorization": f"Bearer {token}"})
    return r if r.status_code == 200 else None


@router.get("/status")
async def get_aeye_status():
    global _cached_token
    url = settings.AEYE_URL.rstrip("/") if settings.AEYE_URL else ""
    if not url:
        return {"configured": False}

    health = None
    dashboard = None

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(f"{url}/api/health")
            if r.status_code == 200:
                health = r.json()
        except Exception as e:
            return {"configured": True, "connected": False, "error": str(e)}

        # Try authenticated endpoints
        if not _cached_token and settings.AEYE_USERNAME and settings.AEYE_PASSWORD:
            await _get_token(client, url)

        for path in ("/api/dashboard/status", "/api/stats", "/api/status"):
            resp = await _authed_get(client, url, path)
            if resp is not None:
                dashboard = resp.json()
                break

    result: dict = {"configured": True, "connected": True, "url": url}

    if health:
        result["status"] = health.get("status")
        ollama = health.get("ollama") or {}
        result["ollama_connected"] = ollama.get("connected") if ollama else health.get("ollama_connected")
        result["ollama_host"] = ollama.get("host") if ollama else health.get("ollama_host")
        result["vision_model"] = (ollama.get("vision_model") if ollama else None) or health.get("vision_model")
        result["llm_model"] = (ollama.get("llm_model") if ollama else None) or health.get("llm_model")
        models = (ollama.get("models") if ollama else None) or health.get("available_models") or []
        result["available_models"] = models if isinstance(models, list) else []

    if dashboard:
        db_stats = dashboard.get("database_stats") or dashboard.get("db_stats") or {}
        worker = dashboard.get("worker") or dashboard.get("worker_state") or {}
        result["total_images"] = db_stats.get("total") or dashboard.get("total_images")
        result["processed"] = db_stats.get("completed") or db_stats.get("processed") or dashboard.get("processed")
        result["pending"] = db_stats.get("pending") or dashboard.get("pending")
        result["errors"] = db_stats.get("error") or db_stats.get("errors") or dashboard.get("errors")
        result["progress_pct"] = dashboard.get("progress_pct") or dashboard.get("overall_progress")
        result["worker_state"] = (
            worker.get("state") if isinstance(worker, dict) else worker
        ) or dashboard.get("worker_state")
        result["queue_depth"] = (
            worker.get("queue_depth") if isinstance(worker, dict) else None
        ) or dashboard.get("queue_depth")

    result["auth_configured"] = bool(settings.AEYE_USERNAME and settings.AEYE_PASSWORD)

    return result
