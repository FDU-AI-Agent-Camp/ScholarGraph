"""Shared fixtures for graph / workflow tests."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.graph.state import STAGE_PERCENT, WorkflowState, initial_workflow_state
from backend.graph.workflow import get_compiled_paper_pipeline
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service


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
def mock_pipeline_dependencies() -> Iterator[dict[str, AsyncMock]]:
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="mock",
    )

    with (
        patch("backend.graph.nodes.ingest_pdf", new_callable=AsyncMock) as ingest,
        patch("backend.graph.nodes.classify", new_callable=AsyncMock) as classify,
        patch("backend.graph.nodes.extract", new_callable=AsyncMock) as extract,
        patch("backend.graph.nodes.GraphStore") as store_cls,
    ):
        ingest.side_effect = lambda path, paper_id=None: {
            "paper_id": paper_id or path.stem,
            "full_text": "full-text",
            "classifier_input": "classifier-input",
        }
        classify.return_value = classification
        extract.side_effect = lambda _text, paradigm: UnifiedPaperGraph(
            paper_id="wf-test-paper",
            paradigm=paradigm,
            nodes=[GraphNode(id="n1", label="N", type="Thesis")],
            edges=[],
        )
        store_instance = store_cls.return_value
        store_instance.save = lambda _graph: None
        yield {
            "ingest": ingest,
            "classify": classify,
            "extract": extract,
            "store_cls": store_cls,
            "store_save": store_instance.save,
        }
