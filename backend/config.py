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

    @property
    def DATABASE_URL(self) -> str:
        if self.DB_HOST:
            # MariaDB / MySQL
            return (
                f"mysql+pymysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        # SQLite — default for Docker/Unraid deployments
        db_path = os.path.join("/data/db", "images.db")
        return f"sqlite:///{db_path}"

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

    # Thumbnails
    THUMBNAIL_DIR: str = os.path.join(os.path.dirname(__file__), "thumbnails")
    THUMBNAIL_SIZE: tuple[int, int] = (300, 300)

    # Authentication
    @property
    def SECRET_KEY(self) -> str:
        return os.getenv("EYERIS_SECRET_KEY", "")


settings = Settings()
