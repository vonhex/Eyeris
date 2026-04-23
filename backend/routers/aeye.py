import httpx
from fastapi import APIRouter

from config import settings

router = APIRouter(prefix="/api/aeye", tags=["aeye"])

TIMEOUT = httpx.Timeout(8.0, connect=3.0)


@router.get("/status")
async def get_aeye_status():
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

        try:
            r = await client.get(f"{url}/api/dashboard/status")
            if r.status_code == 200:
                dashboard = r.json()
        except Exception:
            pass

    result: dict = {"configured": True, "connected": True, "url": url}

    if health:
        result["status"] = health.get("status")
        result["ollama_connected"] = health.get("ollama_connected")
        result["ollama_host"] = health.get("ollama_host")
        result["vision_model"] = health.get("vision_model") or health.get("configured_vision_model")
        result["llm_model"] = health.get("llm_model") or health.get("configured_llm_model")
        models = health.get("available_models") or health.get("models") or []
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
        result["scanning"] = dashboard.get("scanning") or dashboard.get("scan_active", False)

    return result
