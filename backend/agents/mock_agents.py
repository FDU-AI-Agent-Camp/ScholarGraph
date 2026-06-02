"""Fixture-backed classify/extract stand-ins when ``LLM_MODE=mock``."""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"

_STEM_KEYWORDS: tuple[str, ...] = (
    "machine learning",
    "dataset",
    "baseline",
    "experiment",
    "gnn",
    "transformer",
    "crystal",
    "accuracy",
    "metrics",
    "neural network",
)

_HSS_KEYWORDS: tuple[str, ...] = (
    "夏尔巴",
    "父系",
    "电影",
    "政治传播",
    "论点",
    "理论",
    "史料",
    "民族",
    "传播",
)


def mock_classify(classifier_input: str) -> ParadigmClassification:
    """Heuristic paradigm classification for local pipeline / eval smoke."""
    text = classifier_input.lower()
    stem_score = sum(1 for kw in _STEM_KEYWORDS if kw in text)
    hss_score = sum(1 for kw in _HSS_KEYWORDS if kw in text)

    if stem_score > hss_score:
        return ParadigmClassification(
            paradigm=Paradigm.STEM,
            confidence=min(0.95, 0.7 + stem_score * 0.05),
            reason="Mock：检测到 STEM 关键词（实验/方法/数据集等）",
        )
    return ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=min(0.95, 0.7 + max(hss_score, 1) * 0.05),
        reason="Mock：检测到 HSS 关键词（论证/理论/材料等）",
    )


def mock_extract(full_text: str, paradigm: Paradigm) -> UnifiedPaperGraph:
    """Return a fixture graph for mock pipeline runs (no cloud LLM)."""
    _ = full_text
    if paradigm == Paradigm.HSS:
        payload = json.loads((FIXTURES_DIR / "graph-hss.json").read_text(encoding="utf-8"))
        return UnifiedPaperGraph.model_validate(payload["data"])

    return UnifiedPaperGraph(
        paper_id="mock-stem",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="n_rq", label="晶体性质预测问题", type="ResearchQuestion", data={}),
            GraphNode(id="n_method", label="Transformer 原子嵌入", type="Method", data={}),
            GraphNode(id="n_claim", label="优于 GNN 基线", type="Claim", data={}),
            GraphNode(id="n_evidence", label="Materials Project 基准实验", type="Evidence", data={}),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n_method",
                target="n_claim",
                label="SUPPORTS",
                type="SUPPORTS",
            ),
            GraphEdge(
                id="e2",
                source="n_evidence",
                target="n_claim",
                label="SUPPORTS",
                type="SUPPORTS",
            ),
        ],
    )
