import os
from fastapi import APIRouter
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '.env')


def _read_env() -> dict[str, str]:
    """Read .env file into a dict, preserving comments."""
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


def _write_env(env: dict[str, str]):
    """Write env dict back to .env file with section comments."""
    sections = [
        ("# QNAP NAS (SMB)", ["SMB_HOST", "SMB_USERNAME", "SMB_PASSWORD", "SMB_SHARES"]),
        ("# MariaDB", ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]),
        ("# Scanner settings", ["SCAN_CONCURRENCY", "SCAN_INTERVAL_MINUTES"]),
        ("# Scheduled processing window", ["SCAN_SCHEDULE_ENABLED", "SCAN_SCHEDULE_START", "SCAN_SCHEDULE_END"]),
        ("# Elasticsearch", ["ES_HOST", "ES_INDEX"]),
    ]
    written_keys = set()
    lines = []
    for comment, keys in sections:
        lines.append(comment)
        for key in keys:
            if key in env:
                lines.append(f"{key}={env[key]}")
                written_keys.add(key)
        lines.append("")

    # Write any remaining keys not in sections
    for key, value in env.items():
        if key not in written_keys:
            lines.append(f"{key}={value}")

    with open(ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


class SettingsResponse(BaseModel):
    smb_host: str
    smb_username: str
    smb_shares: list[str]
    scan_concurrency: int
    scan_interval_minutes: int
    scan_schedule_enabled: bool
    scan_schedule_start: str
    scan_schedule_end: str


class SettingsUpdate(BaseModel):
    smb_host: str | None = None
    smb_username: str | None = None
    smb_password: str | None = None
    smb_shares: list[str] | None = None
    scan_concurrency: int | None = None
    scan_interval_minutes: int | None = None
    scan_schedule_enabled: bool | None = None
    scan_schedule_start: str | None = None
    scan_schedule_end: str | None = None


@router.get("", response_model=SettingsResponse)
def get_settings():
    return SettingsResponse(
        smb_host=settings.SMB_HOST,
        smb_username=settings.SMB_USERNAME,
        smb_shares=[s.strip() for s in settings.SMB_SHARES if s.strip()],
        scan_concurrency=settings.SCAN_CONCURRENCY,
        scan_interval_minutes=settings.SCAN_INTERVAL_MINUTES,
        scan_schedule_enabled=settings.SCAN_SCHEDULE_ENABLED,
        scan_schedule_start=settings.SCAN_SCHEDULE_START,
        scan_schedule_end=settings.SCAN_SCHEDULE_END,
    )


@router.put("")
def update_settings(body: SettingsUpdate):
    env = _read_env()
    changed = []

    if body.smb_host is not None:
        env["SMB_HOST"] = body.smb_host
        settings.SMB_HOST = body.smb_host
        changed.append("SMB_HOST")

    if body.smb_username is not None:
        env["SMB_USERNAME"] = body.smb_username
        settings.SMB_USERNAME = body.smb_username
        changed.append("SMB_USERNAME")

    if body.smb_password is not None and body.smb_password != "":
        env["SMB_PASSWORD"] = body.smb_password
        settings.SMB_PASSWORD = body.smb_password
        changed.append("SMB_PASSWORD")

    if body.smb_shares is not None:
        shares = [s.strip() for s in body.smb_shares if s.strip()]
        env["SMB_SHARES"] = ",".join(shares)
        settings.SMB_SHARES = shares
        changed.append("SMB_SHARES")

    if body.scan_concurrency is not None:
        env["SCAN_CONCURRENCY"] = str(body.scan_concurrency)
        settings.SCAN_CONCURRENCY = body.scan_concurrency
        changed.append("SCAN_CONCURRENCY")

    if body.scan_interval_minutes is not None:
        env["SCAN_INTERVAL_MINUTES"] = str(body.scan_interval_minutes)
        settings.SCAN_INTERVAL_MINUTES = body.scan_interval_minutes
        changed.append("SCAN_INTERVAL_MINUTES")

    if body.scan_schedule_enabled is not None:
        env["SCAN_SCHEDULE_ENABLED"] = "true" if body.scan_schedule_enabled else "false"
        settings.SCAN_SCHEDULE_ENABLED = body.scan_schedule_enabled
        changed.append("SCAN_SCHEDULE_ENABLED")

    if body.scan_schedule_start is not None:
        env["SCAN_SCHEDULE_START"] = body.scan_schedule_start
        settings.SCAN_SCHEDULE_START = body.scan_schedule_start
        changed.append("SCAN_SCHEDULE_START")

    if body.scan_schedule_end is not None:
        env["SCAN_SCHEDULE_END"] = body.scan_schedule_end
        settings.SCAN_SCHEDULE_END = body.scan_schedule_end
        changed.append("SCAN_SCHEDULE_END")

    _write_env(env)

    # Reset SMB connection cache so new credentials take effect
    if any(k.startswith("SMB_") for k in changed):
        try:
            import smbclient
            from services.smb_service import _ensure_registered
            import services.smb_service as smb_mod
            smb_mod._registered = False
        except Exception:
            pass

    return {"status": "ok", "changed": changed}
