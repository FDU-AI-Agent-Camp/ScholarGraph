"""M1 eval — UnifiedPaperGraph schema coverage per paradigm (A-08).

Green: fixture graphs validate + GraphStore round-trip (CI default).
Red: extract() produces valid graphs from corpus (``pytest -m red`` until BE-2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.agents.extractor import extract
from backend.graph.store import GraphStore
from backend.ingest.pdf import ingest_pdf
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from pydantic import ValidationError

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


def _load_graph_fixture(name: str) -> UnifiedPaperGraph:
    payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return UnifiedPaperGraph.model_validate(payload["data"])


def test_m1_hss_fixture_graph_passes_schema() -> None:
    graph = _load_graph_fixture("graph-hss.json")
    assert graph.paradigm == Paradigm.HSS
    assert graph.nodes
    assert all(node.id and node.label and node.type for node in graph.nodes)
    assert all(edge.source and edge.target for edge in graph.edges)


def test_m1_stem_sample_graph_passes_schema() -> None:
    """STEM 范式样例图谱（测试内构造，待 BE-2 产出真实 JSON 后迁入 fixtures）。"""
    graph = UnifiedPaperGraph.model_validate(
        {
            "paper_id": "stem-001",
            "paradigm": "STEM",
            "nodes": [
                {"id": "n_claim", "label": "GNN 提升晶体性质预测", "type": "Claim", "data": {}},
                {"id": "n_method", "label": "Transformer 原子嵌入", "type": "Method", "data": {}},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "n_method",
                    "target": "n_claim",
                    "label": "SUPPORTS",
                    "type": "SUPPORTS",
                },
            ],
        },
    )
    assert graph.paradigm == Paradigm.STEM
    assert len(graph.nodes) >= 1


def test_m1_graph_store_persists_hss_and_stem(tmp_path: Path) -> None:
    store = GraphStore(base_dir=tmp_path)
    hss = _load_graph_fixture("graph-hss.json")
    stem = UnifiedPaperGraph.model_validate(
        {
            "paper_id": "stem-001",
            "paradigm": "STEM",
            "nodes": [
                {"id": "n_claim", "label": "GNN 提升晶体性质预测", "type": "Claim", "data": {}},
                {"id": "n_method", "label": "Transformer 原子嵌入", "type": "Method", "data": {}},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "n_method",
                    "target": "n_claim",
                    "label": "SUPPORTS",
                    "type": "SUPPORTS",
                },
            ],
        },
    )

    store.save(hss)
    store.save(stem)

    loaded_hss = store.load("hss-001")
    loaded_stem = store.load("stem-001")
    assert loaded_hss is not None and loaded_hss.paradigm == Paradigm.HSS
    assert loaded_stem is not None and loaded_stem.paradigm == Paradigm.STEM


@pytest.mark.red
@pytest.mark.parametrize(
    ("paper_id", "paradigm"),
    [
        ("stem-001", Paradigm.STEM),
        ("hss-001", Paradigm.HSS),
    ],
)
@pytest.mark.xfail(strict=True, reason="BE-2: extract() 尚未实现 — M1 真图谱待交付")
async def test_m1_extract_corpus_produces_valid_graph(paper_id: str, paradigm: Paradigm) -> None:
    """A-08 / M1: 各范式 ≥1 篇可解析 UnifiedPaperGraph。"""
    from tests.ingest.conftest import CORPUS_HSS, CORPUS_STEM

    pdf_path = CORPUS_STEM if paper_id == "stem-001" else CORPUS_HSS
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    full_text = (await ingest_pdf(pdf_path, paper_id=paper_id))["full_text"]
    graph = await extract(full_text, paradigm)

    assert graph.paradigm == paradigm
    assert graph.nodes
    assert all(node.type for node in graph.nodes)


def test_m1_unified_graph_rejects_invalid_paradigm() -> None:
    with pytest.raises(ValidationError):
        UnifiedPaperGraph.model_validate(
            {
                "paper_id": "bad-001",
                "paradigm": "NOT_A_PARADIGM",
                "nodes": [{"id": "n1", "label": "x", "type": "Thesis", "data": {}}],
                "edges": [],
            },
        )
