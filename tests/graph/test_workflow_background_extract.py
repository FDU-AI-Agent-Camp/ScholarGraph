# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for workflow background-extraction routing (Slice 2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_types import ExtractResult
from backend.graph import nodes
from backend.graph.state import WorkflowState
from backend.graph.workflow import _route_after_extract, run_paper_pipeline
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError

from tests.helpers.persistence_testkit import register_test_paper


@pytest.fixture
def long_paper_state() -> WorkflowState:
    return WorkflowState(
        paper_id="long-001",
        full_text="x" * 50_000,
        paradigm=Paradigm.HSS.value,
        classification=ParadigmClassification(
            paradigm=Paradigm.HSS,
            confidence=0.9,
            reason="test",
        ).model_dump(mode="json"),
    )


@pytest.fixture
def short_paper_state() -> WorkflowState:
    return WorkflowState(
        paper_id="short-001",
        full_text="short paper body",
        paradigm=Paradigm.HSS.value,
        classification=ParadigmClassification(
            paradigm=Paradigm.HSS,
            confidence=0.9,
            reason="test",
        ).model_dump(mode="json"),
    )


@pytest.fixture(autouse=True)
def _fresh_service() -> None:
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield
    get_paper_service.cache_clear()


def _make_preview_graph(paper_id: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Preview", type="Thesis")],
        edges=[],
    )


async def _register_paper(paper_id: str) -> None:
    await register_test_paper(paper_id, title="bg routing test", status=PaperStatus.PROCESSING)


class TestExtractNodeBackgroundRouting:
    async def test_long_paper_schedules_background_and_returns_preview(
        self,
        long_paper_state: WorkflowState,
        persistence_env: dict,
    ) -> None:
        await _register_paper(long_paper_state["paper_id"])
        preview = _make_preview_graph(long_paper_state["paper_id"])
        agent_svc = MagicMock()
        agent_svc.extract_graph_background = AsyncMock(
            return_value=ExtractResult(graph=preview, warnings=["mvp_skeleton_preview"]),
        )
        agent_svc.should_extract_in_background = MagicMock(return_value=True)

        with patch("backend.graph.nodes.get_agent_service", return_value=agent_svc):
            out = await nodes.extract_node(long_paper_state)

        assert out.get("background_extraction_scheduled") is True
        assert out["graph"]["paper_id"] == long_paper_state["paper_id"]
        agent_svc.extract_graph_background.assert_awaited_once()
        agent_svc.extract_graph.assert_not_called()

    async def test_short_paper_uses_synchronous_path(
        self,
        short_paper_state: WorkflowState,
        persistence_env: dict,
    ) -> None:
        await _register_paper(short_paper_state["paper_id"])
        graph = _make_preview_graph(short_paper_state["paper_id"])
        agent_svc = MagicMock()
        agent_svc.extract_graph = AsyncMock(return_value=ExtractResult(graph=graph, warnings=[]))
        agent_svc.should_extract_in_background = MagicMock(return_value=False)

        with patch("backend.graph.nodes.get_agent_service", return_value=agent_svc):
            out = await nodes.extract_node(short_paper_state)

        assert out.get("background_extraction_scheduled") is None
        agent_svc.extract_graph.assert_awaited_once()
        agent_svc.extract_graph_background.assert_not_called()


