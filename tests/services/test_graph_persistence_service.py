"""Tests for GraphPersistenceService."""

from unittest.mock import MagicMock

import pytest

from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.errors import ServiceError
from backend.services.graph_persistence_service import GraphPersistenceService


def test_save_delegates_to_store(sample_graph: UnifiedPaperGraph) -> None:
    store = MagicMock()
    service = GraphPersistenceService(store=store)
    service.save(sample_graph)
    store.save.assert_called_once_with(sample_graph)


def test_save_wraps_store_exception(sample_graph: UnifiedPaperGraph) -> None:
    store = MagicMock()
    store.save.side_effect = OSError("disk full")
    service = GraphPersistenceService(store=store)
    with pytest.raises(ServiceError) as err:
        service.save(sample_graph)
    assert err.value.code == "PIPELINE_FAILED"
    assert "disk full" in err.value.message


def test_save_accepts_minimal_valid_graph() -> None:
    graph = UnifiedPaperGraph(
        paper_id="g1",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="L", type="Thesis")],
        edges=[],
    )
    store = MagicMock()
    GraphPersistenceService(store=store).save(graph)
    assert store.save.call_args[0][0].paper_id == "g1"
