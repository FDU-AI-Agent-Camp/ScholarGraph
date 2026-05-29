"""Patrol orchestration entry (BE-4)."""

from collections.abc import Callable
from datetime import UTC, datetime

from backend.graph.store import GraphStore
from backend.patrol.errors import PatrolError
from backend.patrol.lens_clash import build_lens_clash_insight
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.patrol import PatrolMode, PatrolReport

PATROL_PAPER_COUNT = 2
GraphLoader = Callable[[str], UnifiedPaperGraph | None]


async def run_patrol(
    paper_ids: list[str],
    mode: PatrolMode,
    *,
    store: GraphStore | None = None,
    graph_loader: GraphLoader | None = None,
) -> PatrolReport:
    """Run community patrol for exactly two papers."""
    if len(paper_ids) != PATROL_PAPER_COUNT:
        raise PatrolError(
            "PATROL_INVALID_REQUEST",
            f"paper_ids 须恰好 {PATROL_PAPER_COUNT} 篇",
            status_code=400,
        )

    if mode == PatrolMode.CONTRADICTION:
        raise PatrolError(
            "PATROL_UNSUPPORTED_MODE",
            "contradiction 模式尚未实现",
            status_code=501,
        )

    load_graph = graph_loader or _default_graph_loader(store)
    graphs = _load_graphs(paper_ids, load_graph)

    if mode == PatrolMode.LENS_CLASH:
        insight = build_lens_clash_insight(graphs, paper_ids)
        if insight is None:
            raise PatrolError(
                "PATROL_INSUFFICIENT_DATA",
                "未找到可比较的 AnalyticalLens 节点",
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
