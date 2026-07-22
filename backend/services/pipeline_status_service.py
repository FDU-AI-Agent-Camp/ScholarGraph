# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Pipeline status/stage/percent updates aligned with api-contract §2."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import FailedDuringStage, PaperStatus, PaperStatusData, PipelineStage

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

PROCESSING_STAGES: frozenset[PipelineStage] = frozenset(
    {
        PipelineStage.INGESTING,
        PipelineStage.HEAD_REFINING,
        PipelineStage.CLASSIFYING,
        PipelineStage.EXTRACTING,
        PipelineStage.STORING,
    },
)

DEFAULT_STAGE_MESSAGES: dict[PipelineStage, str] = {
    PipelineStage.INGESTING: "正在解析 PDF",
    PipelineStage.HEAD_REFINING: "正在精炼文档头部…",
    PipelineStage.CLASSIFYING: "正在识别范式与理论视角…",
    PipelineStage.EXTRACTING: "正在抽取逻辑图谱",
    PipelineStage.STORING: "正在写入图谱存储",
    PipelineStage.INDEXING: "图谱已就绪，正在构建向量索引…",
    PipelineStage.READY: "建图完成",
    PipelineStage.FAILED: "流水线失败",
}


def validate_status_contract(
    *,
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
) -> None:
    """Enforce api-contract rules for status vs stage vs percent."""
    if status == PaperStatus.PENDING:
        if stage is not None:
            msg = "status=pending 时 stage 必须为 null"
            raise ValueError(msg)
        if percent != 0:
            msg = "status=pending 时 percent 必须为 0"
            raise ValueError(msg)
        return

    if status == PaperStatus.PROCESSING:
        if stage is None or stage not in PROCESSING_STAGES:
            msg = f"status=processing 时 stage 必须为 {sorted(s.value for s in PROCESSING_STAGES)} 之一"
            raise ValueError(msg)
        expected_percent = STAGE_PERCENT[stage]
        if percent != expected_percent:
            msg = f"stage={stage.value} 时 percent 必须为 {expected_percent}"
            raise ValueError(msg)
        return

    if status == PaperStatus.INDEXING:
        if stage != PipelineStage.INDEXING or percent != STAGE_PERCENT[PipelineStage.INDEXING]:
            raise ValueError("status=indexing 时 stage=indexing 且 percent=98")
        return

    if status == PaperStatus.READY:
        if stage != PipelineStage.READY or percent != 100:
            raise ValueError("status=ready 时 stage=ready 且 percent=100")
        return

    if status == PaperStatus.READY_WITH_WARNINGS:
        if stage != PipelineStage.READY or percent != 100:
            raise ValueError("status=ready_with_warnings 时 stage=ready 且 percent=100")
        return

    if status == PaperStatus.FAILED:
        if stage != PipelineStage.FAILED or percent != 0:
            raise ValueError("status=failed 时 stage=failed 且 percent=0")
        return

    raise ValueError(f"未知 status: {status}")


def _coerce_failed_during(
    failed_during: FailedDuringStage | PipelineStage | None,
) -> PipelineStage | None:
    if failed_during is None:
        return None
    return PipelineStage(failed_during.value)


def validate_failed_error_fields(
    *,
    status: PaperStatus,
    error_code: str | None,
    failed_during: FailedDuringStage | PipelineStage | None,
) -> None:
    """failed 态必须带 error_code；failed_during 仅允许处理中阶段。"""
    failed_stage = _coerce_failed_during(failed_during)
    if status == PaperStatus.FAILED:
        if not error_code or not error_code.strip():
            raise ValueError("status=failed 时 error_code 必填")
        if failed_stage is not None and failed_stage not in PROCESSING_STAGES:
            msg = f"failed_during 必须为 {sorted(s.value for s in PROCESSING_STAGES)} 之一"
            raise ValueError(msg)
        return

    if error_code is not None or failed_stage is not None:
        raise ValueError("非 failed 状态不得包含 error_code / failed_during")


