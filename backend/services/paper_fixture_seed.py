"""Seed in-memory ``PaperService`` from ``docs/api/fixtures``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
DEFAULT_GRAPH_DATA_DIR = Path("./data/graphs")


def seed_from_fixtures(service: PaperService) -> None:
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
        service._papers[detail.paper_id] = detail
        graph_path = FIXTURES_DIR / f"graph-{paper_id}.json"
        if not graph_path.is_file() and detail.paradigm == Paradigm.HSS:
            graph_path = FIXTURES_DIR / "graph-hss.json"
        if graph_path.is_file():
            graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
            graph = UnifiedPaperGraph.model_validate(graph_payload["data"])
            graph = graph.model_copy(update={"paper_id": detail.paper_id})
            _seed_graph_fixture_if_needed(graph)
        _seed_status_for_detail(service, detail)


def _seed_graph_fixture_if_needed(graph: UnifiedPaperGraph) -> None:
    """Persist demo fixture graphs only under the default local ``./data/graphs`` dir."""
    from backend.graph.store import GraphStore

    store = GraphStore()
    if store.load(graph.paper_id) is not None:
        return
    if store._base_dir.resolve() != DEFAULT_GRAPH_DATA_DIR.resolve():
        return
    store.save(graph)


def _seed_status_for_detail(service: PaperService, detail: PaperDetail) -> None:
    """Prefer per-paper status fixtures; otherwise synthesize api-contract snapshots."""
    status_path = FIXTURES_DIR / f"paper-status-{detail.paper_id}.json"
    if status_path.is_file():
        status_payload = json.loads(status_path.read_text(encoding="utf-8"))
        service._status[detail.paper_id] = PaperStatusData.model_validate(status_payload["data"])
        return

    updated_at = detail.updated_at or detail.created_at
    if detail.status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS):
        service._status[detail.paper_id] = PaperStatusData(
            paper_id=detail.paper_id,
            status=detail.status,
            percent=100,
            stage=PipelineStage.READY,
            message="建图完成" if detail.status == PaperStatus.READY else "建图完成，但置信度未达门控",
            updated_at=updated_at,
            preview_available=detail.preview_available,
        )
    elif detail.status == PaperStatus.PROCESSING:
        service._status[detail.paper_id] = PaperStatusData(
            paper_id=detail.paper_id,
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="正在识别范式与理论视角…",
            updated_at=updated_at,
            preview_available=detail.preview_available,
        )
    elif detail.status == PaperStatus.PENDING:
        service._status[detail.paper_id] = PaperStatusData(
            paper_id=detail.paper_id,
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message="任务已创建，请轮询 status 接口",
            updated_at=updated_at,
            preview_available=False,
        )
