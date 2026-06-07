"""Shared fixtures for graph / workflow tests."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.graph.state import STAGE_PERCENT, WorkflowState, initial_workflow_state
from backend.graph.workflow import get_compiled_paper_pipeline
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import PipelineCompletionService


@pytest.fixture(autouse=True)
def clear_compiled_pipeline_cache() -> Iterator[None]:
    get_compiled_paper_pipeline.cache_clear()
    yield
    get_compiled_paper_pipeline.cache_clear()


@pytest.fixture
def workflow_paper(tmp_path: Path) -> tuple[str, Path]:
    """Register a pending paper and create a minimal PDF on disk."""
    paper_id = "wf-test-paper"
    pdf_path = tmp_path / f"{paper_id}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% mock content")

    now = datetime.now(UTC)
    service = get_paper_service()
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="workflow unit test",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    service._status.pop(paper_id, None)
    return paper_id, pdf_path


@pytest.fixture
def workflow_initial_state(workflow_paper: tuple[str, Path]) -> WorkflowState:
    paper_id, pdf_path = workflow_paper
    return initial_workflow_state(paper_id=paper_id, pdf_path=str(pdf_path))


@pytest.fixture
def post_ingest_state(workflow_initial_state: WorkflowState) -> WorkflowState:
    state = dict(workflow_initial_state)
    state.update(
        {
            "full_text": "Full paper body text.",
            "classifier_input": "Title\nAbstract\nKeywords",
            "stage": PipelineStage.INGESTING,
            "percent": STAGE_PERCENT[PipelineStage.INGESTING],
            "message": "PDF 解析完成",
            "failed": False,
        },
    )
    return WorkflowState(**state)


@pytest.fixture
def post_classify_state(post_ingest_state: WorkflowState) -> WorkflowState:
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.92,
        reason="历史制度主义视角，无量化实验。",
    )
    state = dict(post_ingest_state)
    state.update(
        {
            "classification": classification.model_dump(mode="json"),
            "paradigm": Paradigm.HSS.value,
            "stage": PipelineStage.CLASSIFYING,
            "percent": STAGE_PERCENT[PipelineStage.CLASSIFYING],
            "message": "范式分类完成",
        },
    )
    return WorkflowState(**state)


@pytest.fixture
def post_extract_state(post_classify_state: WorkflowState) -> WorkflowState:
    paper_id = post_classify_state["paper_id"]
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis")],
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
    state = dict(post_classify_state)
    state.update(
        {
            "graph": graph.model_dump(mode="json"),
            "stage": PipelineStage.EXTRACTING,
            "percent": STAGE_PERCENT[PipelineStage.EXTRACTING],
            "message": "图谱抽取完成",
        },
    )
    return WorkflowState(**state)


@pytest.fixture
def mock_pipeline_dependencies() -> Iterator[dict[str, MagicMock]]:
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="mock",
    )
    graph = UnifiedPaperGraph(
        paper_id="wf-test-paper",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="N", type="Thesis")],
        edges=[],
    )

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": "wf-test-paper",
            "full_text": "full-text",
            "classifier_input": "classifier-input",
        },
    )

    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(return_value=classification)
    agent_svc.extract_graph = AsyncMock(return_value=graph)

    with patch("backend.services.graph_persistence_service.GraphStore") as store_cls:
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)

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
            yield {
                "ingest": ingest_svc,
                "agent": agent_svc,
                "completion": completion_svc,
                "store_save": store_cls.return_value.save,
            }
