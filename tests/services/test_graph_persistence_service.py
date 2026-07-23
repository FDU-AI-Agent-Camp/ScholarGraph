# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for GraphPersistenceService."""

import asyncio
from unittest.mock import MagicMock

import pytest
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.errors import ServiceError
from backend.services.graph_persistence_service import GraphPersistenceService


@pytest.mark.asyncio
async def test_save_delegates_to_store(sample_graph: UnifiedPaperGraph) -> None:
    store = MagicMock()
    store.graph_path_for.return_value = "/data/graphs/g1.json"
    service = GraphPersistenceService(store=store)
    graph_path = await service.save(sample_graph)
    store.save.assert_called_once_with(sample_graph)
    assert graph_path == "/data/graphs/g1.json"


@pytest.mark.asyncio
async def test_save_offloads_store_io_to_thread(
    sample_graph: UnifiedPaperGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disk write must leave the event loop via asyncio.to_thread."""
    store = MagicMock()
    store.graph_path_for.return_value = "/data/graphs/g1.json"
    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def fake_to_thread(fn: object, /, *args: object, **kwargs: object) -> object:
        calls.append((fn, args, kwargs))
        assert callable(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    service = GraphPersistenceService(store=store)
    graph_path = await service.save(sample_graph)

    assert graph_path == "/data/graphs/g1.json"
    assert len(calls) == 1
    assert calls[0][0] == store.save
    assert calls[0][1] == (sample_graph,)
    store.save.assert_called_once_with(sample_graph)


@pytest.mark.asyncio
async def test_save_wraps_store_exception(sample_graph: UnifiedPaperGraph) -> None:
    store = MagicMock()
    store.save.side_effect = OSError("disk full")
    service = GraphPersistenceService(store=store)
    with pytest.raises(ServiceError) as err:
        await service.save(sample_graph)
    assert err.value.code == "PIPELINE_FAILED"
    assert "disk full" in err.value.message


@pytest.mark.asyncio
async def test_save_accepts_minimal_valid_graph() -> None:
    graph = UnifiedPaperGraph(
        paper_id="g1",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="L", type="Thesis")],
        edges=[],
    )
    store = MagicMock()
    await GraphPersistenceService(store=store).save(graph)
    assert store.save.call_args[0][0].paper_id == "g1"
