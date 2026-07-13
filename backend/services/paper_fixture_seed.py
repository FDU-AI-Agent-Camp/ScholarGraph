"""Seed demo papers into the database from ``docs/api/fixtures``."""

from __future__ import annotations

import json
from pathlib import Path

from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
DEFAULT_GRAPH_DATA_DIR = Path("./data/graphs")


async def seed_from_fixtures(
    paper_repo: PaperRepository,
    pipeline_repo: PipelineRepository,
) -> None:
    """Load demo papers, graphs, and status snapshots from OpenAPI fixtures."""
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
        await _seed_paper_row(paper_repo, detail)
        graph_path = FIXTURES_DIR / f"graph-{paper_id}.json"
        if not graph_path.is_file() and detail.paradigm == Paradigm.HSS:
            graph_path = FIXTURES_DIR / "graph-hss.json"
        if graph_path.is_file():
            graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
            graph = UnifiedPaperGraph.model_validate(graph_payload["data"])
            graph = graph.model_copy(update={"paper_id": detail.paper_id})
            _seed_graph_fixture_if_needed(graph)
            from backend.graph.store import GraphStore

            await paper_repo.update_paths(detail.paper_id, graph_path=str(GraphStore()._path(detail.paper_id)))
        await _seed_status_for_detail(pipeline_repo, detail)


async def _seed_paper_row(paper_repo: PaperRepository, detail: PaperDetail) -> None:
    pdf_path = str(Path("./uploads") / f"{detail.paper_id}.pdf")
    existing = await paper_repo.get(detail.paper_id)
    if existing is not None:
        return
    await paper_repo.create(
        detail.paper_id,
        detail.title or detail.paper_id,
        pdf_path,
        status=detail.status,
    )
    if detail.classification is not None:
        await paper_repo.update_classification(detail.paper_id, detail.classification)
    if detail.preview_available:
        await paper_repo.mark_preview_available(detail.paper_id)


def _seed_graph_fixture_if_needed(graph: UnifiedPaperGraph) -> None:
    """Persist demo fixture graphs only under the default local ``./data/graphs`` dir."""
    from backend.graph.store import GraphStore

    store = GraphStore()
    if store._base_dir.resolve() != DEFAULT_GRAPH_DATA_DIR.resolve():
        return
    path = store._path(graph.paper_id)
    if path.is_file():
        try:
            if store.load(graph.paper_id) is not None:
                return
        except Exception:
            pass
    store.save(graph)


async def _seed_status_for_detail(
    pipeline_repo: PipelineRepository,
    detail: PaperDetail,
) -> None:
    """Prefer per-paper status fixtures; otherwise synthesize api-contract snapshots."""
    status_path = FIXTURES_DIR / f"paper-status-{detail.paper_id}.json"
    if status_path.is_file():
        status_payload = json.loads(status_path.read_text(encoding="utf-8"))
        snapshot = PaperStatusData.model_validate(status_payload["data"])
        await pipeline_repo.save_status(detail.paper_id, snapshot)
        return

    updated_at = detail.updated_at or detail.created_at
    if detail.status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS):
        snapshot = PaperStatusData(
            paper_id=detail.paper_id,
            status=detail.status,
            percent=100,
            stage=PipelineStage.READY,
            message="建图完成" if detail.status == PaperStatus.READY else "建图完成，但置信度未达门控",
            updated_at=updated_at,
            preview_available=detail.preview_available,
        )
    elif detail.status == PaperStatus.PROCESSING:
        snapshot = PaperStatusData(
            paper_id=detail.paper_id,
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="正在识别范式与理论视角…",
            updated_at=updated_at,
            preview_available=detail.preview_available,
        )
    elif detail.status == PaperStatus.PENDING:
        snapshot = PaperStatusData(
            paper_id=detail.paper_id,
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message="任务已创建，请轮询 status 接口",
            updated_at=updated_at,
            preview_available=False,
        )
    else:
        snapshot = PaperStatusData(
            paper_id=detail.paper_id,
            status=detail.status,
            percent=0,
            stage=PipelineStage.FAILED,
            message="流水线失败",
            updated_at=updated_at,
            preview_available=detail.preview_available,
        )
    await pipeline_repo.save_status(detail.paper_id, snapshot)


async def refresh_demo_status_snapshots(paper_ids: tuple[str, ...] | list[str]) -> None:
    """Reload per-paper status fixtures so demo rows match docs/api snapshots."""
    from backend.repositories.pipeline_repository import get_pipeline_repository

    pipeline_repo = get_pipeline_repository()
    for paper_id in paper_ids:
        status_path = FIXTURES_DIR / f"paper-status-{paper_id}.json"
        if not status_path.is_file():
            continue
        status_payload = json.loads(status_path.read_text(encoding="utf-8"))
        snapshot = PaperStatusData.model_validate(status_payload["data"])
        await pipeline_repo.save_status(paper_id, snapshot)
