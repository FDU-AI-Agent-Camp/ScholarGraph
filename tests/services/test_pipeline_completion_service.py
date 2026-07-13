"""Tests for PipelineCompletionService — store-step business orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import PipelineCompletionService


def test_finalize_validates_persists_and_marks_ready(
    registered_paper: str,
    sample_graph: UnifiedPaperGraph,
    sample_classification: ParadigmClassification,
) -> None:
    persistence = MagicMock(spec=GraphPersistenceService)
    service = PipelineCompletionService(graph_persistence=persistence)
    graph = sample_graph.model_copy(update={"paper_id": registered_paper})

    with patch(
        "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
        new_callable=AsyncMock,
    ):
        result = service.finalize(
            registered_paper,
            graph_data=graph.model_dump(mode="json"),
            classification_data=sample_classification.model_dump(mode="json"),
            full_text="service test full text body",
        )

    persistence.save.assert_called_once()
    assert result.paper_id == registered_paper
    import asyncio

    paper = asyncio.run(get_paper_service().get_paper(registered_paper))
    assert paper.status == PaperStatus.READY
    assert paper.classification == sample_classification
    status = asyncio.run(get_paper_service().get_status(registered_paper))
    assert status.stage == PipelineStage.READY
    assert status.percent == 100


def test_finalize_invalid_graph_raises_service_error(
    registered_paper: str,
    sample_classification: ParadigmClassification,
) -> None:
    persistence = MagicMock(spec=GraphPersistenceService)
    service = PipelineCompletionService(graph_persistence=persistence)
    with pytest.raises(ServiceError) as err:
        service.finalize(
            registered_paper,
            graph_data={"paper_id": registered_paper, "nodes": "invalid"},
            classification_data=sample_classification.model_dump(mode="json"),
        )
    assert err.value.code == "PIPELINE_FAILED"
    persistence.save.assert_not_called()


def test_finalize_reraises_persistence_service_error(
    registered_paper: str,
    sample_graph: UnifiedPaperGraph,
    sample_classification: ParadigmClassification,
) -> None:
    persistence = MagicMock(spec=GraphPersistenceService)
    persistence.save.side_effect = ServiceError("PIPELINE_FAILED", "save failed")
    service = PipelineCompletionService(graph_persistence=persistence)
    with pytest.raises(ServiceError) as err:
        service.finalize(
            registered_paper,
            graph_data=sample_graph.model_dump(mode="json"),
            classification_data=sample_classification.model_dump(mode="json"),
        )
    assert err.value.message == "save failed"
