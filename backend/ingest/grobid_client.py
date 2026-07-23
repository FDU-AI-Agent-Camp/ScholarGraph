# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP client for GROBID CRF fulltext TEI (§2.1 path B, long PDF)."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

PROCESS_FULLTEXT_PATH = "/api/processFulltextDocument"
GROBID_ISALIVE_PATH = "/api/isalive"
GROBID_HEALTH_PROBE_SECONDS = 3.0


async def check_grobid_isalive(*, settings: Settings | None = None) -> bool:
    """Return True when GROBID sidecar responds to ``/api/isalive``."""
    cfg = settings or get_settings()
    url = f"{cfg.grobid_url.rstrip('/')}{GROBID_ISALIVE_PATH}"
    timeout = httpx.Timeout(GROBID_HEALTH_PROBE_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        if response.status_code != 200:
            return False
        return "true" in response.text.lower()
    except Exception as exc:  # noqa: BLE001 — health probe must not break callers; treat as unavailable
        logger.warning(
            "grobid_health_check_failed",
            extra={
                "url": url,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return False


async def fetch_grobid_tei(
    pdf_path: Path,
    *,
    settings: Settings | None = None,
    paper_id: str | None = None,
) -> str | None:
    """
    POST PDF to GROBID and return TEI XML text.

    Returns None on network/HTTP/timeout errors (caller falls back to rules/snippets).
    """
    cfg = settings or get_settings()
    base_url = cfg.grobid_url.rstrip("/")
    timeout = httpx.Timeout(cfg.grobid_timeout_seconds)
    resolved = pdf_path.resolve()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            with resolved.open("rb") as handle:
                response = await client.post(
                    f"{base_url}{PROCESS_FULLTEXT_PATH}",
                    files={"input": (resolved.name, handle, "application/pdf")},
                    data={
                        "consolidateHeader": "1",
                        "teiCoordinates": "0",
                    },
                )
            response.raise_for_status()
            tei = response.text.strip()
            if not tei:
                logger.warning("GROBID returned empty TEI for %s", resolved.name)
                return None
            return tei
    except Exception as exc:  # noqa: BLE001 — fallback to snippet/rules parser on GROBID sidecar failure
        logger.warning(
            "grobid_tei_extraction_failed",
            extra={
                "pdf_path": str(resolved),
                "paper_id": paper_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return None
