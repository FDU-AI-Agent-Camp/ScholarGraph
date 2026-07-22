# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper CRUD and pipeline status backed by the persistence repositories."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.api.exceptions import ApiError
from backend.config import Settings, get_settings
from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import (
    PaperCreateResult,
    PaperDetail,
    PaperStatus,
    PaperStatusData,
    PaperSummary,
    PipelineStage,
)
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.head_refine_coordinator import HeadRefineCoordinator
from backend.services.paper_core_service import PaperCoreService
from backend.services.paper_detail_assembler import PaperDetailAssembler
from backend.services.paper_pipeline_ops import PaperPipelineOpsService
from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline
from backend.services.paper_service_wiring import (
    bind_paper_service,
    get_paper_service,
    reset_paper_service,
)
from backend.services.paper_warning_service import PaperWarningService
from backend.services.persistence_reset import reset_persistence_singletons
from backend.services.preview_graph_facade import PreviewGraphFacade

MAX_UPLOAD_BYTES = 32 * 1024 * 1024
UPLOAD_QUEUED_MESSAGE = "已接收 PDF，正在自动解构…"
__all__ = [
    "MAX_UPLOAD_BYTES",
    "UPLOAD_QUEUED_MESSAGE",
    "PaperService",
    "bind_paper_service",
    "get_paper_service",
    "reset_paper_service",
    "reset_persistence_singletons",
]


