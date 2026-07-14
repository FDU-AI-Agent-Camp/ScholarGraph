"""Tests for PipelineCompletionService — store-step business orchestration."""

from unittest.mock import AsyncMock, patch

import pytest
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import PipelineCompletionService
from tests.helpers.persistence_testkit import mock_graph_persistence


def test_finalize_validates_persists_and_marks_ready(
    registered_paper: str,
    sample_graph: UnifiedPaperGraph,
    sample_classification: ParadigmClassification,
) -> None:
    persistence = mock_graph_persistence(registered_paper)
    service = PipelineCompletionService(graph_persistence=persistence)
    graph = sample_graph.model_copy(update={"paper_id": registered_paper})

    with patch(
        "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
        new_callable=AsyncMock,
        return_value=True,
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

    from tests.helpers.event_bus_testkit import drain_event_bus_sync

    drain_event_bus_sync()
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
    persistence = mock_graph_persistence(registered_paper)
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
    persistence = mock_graph_persistence(registered_paper)
    persistence.save.side_effect = ServiceError("PIPELINE_FAILED", "save failed")
    service = PipelineCompletionService(graph_persistence=persistence)
    with pytest.raises(ServiceError) as err:
        service.finalize(
            registered_paper,
            graph_data=sample_graph.model_dump(mode="json"),
            classification_data=sample_classification.model_dump(mode="json"),
        )
    assert err.value.message == "save failed"


def test_finalize_does_not_double_write_graph_store(
    registered_paper: str,
    sample_graph: UnifiedPaperGraph,
    sample_classification: ParadigmClassification,
) -> None:
    """D7: mocked persistence is the sole graph writer; GraphStore is not called again."""
    persistence = mock_graph_persistence(registered_paper)
    service = PipelineCompletionService(graph_persistence=persistence)

    with (
        patch(
            "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
            new_callable=AsyncMock,
        ),
        patch("backend.graph.store.GraphStore.save") as graph_store_save,
    ):
        service.finalize(
            registered_paper,
            graph_data=sample_graph.model_dump(mode="json"),
            classification_data=sample_classification.model_dump(mode="json"),
            full_text="no double write",
        )

    persistence.save.assert_called_once()
    graph_store_save.assert_not_called()
