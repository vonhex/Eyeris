from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import settings

connect_args = {}
_is_sqlite = "sqlite" in settings.DATABASE_URL
if _is_sqlite:
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30  # busy_timeout: wait up to 30s instead of failing immediately

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=not _is_sqlite,
    pool_recycle=3600 if not _is_sqlite else -1,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")       # readers never block writers, writers never block readers
        cursor.execute("PRAGMA synchronous=NORMAL")     # safe with WAL, avoids fsync on every commit
        cursor.execute("PRAGMA cache_size=-32000")      # 32MB page cache
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