class PaperService:
    """DB-backed paper CRUD / composition root; pipeline ephemeral state lives in ``pipeline_runs``.

    Pipeline promote / snapshot / watchdog ops belong on ``PaperPipelineOpsService``.
    This facade keeps ``_pipeline_ops`` only for internal status assembly and upload seeding.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        paper_repo: PaperRepository | None = None,
        pipeline_repo: PipelineRepository | None = None,
        pipeline_ops: PaperPipelineOpsService | None = None,
        core_service: PaperCoreService | None = None,
        warning_service: PaperWarningService | None = None,
        head_refine_coordinator: HeadRefineCoordinator | None = None,
        preview_facade: PreviewGraphFacade | None = None,
        detail_assembler: PaperDetailAssembler | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._paper_repo = paper_repo or get_paper_repository()
        self._pipeline_repo = pipeline_repo or get_pipeline_repository()
        self._pipeline_ops = pipeline_ops or PaperPipelineOpsService(self._pipeline_repo)
        self._core = core_service or PaperCoreService(self._paper_repo)
        self._warnings = warning_service or PaperWarningService(self._pipeline_repo)
        self._head_refine = head_refine_coordinator or HeadRefineCoordinator(
            core_service=self._core,
            warning_service=self._warnings,
            paper_repo=self._paper_repo,
            pipeline_repo=self._pipeline_repo,
        )
        self._preview = preview_facade or PreviewGraphFacade(
            core_service=self._core,
            paper_repo=self._paper_repo,
            pipeline_repo=self._pipeline_repo,
        )
        self._detail = detail_assembler or PaperDetailAssembler(
            head_refine=self._head_refine,
            warning_service=self._warnings,
            preview_facade=self._preview,
        )

    async def bootstrap(self) -> None:
        """Optionally seed demo fixtures when ``SEED_DEMO_PAPERS=true`` and the DB is empty."""
        if self._settings.seed_demo_papers and await self._paper_repo.is_empty():
            from backend.services.paper_fixture_seed import seed_from_fixtures

            await seed_from_fixtures(self._paper_repo, self._pipeline_repo)

    async def set_active_run_id(self, paper_id: str, run_id: str | None) -> None:
        """Atomically activate a RAG index run, or clear it (``None`` / ``""`` → NULL)."""
        from backend.debug.async_hotpath_audit import record

        record("paper_service.set_active_run_id")
        await self.ensure_paper_exists(paper_id)
        await self._pipeline_repo.set_active_rag_run_id(paper_id, run_id)

    async def get_active_run_id(self, paper_id: str) -> str | None:
        """Return the currently active RAG index run id, or None when unset/cleared."""
        return await self._pipeline_repo.get_active_rag_run_id(paper_id)

    async def list_papers(
        self,
        *,
        paradigm: Paradigm | None = None,
        status: PaperStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PaperSummary], int]:
        await self.bootstrap()
        return await self._paper_repo.list(
            paradigm=paradigm,
            status=status,
            offset=offset,
            limit=limit,
        )

    async def get_paper(self, paper_id: str) -> PaperDetail:
        await self.bootstrap()
        paper = await self._paper_repo.get(paper_id)
        if paper is None:
            raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)
        return await self._detail.assemble(paper, paper_id)

    async def ensure_paper_exists(self, paper_id: str) -> None:
        paper = await self._paper_repo.get(paper_id)
        if paper is None:
            raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

    async def require_paper_for_pipeline(self, paper_id: str) -> None:
        """Raise pipeline ServiceError when the paper row is missing."""
        from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError

        if await self._paper_repo.get(paper_id) is None:
            msg = f"paper not found: {paper_id}"
            raise ServiceError(PIPELINE_FAILED_CODE, msg)

    def get_extract_quality_thresholds(self) -> tuple[float, float, float]:
        """Quality-gate thresholds used during pipeline finalize."""
        return (
            self._settings.extract_min_supports_rationale_coverage,
            self._settings.extract_max_isolated_node_ratio,
            self._settings.extract_max_generic_edge_ratio,
        )

    def compute_extractor_config_hash(self) -> str:
        from backend.services.extractor_config_fingerprint import compute_extractor_config_hash

        return compute_extractor_config_hash(self._settings)

    async def update_pipeline_classification(
        self,
        paper_id: str,
        classification: ParadigmClassification,
    ) -> None:
        await self._core.update_classification(paper_id, classification)

    async def update_pipeline_graph_path(self, paper_id: str, *, graph_path: str) -> None:
        await self._core.update_paths(paper_id, graph_path=graph_path)

    async def get_pipeline_graph_version(self, paper_id: str) -> str:
        return await self._core.get_graph_version(paper_id)

    async def update_pipeline_graph_version(
        self,
        paper_id: str,
        *,
        graph_version: str,
        extractor_config_hash: str,
    ) -> None:
        await self._core.update_graph_version(
            paper_id,
            graph_version=graph_version,
            extractor_config_hash=extractor_config_hash,
        )

    async def set_status_snapshot(
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
        """Persist validated pipeline status (called by PipelineStatusService)."""
        from backend.services.status_snapshot_guard import persist_status_snapshot

        return await persist_status_snapshot(
            self,
            paper_id,
            status=status,
            stage=stage,
            percent=percent,
            message=message,
            error_code=error_code,
            failed_during=failed_during,
            append_extract_warnings=append_extract_warnings,
        )

    async def update_pipeline_status(
        self,
        paper_id: str,
        *,
        status: PaperStatus,
        stage: PipelineStage | None,
        percent: int,
        message: str,
    ) -> PaperStatusData:
        """Legacy alias — validates contract then writes snapshot."""
        return await self.set_status_snapshot(
            paper_id,
            status=status,
            stage=stage,
            percent=percent,
            message=message,
        )

    async def complete_pipeline(
        self,
        paper_id: str,
        *,
        classification: ParadigmClassification,
        graph: UnifiedPaperGraph,
        full_text: str = "pipeline completion placeholder full text",
    ) -> None:
        from backend.services.graph_persistence_service import get_graph_persistence_service
        from backend.services.pipeline_completion_service import complete_paper_pipeline

        graph_path = await get_graph_persistence_service().save(graph)
        await complete_paper_pipeline(
            self,
            paper_id,
            classification=classification,
            graph=graph,
            graph_path=graph_path,
            full_text=full_text,
        )

    async def force_reextract(self, paper_id: str, *, force: bool = False) -> PaperStatusData:
        """Escape hatch: reset and re-schedule the pipeline for ``paper_id``."""
        await self.ensure_paper_exists(paper_id)
        from backend.services.reextract_service import get_reextract_service

        return await get_reextract_service().force_reextract(paper_id, force=force)

    async def delete_paper(
        self,
        paper_id: str,
        *,
        force: bool = False,
        auth_context: object | None = None,
    ) -> None:
        """Cascading physical delete (SQL + graph + Chroma + PDF).

        ``auth_context`` is reserved for Phase 3 multi-tenancy; V2 is single-node.
        """
        # TODO: Phase 3 multi-tenancy auth guard
        # await self._assert_ownership(paper_id, auth_context)
        _ = auth_context
        from backend.services.paper_delete_service import get_paper_delete_service

        await get_paper_delete_service().delete(paper_id, force=force)

    async def fail_pipeline(
        self,
        paper_id: str,
        *,
        message: str,
        error_code: str = "PIPELINE_FAILED",
        failed_during: PipelineStage | None = None,
    ) -> None:
        from backend.services.pipeline_status_service import get_pipeline_status_service

        await get_pipeline_status_service().mark_failed(
            paper_id,
            message=message,
            error_code=error_code,
            failed_during=failed_during,
        )

    async def apply_head_refine(
        self,
        paper_id: str,
        *,
        merged: IngestHead,
        classifier_input: str,
        warnings: list[str] | None = None,
    ) -> None:
        """Persist async head merge result; never changes pipeline failure state."""
        await self._head_refine.apply(
            paper_id,
            merged=merged,
            classifier_input=classifier_input,
            warnings=warnings,
        )

    async def get_refined_classifier_input(self, paper_id: str) -> str | None:
        return await self._head_refine.get_classifier_input(paper_id)

    async def get_refined_head(self, paper_id: str) -> IngestHead | None:
        return await self._head_refine.load_head(paper_id)

    async def clear_preview_graph(self, paper_id: str) -> None:
        """Clear the temporary preview graph for a specific paper pipeline."""
        await self._preview.clear(paper_id)

    async def save_preview_graph(self, paper_id: str, graph: UnifiedPaperGraph) -> None:
        await self.ensure_paper_exists(paper_id)
        await self._preview.save(paper_id, graph)

    async def mark_preview_available(self, paper_id: str) -> None:
        await self.ensure_paper_exists(paper_id)
        await self._preview.mark_available(paper_id)

    async def is_preview_available(self, paper_id: str) -> bool:
        return await self._preview.is_available(paper_id)

    async def get_preview_graph(self, paper_id: str) -> UnifiedPaperGraph | None:
        return await self._preview.get(paper_id)

    async def get_status(self, paper_id: str) -> PaperStatusData:
        await self.bootstrap()
        paper = await self.get_paper(paper_id)
        snapshot = await self._pipeline_ops.get_pipeline_snapshot(paper_id)
        if snapshot is not None:
            from backend.services.status_snapshot_guard import ensure_status_contract

            return await ensure_status_contract(self, paper_id, snapshot)
        if paper.status == PaperStatus.PENDING:
            return PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.PENDING,
                percent=0,
                stage=None,
                message="任务已创建，请轮询 status 接口",
                updated_at=paper.updated_at or paper.created_at,
            )
        raise ApiError(
            "PIPELINE_STATUS_UNAVAILABLE",
            "流水线状态尚未初始化",
            status_code=409,
        )

    async def get_graph(self, paper_id: str) -> UnifiedPaperGraph:
        paper = await self.get_paper(paper_id)
        if paper.status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS):
            from backend.graph.store import GraphStore

            graph = await asyncio.to_thread(GraphStore().load, paper_id)
            if graph is None:
                raise ApiError("GRAPH_NOT_READY", "图谱数据缺失", status_code=409)
            return graph

        if paper.preview_available or await self.is_preview_available(paper_id):
            preview = await self.get_preview_graph(paper_id)
            if preview is not None:
                return preview

        raise ApiError(
            "GRAPH_NOT_READY",
            "图谱尚未就绪，请轮询 status 接口",
            status_code=409,
        )

    async def create_from_upload(self, *, filename: str, content: bytes) -> PaperCreateResult:
        await self.bootstrap()
        if not filename.lower().endswith(".pdf"):
            raise ApiError("INGEST_FAILED", "仅支持 PDF 文件", status_code=400)
        if len(content) > MAX_UPLOAD_BYTES:
            raise ApiError("INGEST_FAILED", "文件超过 32MB 限制", status_code=400)
        if not content.startswith(b"%PDF"):
            raise ApiError("INGEST_FAILED", "无法解析 PDF 或文件已损坏", status_code=400)

        paper_id = str(uuid4())
        upload_dir = Path(self._settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"{paper_id}.pdf"
        dest.write_bytes(content)

        now = datetime.now(UTC)
        await self._paper_repo.create(
            paper_id,
            filename.removesuffix(".pdf"),
            str(dest),
            status=PaperStatus.PENDING,
        )
        await self._pipeline_ops.save_pipeline_snapshot(
            paper_id,
            PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.PENDING,
                percent=0,
                stage=None,
                message=UPLOAD_QUEUED_MESSAGE,
                updated_at=now,
            ),
        )
        schedule_paper_pipeline(paper_id, dest)
        return PaperCreateResult(
            paper_id=paper_id,
            status=PaperStatus.PENDING,
            message=UPLOAD_QUEUED_MESSAGE,
        )

