"""Database engine/session setup. SQLite locally, PostgreSQL via DATABASE_URL."""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL, IS_SQLITE

# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
engine_options = {"pool_pre_ping": True}
connect_args = {}

if IS_SQLITE:
    # Ensure the SQLite parent directory exists before SQLAlchemy opens the file.
    db_path = DATABASE_URL.split("sqlite:///", 1)[1]
    if db_path and not db_path.startswith(":memory:"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # SQLite connections can be shared across FastAPI threads in this demo.
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db() -> None:
    """Create tables idempotently. Safe to call on every startup."""
    # Import models so their tables are registered on Base.metadata.
    import app.models.entities  # noqa: F401

    Base.metadata.create_all(bind=engine)


def ping_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_db():
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
