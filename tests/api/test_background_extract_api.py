"""HTTP interface tests for Slice 2 background full extraction.

These tests hit the real FastAPI endpoints and verify the observable contract:
- long papers schedule background extraction and return pending immediately
- status polling shows the extracting stage before ready
- GET /papers/{id}/graph returns 409 while background extraction runs
- the paper eventually reaches ready and the graph endpoint succeeds
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.extract_types import ExtractResult
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.api.test_papers_upload import VALID_PDF
from tests.helpers.status_contract import assert_terminal_failed_envelope, assert_terminal_ready_envelope

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_background_extract_worker() -> None:
    from backend.services.extract_worker import reset_extract_worker
    from backend.services.pipeline_task_registry import reset_pipeline_task_registry

    reset_pipeline_task_registry()
    reset_extract_worker()
    yield
    reset_pipeline_task_registry()
    reset_extract_worker()


def _fake_graph(paper_id: str, paradigm: Paradigm) -> UnifiedPaperGraph:
    """Return a small deterministic graph for HTTP contract tests."""
    node_type = NodeType.THESIS if paradigm == Paradigm.HSS else NodeType.RESEARCH_QUESTION
    return UnifiedPaperGraph(
        paper_id=paper_id,
        title="fake-graph",
        paradigm=paradigm,
        nodes=[GraphNode(id="n1", label="Fake node", type=node_type)],
        edges=[],
        summary="fake",
    )


def _full_fake_graph(paper_id: str, paradigm: Paradigm) -> UnifiedPaperGraph:
    """Return a small deterministic graph produced by the background worker."""
    node_type = NodeType.THESIS if paradigm == Paradigm.HSS else NodeType.RESEARCH_QUESTION
    return UnifiedPaperGraph(
        paper_id=paper_id,
        title="full-fake-graph",
        paradigm=paradigm,
        nodes=[
            GraphNode(id="n1", label="Fake node", type=node_type),
            GraphNode(id="n2", label="Another fake node", type=node_type),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n2",
                label="supports",
                type="SUPPORTS",
                rationale="Contract-test support edge with explicit rationale.",
            ),
        ],
        summary="full fake",
    )


async def _fake_extract_preview_and_schedule(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    classification: object,
    settings: object | None = None,
    pipeline_generation_id: str | None = None,
) -> ExtractResult:
    """Schedule the real background worker but return a deterministic preview."""
    from backend.config import get_settings
    from backend.services.extract_worker import schedule_full_extraction

    cfg = settings or get_settings()
    schedule_full_extraction(
        paper_id,
        full_text,
        paradigm,
        classification,
        head_context=None,
        settings=cfg,
        pipeline_generation_id=pipeline_generation_id,
    )
    return ExtractResult(graph=_fake_graph(paper_id, paradigm), warnings=[])


def _slow_full_extraction(sleep_s: float):
    """Patch replacement for ``_extract_chunked_two_phase`` that sleeps deterministically."""

    async def _extract(
        _full_text: str,
        paradigm: Paradigm,
        *,
        paper_id: str,
        **_kwargs: object,
    ) -> ExtractResult:
        await asyncio.sleep(sleep_s)
        return ExtractResult(graph=_full_fake_graph(paper_id, paradigm), warnings=[])

    return _extract


@contextmanager
def _background_extract_contract_patches(
    *,
    extract_chunked_two_phase: object,
    preview_scheduler: object | None = None,
) -> Iterator[None]:
    """Patch consumer namespaces and keep HTTP tests off the PipelineFinalized chain."""
    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": "will-be-replaced",
            "full_text": "x" * 50_000,
            "classifier_input": "classification input",
        },
    )
    scheduler = preview_scheduler or _fake_extract_preview_and_schedule
    with (
        patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch("backend.services.paper_pipeline_scheduler.ensure_head_refine_scheduled"),
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
        ),
        patch("backend.services.agent_service.should_run_background_extraction", return_value=True),
        patch("backend.services.agent_service.extract_preview_and_schedule_full", new=scheduler),
        patch("backend.services.extract_worker._extract_chunked_two_phase", new=extract_chunked_two_phase),
    ):
        yield


_TERMINAL_STATUSES = frozenset({"ready", "ready_with_warnings", "failed"})


async def _poll_status_until_terminal(
    api_client: AsyncClient,
    paper_id: str,
    *,
    max_attempts: int = 120,
    interval_s: float = 0.05,
) -> dict:
    last: dict = {}
    for _ in range(max_attempts):
        await asyncio.sleep(interval_s)
        response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
        assert response.status_code == 200
        last = response.json()["data"]
        if last["status"] in _TERMINAL_STATUSES:
            if last["status"] == "ready":
                assert_terminal_ready_envelope(last)
            elif last["status"] == "failed":
                assert_terminal_failed_envelope(last)
            return last
    return last


async def test_long_paper_upload_reaches_ready_via_background_extraction(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    """Long papers take the background extract path and eventually become ready."""
    _upload_dir, graph_dir = mock_upload_pipeline_env

    with _background_extract_contract_patches(extract_chunked_two_phase=_slow_full_extraction(0.1)):
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("long-paper.pdf", VALID_PDF, "application/pdf")},
        )
        assert create.status_code == 201
        body = create.json()
        assert_success_envelope(body)
        paper_id = body["data"]["paper_id"]

        saw_extracting = False
        final: dict = {}
        for _ in range(120):
            await asyncio.sleep(0.05)
            status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
            final = status_resp.json()["data"]
            if final.get("stage") == "extracting":
                saw_extracting = True
            if final["status"] in _TERMINAL_STATUSES:
                break

        assert saw_extracting, "background extraction should surface the extracting stage"
        assert_terminal_ready_envelope(final)

    detail = await api_client.get(f"/api/v1/papers/{paper_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "ready"

    graph = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph.status_code == 200
    graph_body = graph.json()
    assert_success_envelope(graph_body)
    assert graph_body["data"]["paper_id"] == paper_id
    assert (graph_dir / f"{paper_id}.json").is_file()


async def test_graph_returns_409_while_background_extraction_runs(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    """GET /graph before background extraction finishes must return 409."""
    _upload_dir, _graph_dir = mock_upload_pipeline_env

    with _background_extract_contract_patches(extract_chunked_two_phase=_slow_full_extraction(0.3)):
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("slow-bg.pdf", VALID_PDF, "application/pdf")},
        )
        paper_id = create.json()["data"]["paper_id"]

        saw_409 = False
        for _ in range(40):
            await asyncio.sleep(0.05)
            graph_resp = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
            if graph_resp.status_code == 409:
                saw_409 = True
                assert_error_envelope(graph_resp.json(), code="GRAPH_NOT_READY")
                break
            status = (await api_client.get(f"/api/v1/papers/{paper_id}/status")).json()["data"]
            if status["status"] in _TERMINAL_STATUSES:
                break

        assert saw_409, "graph endpoint should return 409 while background extraction runs"

        final = await _poll_status_until_terminal(api_client, paper_id)
        assert_terminal_ready_envelope(final)


async def test_background_extraction_failed_marks_paper_failed(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    """If the background worker fails, status polling must eventually report failed."""
    _upload_dir, _graph_dir = mock_upload_pipeline_env

    async def failing_full_extraction(*_args, **_kwargs):
        raise RuntimeError("background extraction failed")

    with _background_extract_contract_patches(extract_chunked_two_phase=failing_full_extraction):
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("failing-bg.pdf", VALID_PDF, "application/pdf")},
        )
        paper_id = create.json()["data"]["paper_id"]

        final = await _poll_status_until_terminal(api_client, paper_id)
        assert_terminal_failed_envelope(final)
