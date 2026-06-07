"""Shared fixtures for service-layer tests."""

from datetime import UTC, datetime

import pytest
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service


@pytest.fixture
def sample_classification() -> ParadigmClassification:
    return ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.91,
        reason="测试分类理由",
    )


@pytest.fixture
def sample_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="svc-test-paper",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
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


@pytest.fixture
def registered_paper() -> str:
    paper_id = "svc-test-paper"
    now = datetime.now(UTC)
    service = get_paper_service()
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="service test",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    service._status.pop(paper_id, None)
    service._head_refine_warnings.pop(paper_id, None)
    service._refined_classifier_input.pop(paper_id, None)
    service._refined_head.pop(paper_id, None)
    from backend.graph.head_store import HeadStore

    HeadStore()._path(paper_id).unlink(missing_ok=True)
    return paper_id
