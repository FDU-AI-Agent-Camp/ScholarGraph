# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Ingest service facade (BE-1 implements backend.ingest)."""

from functools import lru_cache
from pathlib import Path

from backend.ingest.pdf import IngestResult, ingest_pdf
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError


class IngestService:
    """PDF ingestion; workflow nodes call this instead of backend.ingest directly."""

    async def ingest(self, pdf_path: Path, *, paper_id: str) -> IngestResult:
        try:
            return await ingest_pdf(pdf_path, paper_id=paper_id)
        except NotImplementedError as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, str(exc)) from exc
        except Exception as exc:
            raise ServiceError("INGEST_FAILED", f"PDF 解析失败: {exc}") from exc


@lru_cache
def get_ingest_service() -> IngestService:
    return IngestService()
