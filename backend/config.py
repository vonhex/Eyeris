import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


class Settings:
    # SMB / NAS
    SMB_HOST: str = os.getenv("SMB_HOST", "10.0.1.228")
    SMB_USERNAME: str = os.getenv("SMB_USERNAME", "")
    SMB_PASSWORD: str = os.getenv("SMB_PASSWORD", "")
    SMB_SHARES: list[str] = os.getenv("SMB_SHARES", "").split(",")

    # Database — SQLite by default (good for Docker/Unraid), MariaDB when DB_HOST is set
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "image_catalog")

    # --- Path Configuration (Universal) ---
    # Default to relative paths for host-based installs (Unraid/Linux)
    # Docker overrides these via ENV variables in the Dockerfile.
    @property
    def REPO_ROOT(self) -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @property
    def DATABASE_URL(self) -> str:
        if self.DB_HOST:
            # MariaDB / MySQL
            return (
                f"mysql+pymysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        # SQLite — default for host-based or simple Docker setups
        default_db = os.path.join(self.REPO_ROOT, "db", "images.db")
        db_path = os.getenv("DB_PATH", default_db)
        # Ensure parent dir exists for SQLite
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return f"sqlite:///{db_path}"

    # Thumbnails
    THUMBNAIL_DIR: str = os.getenv("THUMBNAIL_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "thumbnails"))
    THUMBNAIL_SIZE: tuple[int, int] = (300, 300)

    # Media Storage (where NAS shares are mounted or local photos reside)
    MOUNT_BASE: str = os.getenv("MOUNT_BASE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images"))

    # SearXNG integration
    SEARXNG_URL: str = os.getenv("SEARXNG_URL", "")

    # Scanner
    SCAN_CONCURRENCY: int = int(os.getenv("SCAN_CONCURRENCY", "2"))
    SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))

    # Scheduled processing window — restrict scans to a time window (e.g. overnight)
    # SCAN_SCHEDULE_ENABLED=true, SCAN_SCHEDULE_START=22:00, SCAN_SCHEDULE_END=06:00
    # Start after End = crosses midnight (e.g. 22:00–06:00). Same = run 24/7.
    SCAN_SCHEDULE_ENABLED: bool = os.getenv("SCAN_SCHEDULE_ENABLED", "false").lower() == "true"
    SCAN_SCHEDULE_START: str = os.getenv("SCAN_SCHEDULE_START", "22:00")
    SCAN_SCHEDULE_END: str = os.getenv("SCAN_SCHEDULE_END", "06:00")

    # Authentication
    @property
    def SECRET_KEY(self) -> str:
        return os.getenv("EYERIS_SECRET_KEY", "")


settings = Settings()
