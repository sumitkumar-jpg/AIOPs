"""FastAPI entry point.

Serves the JSON API under /api and the static frontends (dashboard + admin).
CORS is configured from environment variables for Vercel production use.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS
from app.database.db import init_db
from app.routes import api

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Idempotent: creates tables if missing, never drops data.
    init_db()
    yield


app = FastAPI(
    title="AIOps Simulation Platform",
    description="Human-governed AIOps simulation: correlated telemetry, AI root-cause "
                "analysis, risk-ranked playbooks and a full audit trail.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router, prefix="/api")


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard/")


@app.get("/config.js")
def config_js():
    """Frontend runtime config (API base URL override for Vercel)."""
    cfg = FRONTEND_DIR / "config.js"
    if cfg.exists():
        return FileResponse(cfg, media_type="text/javascript")
    return Response("window.AIOPS_API_BASE = window.AIOPS_API_BASE || '';", media_type="text/javascript")


# Static frontends (dashboard + admin). Only mounted when the frontend folder is
# present, so a backend-only Railway deploy (frontend on Vercel) still boots.
if (FRONTEND_DIR / "dashboard").exists():
    app.mount("/dashboard", StaticFiles(directory=FRONTEND_DIR / "dashboard", html=True), name="dashboard")
if (FRONTEND_DIR / "admin").exists():
    app.mount("/admin", StaticFiles(directory=FRONTEND_DIR / "admin", html=True), name="admin")
