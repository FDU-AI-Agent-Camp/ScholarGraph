"""HTTP client for GROBID CRF fulltext TEI (§2.1 path B, long PDF)."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

PROCESS_FULLTEXT_PATH = "/api/processFulltextDocument"


async def fetch_grobid_tei(
    pdf_path: Path,
    *,
    settings: Settings | None = None,
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
    except Exception:
        logger.exception("GROBID request failed for %s", resolved.name)
        return None