class TestWorkflowBackgroundRouting:
    async def test_long_paper_pipeline_ends_at_extract_stage(
        self,
        tmp_path: Path,
        persistence_env: dict,
    ) -> None:
        paper_id = "wf-long-001"
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake pdf content")
        await register_test_paper(paper_id, title="long wf", pdf_path=str(pdf_path))

        preview = _make_preview_graph(paper_id)
        agent_svc = MagicMock()
        agent_svc.classify_paradigm = AsyncMock(
            return_value=ClassifyResult(
                classification=ParadigmClassification(
                    paradigm=Paradigm.HSS,
                    confidence=0.9,
                    reason="test",
                ),
                warnings=[],
            ),
        )
        agent_svc.extract_graph_background = AsyncMock(
            return_value=ExtractResult(graph=preview, warnings=["mvp_skeleton_preview"]),
        )
        agent_svc.should_extract_in_background = MagicMock(return_value=True)

        ingest_svc = MagicMock()
        ingest_svc.ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": "x" * 50_000,
                "classifier_input": "classifier-input",
            },
        )

        completion_svc = MagicMock()
        completion_svc.finalize = MagicMock(return_value=preview)

        with (
            patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
            patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
            patch("backend.graph.nodes.get_pipeline_completion_service", return_value=completion_svc),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
            patch(
                "backend.graph.nodes.wait_for_refined_classifier_input",
                new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

        assert final.get("background_extraction_scheduled") is True
        assert final.get("stage") == PipelineStage.EXTRACTING
        completion_svc.finalize.assert_not_called()


class TestWorkflowForegroundRouting:
    async def test_short_paper_pipeline_runs_to_indexing(
        self,
        tmp_path: Path,
        persistence_env: dict,
    ) -> None:
        paper_id = "wf-short-001"
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake pdf content")
        await register_test_paper(paper_id, title="short wf", pdf_path=str(pdf_path))

        graph = _make_preview_graph(paper_id)
        agent_svc = MagicMock()
        agent_svc.classify_paradigm = AsyncMock(
            return_value=ClassifyResult(
                classification=ParadigmClassification(
                    paradigm=Paradigm.HSS,
                    confidence=0.9,
                    reason="test",
                ),
                warnings=[],
            ),
        )
        agent_svc.extract_graph = AsyncMock(
            return_value=ExtractResult(graph=graph, warnings=[]),
        )
        agent_svc.should_extract_in_background = MagicMock(return_value=False)

        ingest_svc = MagicMock()
        ingest_svc.ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": "short paper",
                "classifier_input": "classifier-input",
            },
        )

        completion_svc = MagicMock()
        completion_svc.finalize = MagicMock(return_value=None)

        with (
            patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
            patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
            patch("backend.graph.nodes.get_pipeline_completion_service", return_value=completion_svc),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
            patch(
                "backend.graph.nodes.wait_for_refined_classifier_input",
                new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

        assert final.get("background_extraction_scheduled") is None
        # P10: LangGraph store step ends at INDEXING; READY is after RAG EventBus promote.
        assert final.get("stage") == PipelineStage.INDEXING
        completion_svc.finalize.assert_called_once()


class TestWorkflowBackgroundFailure:
    async def test_background_extract_service_error_routes_to_fail(
        self,
        tmp_path: Path,
        persistence_env: dict,
    ) -> None:
        paper_id = "wf-bg-fail-001"
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake pdf content")
        await register_test_paper(paper_id, title="bg fail wf", pdf_path=str(pdf_path))

        agent_svc = MagicMock()
        agent_svc.classify_paradigm = AsyncMock(
            return_value=ClassifyResult(
                classification=ParadigmClassification(
                    paradigm=Paradigm.HSS,
                    confidence=0.9,
                    reason="test",
                ),
                warnings=[],
            ),
        )
        agent_svc.extract_graph_background = AsyncMock(
            side_effect=ServiceError(code="LLM_JSON_INVALID", message="background extract failed"),
        )
        agent_svc.should_extract_in_background = MagicMock(return_value=True)

        ingest_svc = MagicMock()
        ingest_svc.ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": "x" * 50_000,
                "classifier_input": "classifier-input",
            },
        )

        with (
            patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
            patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
            patch("backend.graph.nodes.get_pipeline_completion_service") as _completion,
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
            patch(
                "backend.graph.nodes.wait_for_refined_classifier_input",
                new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

        assert final.get("failed") is True
        assert final.get("error_code") == "LLM_JSON_INVALID"
        assert final.get("stage") == PipelineStage.FAILED


class TestRouteAfterExtract:
    def test_failed_routes_to_fail(self) -> None:
        state: WorkflowState = {"failed": True}
        assert _route_after_extract(state) == "fail"

    def test_background_routes_to_end(self) -> None:
        state: WorkflowState = {"background_extraction_scheduled": True}
        assert _route_after_extract(state) == "background"

    def test_continue_routes_to_store(self) -> None:
        state: WorkflowState = {}
        assert _route_after_extract(state) == "continue"
