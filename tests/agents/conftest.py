"""BE-2 agent tests exercise heuristic classify/extract, not mock_agents."""

from __future__ import annotations

import pytest
from backend.config import get_settings
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def minimal_valid_llm_graph(
    *,
    paper_id: str = "ignored",
    paradigm: Paradigm = Paradigm.HSS,
    summary: str | None = None,
) -> UnifiedPaperGraph:
    """LLM graph fixture that passes ``_validate_llm_graph`` (nodes + edges present)."""
    if paradigm == Paradigm.HSS:
        node_type = "Thesis"
        edge_type = "REF"
    else:
        node_type = "Method"
        edge_type = "RELATES_TO"
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=paradigm,
        nodes=[GraphNode(id="n1", label="core", type=node_type)],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label=edge_type, type=edge_type)],
        summary=summary,
    )


@pytest.fixture(autouse=True)
def be2_heuristic_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    get_settings.cache_clear()
