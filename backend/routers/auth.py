import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import bcrypt

router = APIRouter(prefix="/auth", tags=["auth"])

ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '.env')

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


def _read_env() -> dict[str, str]:
    # Seed from process environment (works in Docker where .env is passed as env vars)
    env = {k: v for k, v in os.environ.items()}
    # File values override, and become the source of truth for writes
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


def _write_env(env: dict[str, str]):
    sections = [
        ("# QNAP NAS (SMB)", ["SMB_HOST", "SMB_USERNAME", "SMB_PASSWORD", "SMB_SHARES"]),
        ("# MariaDB", ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]),
        ("# Scanner settings", ["SCAN_CONCURRENCY", "SCAN_INTERVAL_MINUTES"]),
        ("# Scheduled processing window", ["SCAN_SCHEDULE_ENABLED", "SCAN_SCHEDULE_START", "SCAN_SCHEDULE_END"]),
        ("# SearXNG integration", ["SEARXNG_URL"]),
        ("# Authentication (auto-generated)", ["EYERIS_SECRET_KEY", "EYERIS_PASSWORD_HASH"]),
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

    with open(ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    
    # Update current process environment
    for key, value in env.items():
        os.environ[key] = str(value)


def _get_password_hash() -> str | None:
    env = _read_env()
    return env.get("EYERIS_PASSWORD_HASH")


def _is_setup_complete() -> bool:
    return _get_password_hash() is not None


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


class PasswordSetup(BaseModel):
    password: str


class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class StatusResponse(BaseModel):
    setup_complete: bool
    authenticated: bool


@router.get("/status", response_model=StatusResponse)
def auth_status():
    setup_complete = _is_setup_complete()
    return {
        "setup_complete": setup_complete,
        "authenticated": False if not setup_complete else True,  # placeholder - actual check via token
    }


@router.post("/setup")
def setup_password(body: PasswordSetup):
    """Set initial admin password (only callable before first setup)."""
    if _is_setup_complete():
        raise HTTPException(status_code=409, detail="Password already set")

    hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    env = _read_env()
    secret_key = secrets.token_hex(32)
    env["EYERIS_SECRET_KEY"] = secret_key
    env["EYERIS_PASSWORD_HASH"] = hash
    
    _write_env(env)
    
    return {"status": "ok", "setup_complete": True}


@router.post("/auto-setup")
def auto_setup():
    """Auto-generate a default password if not yet set. Returns the plaintext password."""
    if _is_setup_complete():
        raise HTTPException(status_code=409, detail="Password already set")

    default_password = "eyeris"
    hash = bcrypt.hashpw(default_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    env = _read_env()
    secret_key = secrets.token_hex(32)
    env["EYERIS_SECRET_KEY"] = secret_key
    env["EYERIS_PASSWORD_HASH"] = hash
    
    _write_env(env)
    
    return {"status": "ok", "setup_complete": True, "password": default_password}


@router.post("/login")
def login(body: LoginRequest):
    """Login with password, returns JWT token."""
    hashed = _get_password_hash()
    if not hashed or not _verify_password(body.password, hashed):
        raise HTTPException(status_code=401, detail="Invalid password")

    env = _read_env()
    secret_key = env.get("EYERIS_SECRET_KEY", secrets.token_hex(32))

    token_data = {
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    
    try:
        import jwt as pyjwt
        token = pyjwt.encode(token_data, secret_key, algorithm=JWT_ALGORITHM)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token generation failed: {e}")

    return {"token": token}


@router.post("/logout")
def logout():
    """Logout (client clears token)."""
    return {"status": "ok"}


@router.put("/change-password")
def change_password(body: ChangePasswordRequest):
    """Change password for authenticated user."""
    hashed = _get_password_hash()
    if not hashed or not _verify_password(body.current_password, hashed):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    env = _read_env()
    env["EYERIS_PASSWORD_HASH"] = new_hash
    
    _write_env(env)
    
    return {"status": "ok"}
