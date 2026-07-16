"""Optional Vue SPA static hosting for single-container deployments."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# Paths owned by FastAPI / OpenAPI; SPA catch-all must not claim them.
_SPA_RESERVED_PREFIXES: tuple[str, ...] = (
    "api",
    "docs",
    "redoc",
    "openapi.json",
)


def resolve_frontend_dist_dir() -> Path | None:
    """Return ``frontend/dist`` when the production build is present."""
    repo_root = Path(__file__).resolve().parents[2]
    dist_dir = repo_root / "frontend" / "dist"
    if not dist_dir.is_dir() or not (dist_dir / "index.html").is_file():
        return None
    return dist_dir


def mount_frontend_spa(app: FastAPI, *, dist_dir: Path | None = None) -> bool:
    """
    Serve the Vite build from ``frontend/dist`` (same-origin with ``/api/v1``).

    Returns True when SPA routes were registered. No-op when dist is missing
    (local API-only / pytest).
    """
    resolved = dist_dir if dist_dir is not None else resolve_frontend_dist_dir()
    if resolved is None or not (resolved / "index.html").is_file():
        logger.info("frontend/dist not found; SPA static hosting disabled")
        return False

    index_html = resolved / "index.html"
    assets_dir = resolved / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/")
    async def spa_root() -> FileResponse:
        return FileResponse(index_html)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if _is_reserved_spa_path(full_path):
            # Should not normally be reached (API/docs registered earlier).
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = resolved / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_html)

    logger.info("SPA static hosting enabled from %s", resolved)
    return True


def _is_reserved_spa_path(full_path: str) -> bool:
    normalized = full_path.lstrip("/")
    for prefix in _SPA_RESERVED_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return True
    return False
