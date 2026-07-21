# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Explicit sync facade over async ``PaperService`` (Phase-3 peripheral bridge).

LangGraph workflow nodes in this repo are already ``async def`` and must
``await`` PaperService directly. Use this adapter only from:

- CLI / scripts that cannot enter an async context
- OS-thread / sync-only peripheral entry points
- tests that intentionally exercise the unidirectional bridge

Never import this module from ``backend/services`` or ``backend/patrol``.
"""

from __future__ import annotations

from backend.repositories.async_bridge import run_async
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_service import PaperService, get_paper_service


class PaperServiceSyncAdapter:
    """Unidirectional peripheral bridge: sync caller → ``run_async`` → PaperService."""

    def __init__(self, paper_service: PaperService | None = None) -> None:
        self._paper_service = paper_service or get_paper_service()

    def get_active_run_id(self, paper_id: str) -> str | None:
        return run_async(self._paper_service.get_active_run_id(paper_id))

    def set_active_run_id(self, paper_id: str, run_id: str | None) -> None:
        run_async(self._paper_service.set_active_run_id(paper_id, run_id))

    def get_status(self, paper_id: str) -> PaperStatusData:
        return run_async(self._paper_service.get_status(paper_id))

    def set_status_snapshot(
        self,
        paper_id: str,
        *,
        status: PaperStatus,
        stage: PipelineStage | None,
        percent: int,
        message: str,
        error_code: str | None = None,
        failed_during: PipelineStage | None = None,
        append_extract_warnings: list[str] | None = None,
    ) -> PaperStatusData:
        return run_async(
            self._paper_service.set_status_snapshot(
                paper_id,
                status=status,
                stage=stage,
                percent=percent,
                message=message,
                error_code=error_code,
                failed_during=failed_during,
                append_extract_warnings=append_extract_warnings,
            )
        )

    def fail_pipeline(
        self,
        paper_id: str,
        *,
        message: str,
        error_code: str,
        failed_during: PipelineStage | None = None,
    ) -> None:
        run_async(
            self._paper_service.fail_pipeline(
                paper_id,
                message=message,
                error_code=error_code,
                failed_during=failed_during,
            )
        )

    def get_pipeline_graph_version(self, paper_id: str) -> str:
        return run_async(self._paper_service.get_pipeline_graph_version(paper_id))