class PipelineStatusService:
    """Single entry for workflow progress writes consumed by GET .../status."""

    def __init__(self, paper_service: PaperService | None = None) -> None:
        self._paper_service = paper_service

    def _resolve_paper_service(self) -> PaperService:
        if self._paper_service is not None:
            return self._paper_service
        from backend.services.paper_service import get_paper_service

        return get_paper_service()

    async def start_processing(self, paper_id: str, *, message: str | None = None) -> PaperStatusData:
        """pending → processing，进入 ingesting（percent=20）。"""
        return await self.advance_stage(
            paper_id,
            PipelineStage.INGESTING,
            message=message or "流水线已启动，正在解析 PDF",
        )

    async def advance_stage(
        self,
        paper_id: str,
        stage: PipelineStage,
        *,
        message: str | None = None,
    ) -> PaperStatusData:
        if stage not in PROCESSING_STAGES:
            raise ValueError(f"advance_stage 不接受终态 stage: {stage}")
        percent = STAGE_PERCENT[stage]
        msg = message or DEFAULT_STAGE_MESSAGES[stage]
        return await self._apply(
            paper_id,
            status=PaperStatus.PROCESSING,
            stage=stage,
            percent=percent,
            message=msg,
        )

    async def mark_indexing(
        self,
        paper_id: str,
        *,
        message: str | None = None,
        append_extract_warnings: list[str] | None = None,
    ) -> PaperStatusData:
        """Graph is persisted; wait for RAG VectorStore before terminal ready (P10)."""
        return await self._apply(
            paper_id,
            status=PaperStatus.INDEXING,
            stage=PipelineStage.INDEXING,
            percent=STAGE_PERCENT[PipelineStage.INDEXING],
            message=message or DEFAULT_STAGE_MESSAGES[PipelineStage.INDEXING],
            append_extract_warnings=append_extract_warnings,
        )

    async def mark_ready(
        self,
        paper_id: str,
        *,
        message: str | None = None,
        append_extract_warnings: list[str] | None = None,
    ) -> PaperStatusData:
        return await self._apply(
            paper_id,
            status=PaperStatus.READY,
            stage=PipelineStage.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            message=message or DEFAULT_STAGE_MESSAGES[PipelineStage.READY],
            append_extract_warnings=append_extract_warnings,
        )

    async def mark_ready_with_warnings(
        self,
        paper_id: str,
        *,
        message: str | None = None,
        append_extract_warnings: list[str] | None = None,
    ) -> PaperStatusData:
        return await self._apply(
            paper_id,
            status=PaperStatus.READY_WITH_WARNINGS,
            stage=PipelineStage.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            message=message or "建图完成，但图谱置信度未达门控，请复核",
            append_extract_warnings=append_extract_warnings,
        )

    async def mark_failed(
        self,
        paper_id: str,
        *,
        message: str,
        error_code: str,
        failed_during: PipelineStage | None = None,
    ) -> PaperStatusData:
        return await self._apply(
            paper_id,
            status=PaperStatus.FAILED,
            stage=PipelineStage.FAILED,
            percent=STAGE_PERCENT[PipelineStage.FAILED],
            message=message,
            error_code=error_code,
            failed_during=failed_during,
        )

    async def _apply(
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
        from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
        from backend.services.paper_status_transitions import assert_status_transition_allowed

        validate_status_contract(status=status, stage=stage, percent=percent)
        validate_failed_error_fields(
            status=status,
            error_code=error_code,
            failed_during=failed_during,
        )

        existing = await get_paper_pipeline_ops_service().get_pipeline_snapshot(paper_id)
        if existing is not None:
            assert_status_transition_allowed(existing.status, status, paper_id=paper_id)
        return await self._resolve_paper_service().set_status_snapshot(
            paper_id,
            status=status,
            stage=stage,
            percent=percent,
            message=message,
            error_code=error_code,
            failed_during=failed_during,
            append_extract_warnings=append_extract_warnings,
        )


@lru_cache
def get_pipeline_status_service() -> PipelineStatusService:
    return PipelineStatusService()
