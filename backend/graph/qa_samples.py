"""M2 eval graph seeds and canonical questions (see docs/v1/eval/qa_samples.md)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.graph.store import GraphStore
from backend.llm.qa_scale import QuestionScale
from backend.schemas.graph import UnifiedPaperGraph

M2_DEMO_PAPER_ID = "hss-001"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


@dataclass(frozen=True, slots=True)
class M2QuestionSample:
    """One M2 acceptance question with expected scale and citable node types."""

    scale: QuestionScale
    question: str
    expected_node_types: tuple[str, ...]


M2_HSS_QUESTIONS: tuple[M2QuestionSample, ...] = (
    M2QuestionSample(
        scale="summary",
        question="这篇论文做了什么？请给出核心论点总览。",
        expected_node_types=("Thesis",),
    ),
    M2QuestionSample(
        scale="detail",
        question="分论点如何支撑核心论点？",
        expected_node_types=("SubArgument", "Thesis"),
    ),
    M2QuestionSample(
        scale="verification",
        question="核心论点通过哪些材料、经何种理论视角被论证？",
        expected_node_types=("AnalyticalLens", "ObjectOrData", "Thesis"),
    ),
)


def load_m2_demo_graph() -> UnifiedPaperGraph:
    """Load the canonical hss-001 graph used for M2 smoke / eval."""
    payload = json.loads((FIXTURES_DIR / "graph-hss.json").read_text(encoding="utf-8"))
    return UnifiedPaperGraph.model_validate(payload["data"])


def seed_m2_qa_graph(store_dir: Path, *, paper_id: str = M2_DEMO_PAPER_ID) -> GraphStore:
    """Write the M2 demo graph to *store_dir* for CLI smoke tests."""
    store = GraphStore(base_dir=store_dir)
    graph = load_m2_demo_graph().model_copy(update={"paper_id": paper_id})
    store.save(graph)
    return store
