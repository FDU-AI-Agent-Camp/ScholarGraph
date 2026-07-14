"""Paper CRUD and pipeline status backed by the persistence repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from backend.api.exceptions import ApiError
from backend.config import Settings, get_settings
from backend.db.base import reset_database_caches
from backend.repositories import run_async
from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.repositories.pipeline_sync import reset_pipeline_sync_engine
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead, PersistedHeadRefine
from backend.schemas.paper import (
    FailedDuringStage,
    PaperCreateResult,
    PaperDetail,
    PaperStatus,
    PaperStatusData,
    PaperSummary,
    PipelineStage,
)
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_pipeline_ops import PaperPipelineOpsMixin
from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline

MAX_UPLOAD_BYTES = 32 * 1024 * 1024
UPLOAD_QUEUED_MESSAGE = "已接收 PDF，正在自动解构…"


def _to_failed_during(stage: PipelineStage | None) -> FailedDuringStage | None:
    if stage is None:
        return None
    return FailedDuringStage(stage.value)


def reset_persistence_singletons() -> None:
    """Clear cached settings, DB engines, repositories, and service singletons."""
    get_settings.cache_clear()
    reset_database_caches()
    get_paper_repository.cache_clear()
    get_pipeline_repository.cache_clear()
    reset_pipeline_sync_engine()
    get_paper_service.cache_clear()
    from backend.services.graph_persistence_service import get_graph_persistence_service
    from backend.services.pipeline_completion_service import get_pipeline_completion_service
    from backend.services.pipeline_status_service import get_pipeline_status_service

    get_graph_persistence_service.cache_clear()
    get_pipeline_status_service.cache_clear()
    get_pipeline_completion_service.cache_clear()
    from backend.events.bus import reset_event_bus_cache

    reset_event_bus_cache()


class PaperService(PaperPipelineOpsMixin):
    """DB-backed paper store; pipeline ephemeral state lives in ``pipeline_runs``.

    External RAG / watchdog callers must use ``PaperPipelineOpsMixin`` public
    methods (e.g. ``promote_paper_to_terminal_status``) instead of ``_pipeline_repo``.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        paper_repo: PaperRepository | None = None,
        pipeline_repo: PipelineRepository | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._paper_repo = paper_repo or get_paper_repository()
        self._pipeline_repo = pipeline_repo or get_pipeline_repository()

    async def bootstrap(self) -> None:
        """Optionally seed demo fixtures when ``SEED_DEMO_PAPERS=true`` and the DB is empty."""
        if self._settings.seed_demo_papers and await self._paper_repo.is_empty():
            from backend.services.paper_fixture_seed import seed_from_fixtures

            await seed_from_fixtures(self._paper_repo, self._pipeline_repo)

    def set_active_run_id(self, paper_id: str, run_id: str | None) -> None:
        """Atomically activate a RAG index run, or clear it (``None`` / ``""`` → NULL)."""
        self.ensure_paper_exists(paper_id)
        run_async(self._pipeline_repo.set_active_rag_run_id(paper_id, run_id))

    def get_active_run_id(self, paper_id: str) -> str | None:
        """Return the currently active RAG index run id, or None when unset/cleared."""
        return run_async(self._pipeline_repo.get_active_rag_run_id(paper_id))

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
        return self._enrich_paper_detail(paper, paper_id)

    def _enrich_paper_detail(self, paper: PaperDetail, paper_id: str) -> PaperDetail:
        """Attach optional ingest head, preview flag, and degrade codes for detail API (X17)."""
        self._sync_head_refine_warnings_from_disk(paper_id)
        ingest_head = self._load_ingest_head(paper_id)
        snapshot = run_async(self._pipeline_repo.get_latest(paper_id))
        extract_warnings: list[str] = []
        classify_warnings: list[str] = []
        if snapshot is not None:
            extract_warnings = snapshot.extract_warnings
            classify_warnings = snapshot.classify_warnings
        return paper.model_copy(
            update={
                "ingest_head": ingest_head,
                "preview_available": paper.preview_available or self.is_preview_available(paper_id),
                "extract_warnings": extract_warnings,
                "classify_warnings": classify_warnings,
            },
        )

    def ensure_paper_exists(self, paper_id: str) -> None:
        paper = run_async(self._paper_repo.get(paper_id))
        if paper is None:
            raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

    def require_paper_for_pipeline(self, paper_id: str) -> None:
        """Raise pipeline ServiceError when the paper row is missing."""
        from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError

        if run_async(self._paper_repo.get(paper_id)) is None:
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

    def update_pipeline_classification(
        self,
        paper_id: str,
        classification: ParadigmClassification,
    ) -> None:
        run_async(self._paper_repo.update_classification(paper_id, classification))

    def update_pipeline_graph_path(self, paper_id: str, *, graph_path: str) -> None:
        run_async(self._paper_repo.update_paths(paper_id, graph_path=graph_path))

    def get_pipeline_graph_version(self, paper_id: str) -> str:
        return run_async(self._paper_repo.get_graph_version(paper_id))

    def update_pipeline_graph_version(
        self,
        paper_id: str,
        *,
        graph_version: str,
        extractor_config_hash: str,
    ) -> None:
        run_async(
            self._paper_repo.update_graph_version(
                paper_id,
                graph_version=graph_version,
                extractor_config_hash=extractor_config_hash,
            ),
        )

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
        """Persist validated pipeline status (called by PipelineStatusService)."""
        from backend.services.status_snapshot_guard import persist_status_snapshot

        return persist_status_snapshot(
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

    def update_pipeline_status(
        self,
        paper_id: str,
        *,
        status: PaperStatus,
        stage: PipelineStage | None,
        percent: int,
        message: str,
    ) -> PaperStatusData:
        """Legacy alias — validates contract then writes snapshot."""
        return self.set_status_snapshot(
            paper_id,
            status=status,
            stage=stage,
            percent=percent,
            message=message,
        )

    def complete_pipeline(
        self,
        paper_id: str,
        *,
        classification: ParadigmClassification,
        graph: UnifiedPaperGraph,
        full_text: str = "pipeline completion placeholder full text",
    ) -> None:
        from backend.services.graph_persistence_service import get_graph_persistence_service
        from backend.services.pipeline_completion_service import complete_paper_pipeline

        graph_path = get_graph_persistence_service().save(graph)
        complete_paper_pipeline(
            self,
            paper_id,
            classification=classification,
            graph=graph,
            graph_path=graph_path,
            full_text=full_text,
        )

    async def force_reextract(self, paper_id: str) -> PaperStatusData:
        """Escape hatch: reset and re-schedule the pipeline for ``paper_id``."""
        self.ensure_paper_exists(paper_id)
        from backend.services.reextract_service import force_reextract

        return force_reextract(self, paper_id)

    def fail_pipeline(
        self,
        paper_id: str,
        *,
        message: str,
        error_code: str = "PIPELINE_FAILED",
        failed_during: PipelineStage | None = None,
    ) -> None:
        from backend.services.pipeline_status_service import get_pipeline_status_service

        get_pipeline_status_service().mark_failed(
            paper_id,
            message=message,
            error_code=error_code,
            failed_during=failed_during,
        )

    def apply_head_refine(
        self,
        paper_id: str,
        *,
        merged: IngestHead,
        classifier_input: str,
        warnings: list[str] | None = None,
    ) -> None:
        """Persist async head merge result; never changes pipeline failure state."""
        if warnings:
            self.record_head_refine_warnings(paper_id, warnings)
        paper = run_async(self._paper_repo.get(paper_id))
        if merged.title.strip() and paper is not None and paper.status == PaperStatus.PENDING:
            run_async(self._paper_repo.update_title(paper_id, merged.title.strip()))
        self._persist_head_refine(
            paper_id,
            merged=merged,
            classifier_input=classifier_input,
            warnings=warnings,
        )

    def _load_ingest_head(self, paper_id: str) -> IngestHead | None:
        from backend.graph.head_store import HeadStore

        record = HeadStore().load(paper_id)
        return record.merged if record is not None else None

    def _load_head_refine_record(self, paper_id: str) -> PersistedHeadRefine | None:
        from backend.graph.head_store import HeadStore

        return HeadStore().load(paper_id)

    def _sync_head_refine_warnings_from_disk(self, paper_id: str) -> None:
        from backend.graph.head_store import HeadStore

        record = HeadStore().load(paper_id)
        if record is None or not record.warnings:
            return
        snapshot = run_async(self._pipeline_repo.get_latest(paper_id))
        if snapshot is not None and snapshot.head_refine_warnings:
            return
        self.record_head_refine_warnings(paper_id, list(record.warnings))

    def _persist_head_refine(
        self,
        paper_id: str,
        *,
        merged: IngestHead,
        classifier_input: str,
        warnings: list[str] | None,
    ) -> None:
        from backend.graph.head_store import HeadStore

        HeadStore().save(
            paper_id,
            merged=merged,
            classifier_input=classifier_input,
            warnings=warnings,
        )
        head_path = str(HeadStore()._path(paper_id))
        run_async(self._paper_repo.update_paths(paper_id, head_path=head_path))

    def get_refined_classifier_input(self, paper_id: str) -> str | None:
        record = self._load_head_refine_record(paper_id)
        if record is None:
            return None
        stripped = record.classifier_input.strip()
        return stripped or None

    def get_refined_head(self, paper_id: str) -> IngestHead | None:
        return self._load_ingest_head(paper_id)

    def record_head_refine_warnings(self, paper_id: str, warnings: list[str]) -> None:
        if not warnings:
            return
        run_async(
            self._pipeline_repo.record_warnings(paper_id, head_refine=warnings),
        )

    def get_head_refine_warnings(self, paper_id: str) -> list[str]:
        snapshot = run_async(self._pipeline_repo.get_latest(paper_id))
        if snapshot is None:
            return []
        return list(snapshot.head_refine_warnings)

    def record_extract_warnings(self, paper_id: str, warnings: list[str]) -> None:
        if not warnings:
            return
        run_async(self._pipeline_repo.record_warnings(paper_id, extract=warnings))

    def clear_preview_graph(self, paper_id: str) -> None:
        """Clear the temporary preview graph for a specific paper pipeline."""
        run_async(self._pipeline_repo.clear_preview_graph(paper_id))

    def record_classify_warnings(self, paper_id: str, warnings: list[str]) -> None:
        if not warnings:
            return
        run_async(self._pipeline_repo.record_warnings(paper_id, classify=warnings))

    def get_classify_warnings(self, paper_id: str) -> list[str]:
        snapshot = run_async(self._pipeline_repo.get_latest(paper_id))
        if snapshot is None:
            return []
        return list(snapshot.classify_warnings)

    def get_extract_warnings(self, paper_id: str) -> list[str]:
        snapshot = run_async(self._pipeline_repo.get_latest(paper_id))
        if snapshot is None:
            return []
        return list(snapshot.extract_warnings)

    def save_preview_graph(self, paper_id: str, graph: UnifiedPaperGraph) -> None:
        self.ensure_paper_exists(paper_id)
        run_async(self._pipeline_repo.save_preview_graph(paper_id, graph))

    def mark_preview_available(self, paper_id: str) -> None:
        self.ensure_paper_exists(paper_id)
        run_async(self._paper_repo.mark_preview_available(paper_id))

    def is_preview_available(self, paper_id: str) -> bool:
        paper = run_async(self._paper_repo.get(paper_id))
        if paper is not None and paper.preview_available:
            return True
        return run_async(self._pipeline_repo.get_preview_graph(paper_id)) is not None

    def get_preview_graph(self, paper_id: str) -> UnifiedPaperGraph | None:
        return run_async(self._pipeline_repo.get_preview_graph(paper_id))

    def clear_ephemeral_pipeline_state(self, paper_id: str) -> None:
        run_async(self._pipeline_repo.clear_ephemeral_pipeline_state(paper_id))

    async def get_status(self, paper_id: str) -> PaperStatusData:
        await self.bootstrap()
        paper = await self.get_paper(paper_id)
        snapshot = await self._pipeline_repo.get_latest(paper_id)
        if snapshot is not None:
            from backend.services.status_snapshot_guard import ensure_status_contract

            return ensure_status_contract(self, paper_id, snapshot)
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

            graph = GraphStore().load(paper_id)
            if graph is None:
                raise ApiError("GRAPH_NOT_READY", "图谱数据缺失", status_code=409)
            return graph

        if paper.preview_available or self.is_preview_available(paper_id):
            preview = self.get_preview_graph(paper_id)
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
        await self._pipeline_repo.save_status(
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


@lru_cache
def get_paper_service() -> PaperService:
    return PaperService()
