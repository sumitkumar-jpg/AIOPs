"""Application configuration loaded from environment variables (.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the backend directory (safe no-op when missing).
load_dotenv(BASE_DIR / ".env")


def _as_bool(value, default=False):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    # Local default: SQLite stored next to the backend (never committed).
    DATABASE_URL = f"sqlite:///{(BASE_DIR / 'data' / 'aiops.db').as_posix()}"

# Railway exposes postgres:// URLs; SQLAlchemy wants postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

IS_SQLITE = DATABASE_URL.startswith("sqlite")


# --------------------------------------------------------------------------- #
# AI / Groq
# --------------------------------------------------------------------------- #
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "45"))

AI_AVAILABLE = bool(GROQ_API_KEY)


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #
EXTRA_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "").split(",")
    if o.strip()
]

if EXTRA_CORS_ORIGINS:
    CORS_ORIGINS = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ] + EXTRA_CORS_ORIGINS
else:
    # No auth in this demo: allow all origins, credentials are not used.
    CORS_ORIGINS = ["*"]


# --------------------------------------------------------------------------- #
# Runtime behaviour
# --------------------------------------------------------------------------- #
RECOVERY_DURATION_SECONDS = float(os.getenv("RECOVERY_DURATION_SECONDS", "12"))
AUTO_EXECUTE_LOW_RISK = _as_bool(os.getenv("AUTO_EXECUTE_LOW_RISK", "true"))
