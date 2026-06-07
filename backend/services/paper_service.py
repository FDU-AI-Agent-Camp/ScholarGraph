"""Paper CRUD and pipeline status (skeleton with fixture seed data)."""

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from backend.api.exceptions import ApiError
from backend.config import Settings, get_settings
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
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
from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
DEFAULT_GRAPH_DATA_DIR = Path("./data/graphs")
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
UPLOAD_QUEUED_MESSAGE = "已接收 PDF，正在自动解构…"


def _to_failed_during(stage: PipelineStage | None) -> FailedDuringStage | None:
    if stage is None:
        return None
    return FailedDuringStage(stage.value)


class PaperService:
    """In-memory store seeded from docs/api/fixtures for local dev."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._papers: dict[str, PaperDetail] = {}
        self._status: dict[str, PaperStatusData] = {}
        self._refined_classifier_input: dict[str, str] = {}
        self._refined_head: dict[str, IngestHead] = {}
        self._head_refine_warnings: dict[str, list[str]] = {}
        self._extract_warnings: dict[str, list[str]] = {}
        self._seed_from_fixtures()

    def _seed_from_fixtures(self) -> None:
        list_path = FIXTURES_DIR / "papers-list.json"
        if not list_path.is_file():
            return
        payload = json.loads(list_path.read_text(encoding="utf-8"))
        detail_aliases = {
            "hss-001": "paper-detail-ready.json",
            "hss-failed-001": "paper-detail-failed.json",
        }
        for item in payload["data"]["items"]:
            paper_id = item["paper_id"]
            alias = detail_aliases.get(paper_id, f"paper-detail-{paper_id}.json")
            detail_path = FIXTURES_DIR / alias
            if detail_path.is_file():
                detail_payload = json.loads(detail_path.read_text(encoding="utf-8"))
                detail = PaperDetail.model_validate(detail_payload["data"])
            else:
                detail = PaperDetail.model_validate(item)
            self._papers[detail.paper_id] = detail
            graph_path = FIXTURES_DIR / f"graph-{paper_id}.json"
            if not graph_path.is_file() and detail.paradigm == Paradigm.HSS:
                graph_path = FIXTURES_DIR / "graph-hss.json"
            if graph_path.is_file():
                graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
                graph = UnifiedPaperGraph.model_validate(graph_payload["data"])
                graph = graph.model_copy(update={"paper_id": detail.paper_id})
                self._seed_graph_fixture_if_needed(graph)
            self._seed_status_for_detail(detail)

    def _seed_graph_fixture_if_needed(self, graph: UnifiedPaperGraph) -> None:
        """Persist demo fixture graphs only under the default local ``./data/graphs`` dir."""
        from backend.graph.store import GraphStore

        store = GraphStore()
        if store.load(graph.paper_id) is not None:
            return
        if store._base_dir.resolve() != DEFAULT_GRAPH_DATA_DIR.resolve():
            return
        store.save(graph)

    def _seed_status_for_detail(self, detail: PaperDetail) -> None:
        """Prefer per-paper status fixtures; otherwise synthesize api-contract snapshots."""
        status_path = FIXTURES_DIR / f"paper-status-{detail.paper_id}.json"
        if status_path.is_file():
            status_payload = json.loads(status_path.read_text(encoding="utf-8"))
            self._status[detail.paper_id] = PaperStatusData.model_validate(status_payload["data"])
            return

        updated_at = detail.updated_at or detail.created_at
        if detail.status == PaperStatus.READY:
            self._status[detail.paper_id] = PaperStatusData(
                paper_id=detail.paper_id,
                status=PaperStatus.READY,
                percent=100,
                stage=PipelineStage.READY,
                message="建图完成",
                updated_at=updated_at,
            )
        elif detail.status == PaperStatus.PROCESSING:
            self._status[detail.paper_id] = PaperStatusData(
                paper_id=detail.paper_id,
                status=PaperStatus.PROCESSING,
                percent=50,
                stage=PipelineStage.CLASSIFYING,
                message="正在识别范式与理论视角…",
                updated_at=updated_at,
            )
        elif detail.status == PaperStatus.PENDING:
            self._status[detail.paper_id] = PaperStatusData(
                paper_id=detail.paper_id,
                status=PaperStatus.PENDING,
                percent=0,
                stage=None,
                message="任务已创建，请轮询 status 接口",
                updated_at=updated_at,
            )

    async def list_papers(
        self,
        *,
        paradigm: Paradigm | None = None,
        status: PaperStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PaperSummary], int]:
        items = list(self._papers.values())
        if paradigm is not None:
            items = [p for p in items if p.paradigm == paradigm]
        if status is not None:
            items = [p for p in items if p.status == status]
        total = len(items)
        page = items[offset : offset + limit]
        return [PaperSummary.model_validate(p) for p in page], total

    async def get_paper(self, paper_id: str) -> PaperDetail:
        paper = self._papers.get(paper_id)
        if paper is None:
            raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)
        self._hydrate_head_refine_from_disk(paper_id)
        ingest_head = self._refined_head.get(paper_id)
        if ingest_head is None:
            return paper
        return paper.model_copy(update={"ingest_head": ingest_head})

    def ensure_paper_exists(self, paper_id: str) -> None:
        if paper_id not in self._papers:
            raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

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
    ) -> PaperStatusData:
        """Persist validated pipeline status (called by PipelineStatusService)."""
        from backend.services.pipeline_status_service import (
            validate_failed_error_fields,
            validate_status_contract,
        )

        validate_status_contract(status=status, stage=stage, percent=percent)
        validate_failed_error_fields(
            status=status,
            error_code=error_code,
            failed_during=failed_during,
        )
        self.ensure_paper_exists(paper_id)
        now = datetime.now(UTC)
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=percent,
            stage=stage,
            message=message,
            updated_at=now,
            error_code=error_code,
            failed_during=_to_failed_during(failed_during),
            head_refine_warnings=self.get_head_refine_warnings(paper_id),
            extract_warnings=self.get_extract_warnings(paper_id),
        )
        self._status[paper_id] = snapshot
        paper = self._papers[paper_id]
        self._papers[paper_id] = paper.model_copy(update={"status": status, "updated_at": now})
        return snapshot

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
        from backend.services.pipeline_status_service import validate_status_contract

        validate_status_contract(status=status, stage=stage, percent=percent)
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
    ) -> None:
        self.ensure_paper_exists(paper_id)
        now = datetime.now(UTC)
        paper = self._papers[paper_id]
        self._papers[paper_id] = paper.model_copy(
            update={
                "status": PaperStatus.READY,
                "paradigm": classification.paradigm,
                "classification": classification,
                "updated_at": now,
            },
        )
        from backend.graph.store import GraphStore
        from backend.services.pipeline_status_service import get_pipeline_status_service

        GraphStore().save(graph)
        get_pipeline_status_service().mark_ready(paper_id)

    def fail_pipeline(
        self,
        paper_id: str,
        *,
        message: str,
        error_code: str = "PIPELINE_FAILED",
        failed_during: PipelineStage | None = None,
    ) -> None:
        from backend.services.pipeline_status_service import get_pipeline_status_service

        _ = error_code
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
        self._refined_head[paper_id] = merged
        if classifier_input.strip():
            self._refined_classifier_input[paper_id] = classifier_input.strip()
        if warnings:
            self.record_head_refine_warnings(paper_id, warnings)
        if merged.title.strip() and paper_id in self._papers:
            paper = self._papers[paper_id]
            if paper.status == PaperStatus.PENDING:
                paper.title = merged.title.strip()
        self._persist_head_refine(
            paper_id,
            merged=merged,
            classifier_input=classifier_input,
            warnings=warnings,
        )

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

    def _hydrate_head_refine_from_disk(self, paper_id: str) -> None:
        if paper_id in self._refined_head:
            return
        from backend.graph.head_store import HeadStore

        record = HeadStore().load(paper_id)
        if record is None:
            return
        self._refined_head[paper_id] = record.merged
        if record.classifier_input.strip():
            self._refined_classifier_input[paper_id] = record.classifier_input.strip()
        if record.warnings and paper_id not in self._head_refine_warnings:
            self._head_refine_warnings[paper_id] = list(record.warnings)
            self._sync_head_refine_warnings_to_status(paper_id)

    def record_head_refine_warnings(self, paper_id: str, warnings: list[str]) -> None:
        """Merge head-refine warning codes and reflect them on the status snapshot."""
        if not warnings:
            return
        existing = self._head_refine_warnings.get(paper_id, [])
        merged: list[str] = list(existing)
        for code in warnings:
            if code not in merged:
                merged.append(code)
        self._head_refine_warnings[paper_id] = merged
        self._sync_head_refine_warnings_to_status(paper_id)

    def _sync_head_refine_warnings_to_status(self, paper_id: str) -> None:
        if paper_id not in self._status:
            return
        snapshot = self._status[paper_id]
        warnings = self.get_head_refine_warnings(paper_id)
        if snapshot.head_refine_warnings != warnings:
            self._status[paper_id] = snapshot.model_copy(update={"head_refine_warnings": warnings})

    def _enrich_status_with_head_refine_warnings(
        self,
        snapshot: PaperStatusData,
        paper_id: str,
    ) -> PaperStatusData:
        warnings = self.get_head_refine_warnings(paper_id)
        if snapshot.head_refine_warnings == warnings:
            return snapshot
        return snapshot.model_copy(update={"head_refine_warnings": warnings})

    def get_refined_classifier_input(self, paper_id: str) -> str | None:
        self._hydrate_head_refine_from_disk(paper_id)
        return self._refined_classifier_input.get(paper_id)

    def get_refined_head(self, paper_id: str) -> IngestHead | None:
        self._hydrate_head_refine_from_disk(paper_id)
        return self._refined_head.get(paper_id)

    def get_head_refine_warnings(self, paper_id: str) -> list[str]:
        return list(self._head_refine_warnings.get(paper_id, ()))

    def record_extract_warnings(self, paper_id: str, warnings: list[str]) -> None:
        """Merge extract degrade codes and reflect them on the status snapshot."""
        if not warnings:
            return
        existing = self._extract_warnings.get(paper_id, [])
        merged: list[str] = list(existing)
        for code in warnings:
            if code not in merged:
                merged.append(code)
        self._extract_warnings[paper_id] = merged
        self._sync_extract_warnings_to_status(paper_id)

    def _sync_extract_warnings_to_status(self, paper_id: str) -> None:
        if paper_id not in self._status:
            return
        snapshot = self._status[paper_id]
        warnings = self.get_extract_warnings(paper_id)
        if snapshot.extract_warnings != warnings:
            self._status[paper_id] = snapshot.model_copy(update={"extract_warnings": warnings})

    def _enrich_status_with_extract_warnings(
        self,
        snapshot: PaperStatusData,
        paper_id: str,
    ) -> PaperStatusData:
        warnings = self.get_extract_warnings(paper_id)
        if snapshot.extract_warnings == warnings:
            return snapshot
        return snapshot.model_copy(update={"extract_warnings": warnings})

    def get_extract_warnings(self, paper_id: str) -> list[str]:
        return list(self._extract_warnings.get(paper_id, ()))

    def _enrich_status_snapshot(self, snapshot: PaperStatusData, paper_id: str) -> PaperStatusData:
        return self._enrich_status_with_extract_warnings(
            self._enrich_status_with_head_refine_warnings(snapshot, paper_id),
            paper_id,
        )

    async def get_status(self, paper_id: str) -> PaperStatusData:
        paper = await self.get_paper(paper_id)
        if paper_id in self._status:
            return self._enrich_status_snapshot(self._status[paper_id], paper_id)
        if paper.status == PaperStatus.PENDING:
            return self._enrich_status_snapshot(
                PaperStatusData(
                    paper_id=paper_id,
                    status=PaperStatus.PENDING,
                    percent=0,
                    stage=None,
                    message="任务已创建，请轮询 status 接口",
                    updated_at=paper.updated_at or paper.created_at,
                ),
                paper_id,
            )
        raise ApiError(
            "PIPELINE_STATUS_UNAVAILABLE",
            "流水线状态尚未初始化",
            status_code=409,
        )

    async def get_graph(self, paper_id: str) -> UnifiedPaperGraph:
        paper = await self.get_paper(paper_id)
        if paper.status != PaperStatus.READY:
            raise ApiError(
                "GRAPH_NOT_READY",
                "图谱尚未就绪，请轮询 status 接口",
                status_code=409,
            )
        from backend.graph.store import GraphStore

        graph = GraphStore().load(paper_id)
        if graph is None:
            raise ApiError("GRAPH_NOT_READY", "图谱数据缺失", status_code=409)
        return graph

    async def create_from_upload(self, *, filename: str, content: bytes) -> PaperCreateResult:
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
        detail = PaperDetail(
            paper_id=paper_id,
            title=filename.removesuffix(".pdf"),
            status=PaperStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._papers[paper_id] = detail
        self._status[paper_id] = PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message=UPLOAD_QUEUED_MESSAGE,
            updated_at=now,
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
