"""Paper CRUD and pipeline status (skeleton with fixture seed data)."""

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from backend.api.exceptions import ApiError
from backend.config import Settings, get_settings
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import (
    PaperCreateResult,
    PaperDetail,
    PaperStatus,
    PaperStatusData,
    PaperSummary,
    PipelineStage,
)
from backend.schemas.paradigm import Paradigm, ParadigmClassification

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
MAX_UPLOAD_BYTES = 32 * 1024 * 1024


class PaperService:
    """In-memory store seeded from docs/api/fixtures for local dev."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._papers: dict[str, PaperDetail] = {}
        self._graphs: dict[str, UnifiedPaperGraph] = {}
        self._status: dict[str, PaperStatusData] = {}
        self._seed_from_fixtures()

    def _seed_from_fixtures(self) -> None:
        list_path = FIXTURES_DIR / "papers-list.json"
        if not list_path.is_file():
            return
        payload = json.loads(list_path.read_text(encoding="utf-8"))
        detail_aliases = {"hss-001": "paper-detail-ready.json"}
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
                self._graphs[detail.paper_id] = graph.model_copy(update={"paper_id": detail.paper_id})

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
        return paper

    def ensure_paper_exists(self, paper_id: str) -> None:
        if paper_id not in self._papers:
            raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

    def update_pipeline_status(
        self,
        paper_id: str,
        *,
        status: PaperStatus,
        stage: PipelineStage | None,
        percent: int,
        message: str,
    ) -> None:
        self.ensure_paper_exists(paper_id)
        now = datetime.now(UTC)
        self._status[paper_id] = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=percent,
            stage=stage,
            message=message,
            updated_at=now,
        )
        paper = self._papers[paper_id]
        self._papers[paper_id] = paper.model_copy(update={"status": status, "updated_at": now})

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
        self._graphs[paper_id] = graph
        self._status[paper_id] = PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.READY,
            percent=100,
            stage=PipelineStage.READY,
            message="建图完成",
            updated_at=now,
        )

    def fail_pipeline(self, paper_id: str, *, message: str, error_code: str = "PIPELINE_FAILED") -> None:
        self.ensure_paper_exists(paper_id)
        now = datetime.now(UTC)
        paper = self._papers[paper_id]
        self._papers[paper_id] = paper.model_copy(
            update={"status": PaperStatus.FAILED, "updated_at": now},
        )
        self._status[paper_id] = PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.FAILED,
            percent=0,
            stage=PipelineStage.FAILED,
            message=message,
            updated_at=now,
        )
        _ = error_code  # reserved for future error envelope on detail API

    async def get_status(self, paper_id: str) -> PaperStatusData:
        if paper_id in self._status:
            return self._status[paper_id]
        paper = await self.get_paper(paper_id)
        if paper.status == PaperStatus.READY:
            return PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.READY,
                percent=100,
                stage=PipelineStage.READY,
                message="建图完成",
                updated_at=paper.updated_at or paper.created_at,
            )
        if paper.status == PaperStatus.PROCESSING:
            return PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.PROCESSING,
                percent=50,
                stage=PipelineStage.CLASSIFYING,
                message="正在范式分类（骨架占位）",
                updated_at=paper.updated_at or paper.created_at,
            )
        return PaperStatusData(
            paper_id=paper_id,
            status=paper.status,
            percent=0,
            stage=None,
            message="任务已创建，等待流水线（骨架占位）",
            updated_at=paper.updated_at or paper.created_at,
        )

    async def get_graph(self, paper_id: str) -> UnifiedPaperGraph:
        paper = await self.get_paper(paper_id)
        if paper.status != PaperStatus.READY:
            raise ApiError(
                "GRAPH_NOT_READY",
                "图谱尚未就绪，请轮询 status 接口",
                status_code=409,
            )
        graph = self._graphs.get(paper_id)
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
            message="任务已创建，请轮询 status 接口",
            updated_at=now,
        )
        return PaperCreateResult(
            paper_id=paper_id,
            status=PaperStatus.PENDING,
            message="任务已创建，请轮询 status 接口",
        )


@lru_cache
def get_paper_service() -> PaperService:
    return PaperService()
