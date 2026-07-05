"""Shared pytest fixtures for cross-package tests."""

from __future__ import annotations

import importlib.util
import os

# Keep unit tests independent of developer ``.env`` (LLM_MODE=live, custom models, etc.).
os.environ.setdefault("SCHOLARGRAPH_IGNORE_DOTENV", "1")
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_PIPELINE_SCRIPT = REPO_ROOT / "scripts" / "run_pipeline.py"
RUN_PATROL_SCRIPT = REPO_ROOT / "scripts" / "run_patrol.py"
BENCHMARK_DUAL_ROUTE_SCRIPT = REPO_ROOT / "scripts" / "benchmark_dual_route.py"
BENCHMARK_REGRESSION_SCRIPT = REPO_ROOT / "scripts" / "benchmark_regression.py"


@pytest.fixture
def run_pipeline_module():
    """Load scripts/run_pipeline.py as a module (not installed as package)."""
    spec = importlib.util.spec_from_file_location("run_pipeline", RUN_PIPELINE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_patrol_module():
    """Load scripts/run_patrol.py as a module (not installed as package)."""
    spec = importlib.util.spec_from_file_location("run_patrol", RUN_PATROL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def benchmark_regression_module():
    """Load scripts/benchmark_regression.py as a module (not installed as package)."""
    import sys

    spec = importlib.util.spec_from_file_location("benchmark_regression", BENCHMARK_REGRESSION_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def benchmark_dual_route_module():
    """Load scripts/benchmark_dual_route.py as a module (not installed as package)."""
    import sys

    spec = importlib.util.spec_from_file_location("benchmark_dual_route", BENCHMARK_DUAL_ROUTE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _disable_two_phase_extraction_for_legacy_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default tests to the single-phase extraction path to preserve existing mocks.

    New tests for the two-phase sub-graph should explicitly re-enable it with
    ``monkeypatch.setenv('EXTRACT_TWO_PHASE_ENABLED', 'true')``.
    """
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "false")
    get_settings.cache_clear()


@pytest.fixture
def minimal_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "minimal.pdf"
    path.write_bytes(b"%PDF-1.4\n% minimal test pdf")
    return path


@contextmanager
def mock_pipeline_node_services(
    paper_id: str,
) -> Iterator[dict[str, MagicMock]]:
    """Patch workflow node services with successful mocks for a given paper_id."""
    from backend.agents.classifier_types import ClassifyResult
    from backend.agents.extract_types import ExtractResult
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm, ParadigmClassification
    from backend.services.graph_persistence_service import GraphPersistenceService
    from backend.services.pipeline_completion_service import PipelineCompletionService

    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="mock",
    )
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="N", type="Thesis")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="REF",
                type="REF",
            ),
        ],
    )
    extract_result = ExtractResult(graph=graph, warnings=[])

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": paper_id,
            "full_text": "full-text",
            "classifier_input": "classifier-input",
        },
    )

    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(return_value=ClassifyResult(classification=classification, warnings=[]))
    agent_svc.extract_graph = AsyncMock(return_value=extract_result)
    agent_svc.extract_graph_background = AsyncMock(return_value=extract_result)
    agent_svc.should_extract_in_background = MagicMock(return_value=False)

    with patch("backend.services.graph_persistence_service.GraphStore") as store_cls:
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)

        with (
            patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
            patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
            patch("backend.services.agent_service.get_agent_service", return_value=agent_svc),
            patch(
                "backend.graph.nodes.get_pipeline_completion_service",
                return_value=completion_svc,
            ),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
            patch(
                "backend.graph.nodes.wait_for_refined_classifier_input",
                new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
            ),
        ):
            yield {
                "ingest": ingest_svc,
                "agent": agent_svc,
                "completion": completion_svc,
                "store_save": store_cls.return_value.save,
            }


@pytest.fixture
def mock_pipeline_services():
    """Pytest fixture wrapper: use as `with mock_pipeline_services("paper-id"):` via request."""

    @contextmanager
    def _apply(paper_id: str) -> Iterator[dict[str, MagicMock]]:
        with mock_pipeline_node_services(paper_id) as mocks:
            yield mocks

    return _apply


@contextmanager
def mock_agent_services_only(
    paper_id: str,
) -> Iterator[dict[str, MagicMock]]:
    """Patch agent + store only; ingest runs real ``IngestService`` (BE-1 + platform)."""
    from backend.agents.classifier_types import ClassifyResult
    from backend.agents.extract_types import ExtractResult
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm, ParadigmClassification
    from backend.services.graph_persistence_service import GraphPersistenceService
    from backend.services.pipeline_completion_service import PipelineCompletionService

    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.91,
        reason="three-branch mock classify",
    )
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="N", type="Method")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="Mock self-supporting edge to satisfy quality gate coverage.",
                source_span="Mock textual anchor.",
                confidence="HIGH",
            ),
        ],
    )
    extract_result = ExtractResult(graph=graph, warnings=[])

    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(return_value=ClassifyResult(classification=classification, warnings=[]))
    agent_svc.extract_graph = AsyncMock(return_value=extract_result)
    agent_svc.extract_graph_background = AsyncMock(return_value=extract_result)
    agent_svc.should_extract_in_background = MagicMock(return_value=False)

    with patch("backend.services.graph_persistence_service.GraphStore") as store_cls:
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)

        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
            patch("backend.services.agent_service.get_agent_service", return_value=agent_svc),
            patch(
                "backend.graph.nodes.get_pipeline_completion_service",
                return_value=completion_svc,
            ),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
            patch(
                "backend.graph.nodes.wait_for_refined_classifier_input",
                new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
            ),
        ):
            yield {
                "agent": agent_svc,
                "completion": completion_svc,
                "store_save": store_cls.return_value.save,
            }
