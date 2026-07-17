# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Patrol orchestration entry (BE-4)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backend.graph.store import GraphStore
from backend.llm.client import LlmClient
from backend.llm.embeddings import EmbeddingClient
from backend.patrol.claim_evolution import build_claim_evolution_insight
from backend.patrol.contradiction import build_contradiction_insight
from backend.patrol.errors import PatrolError
from backend.patrol.lens_clash import build_lens_clash_insight
from backend.patrol.method_overlap import build_method_overlap_insight
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.patrol import PatrolMode, PatrolReport

if TYPE_CHECKING:
    from backend.rag.vector_store import VectorStore

PATROL_PAPER_COUNT = 2
GraphLoader = Callable[[str], UnifiedPaperGraph | None]


async def run_patrol(
    paper_ids: list[str],
    mode: PatrolMode,
    *,
    store: GraphStore | None = None,
    graph_loader: GraphLoader | None = None,
    vector_store: VectorStore | None = None,
    embedding_client: EmbeddingClient | None = None,
    llm_client: LlmClient | None = None,
) -> PatrolReport:
    """Run community patrol for exactly two papers."""
    if len(paper_ids) != PATROL_PAPER_COUNT:
        raise PatrolError(
            "PATROL_INVALID_REQUEST",
            f"paper_ids 须恰好 {PATROL_PAPER_COUNT} 篇",
            status_code=400,
        )

    load_graph = graph_loader or _default_graph_loader(store)
    graphs = _load_graphs(paper_ids, load_graph)

    if mode == PatrolMode.LENS_CLASH:
        insight = await build_lens_clash_insight(graphs, paper_ids, llm_client=llm_client)
        if insight is None:
            raise PatrolError(
                "PATROL_INSUFFICIENT_DATA",
                "未找到可比较的 AnalyticalLens 节点",
                status_code=422,
            )
        insights = [insight]
    elif mode == PatrolMode.CONTRADICTION:
        insight = await build_contradiction_insight(
            graphs,
            paper_ids,
            vector_store=vector_store,
            llm_client=llm_client,
        )
        if insight is None:
            raise PatrolError(
                "PATROL_INSUFFICIENT_DATA",
                "无法构建矛盾巡检洞察",
                status_code=422,
            )
        insights = [insight]
    elif mode == PatrolMode.METHOD_OVERLAP:
        insight = await build_method_overlap_insight(
            graphs,
            paper_ids,
            vector_store=vector_store,
            embedding_client=embedding_client,
            llm_client=llm_client,
        )
        if insight is None:
            raise PatrolError(
                "PATROL_INSUFFICIENT_DATA",
                "无法构建方法重叠巡检洞察",
                status_code=422,
            )
        insights = [insight]
    elif mode == PatrolMode.CLAIM_EVOLUTION:
        insight = await build_claim_evolution_insight(
            graphs,
            paper_ids,
            vector_store=vector_store,
            embedding_client=embedding_client,
            llm_client=llm_client,
        )
        if insight is None:
            raise PatrolError(
                "PATROL_INSUFFICIENT_DATA",
                "无法构建观点演进巡检洞察",
                status_code=422,
            )
        insights = [insight]
    else:
        raise PatrolError(
            "PATROL_UNSUPPORTED_MODE",
            f"不支持的巡检模式: {mode.value}",
            status_code=400,
        )

    return PatrolReport(
        mode=mode,
        paper_ids=list(paper_ids),
        insights=insights,
        generated_at=datetime.now(UTC),
    )


def _default_graph_loader(store: GraphStore | None) -> GraphLoader:
    graph_store = store or GraphStore()

    def load(paper_id: str) -> UnifiedPaperGraph | None:
        return graph_store.load(paper_id)

    return load


def _load_graphs(
    paper_ids: list[str],
    load_graph: GraphLoader,
) -> dict[str, UnifiedPaperGraph]:
    graphs: dict[str, UnifiedPaperGraph] = {}
    for paper_id in paper_ids:
        graph = load_graph(paper_id)
        if graph is None:
            raise PatrolError(
                "GRAPH_NOT_READY",
                f"图谱未就绪: {paper_id}",
                status_code=409,
            )
        graphs[paper_id] = graph
    return graphs
