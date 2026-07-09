"""Method overlap patrol logic (RAG Phase 3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from backend.llm.client import LlmClient
from backend.patrol.llm_summary import generate_patrol_summary
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.patrol import (
    MethodOverlapPoint,
    NodeRef,
    PatrolInsight,
    PatrolInsightStatus,
    PatrolMode,
)

if TYPE_CHECKING:
    from backend.rag.vector_store import VectorStore

METHOD_OVERLAP_INSIGHT_ID = "ins-method-overlap-001"
METHOD_OVERLAP_TITLE = "方法重叠（Method Overlap）"
METHOD_OVERLAP_QUERY_TEXT = "method dataset experimental setup"
METHOD_TOP_K = 3


def method_nodes(graph: UnifiedPaperGraph | None) -> list[GraphNode]:
    if graph is None:
        return []
    return [node for node in graph.nodes if node.type == NodeType.METHOD]


def dataset_nodes(graph: UnifiedPaperGraph | None) -> list[GraphNode]:
    if graph is None:
        return []
    return [node for node in graph.nodes if node.type == NodeType.DATASET]


def _primary_node(nodes: list[GraphNode]) -> GraphNode | None:
    return nodes[0] if nodes else None


async def build_method_overlap_insight(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    vector_store: VectorStore | None = None,
    llm_client: LlmClient | None = None,
) -> PatrolInsight | None:
    """Compare methods and datasets across two STEM papers."""
    if len(paper_ids) != 2:
        return None

    left_id, right_id = paper_ids
    left_graph = graphs.get(left_id)
    right_graph = graphs.get(right_id)
    left_methods = method_nodes(left_graph)
    right_methods = method_nodes(right_graph)

    missing: list[str] = []
    if not left_methods:
        missing.append(left_id)
    if not right_methods:
        missing.append(right_id)
    if missing:
        summary = (
            f"由于对比文献 {'、'.join(missing)} 中缺乏方法（Method）数据，"
            "无法生成方法重叠巡检报告。建议补充文献内容或重新解析。"
        )
        return PatrolInsight(
            insight_id=METHOD_OVERLAP_INSIGHT_ID,
            title=METHOD_OVERLAP_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[],
        )

    left_primary = _primary_node(left_methods)
    right_primary = _primary_node(right_methods)
    assert left_primary is not None and right_primary is not None

    left_datasets = dataset_nodes(left_graph)
    right_datasets = dataset_nodes(right_graph)
    left_dataset = _primary_node(left_datasets)
    right_dataset = _primary_node(right_datasets)

    context = await _build_method_overlap_context(
        graphs,
        paper_ids,
        vector_store=vector_store,
    )
    llm_summary = await generate_patrol_summary(
        PatrolMode.METHOD_OVERLAP,
        context,
        llm_client=llm_client,
    )
    summary = llm_summary or _fallback_method_overlap_summary(
        left_primary.label,
        right_primary.label,
    )

    point = MethodOverlapPoint(
        mode="method_overlap",
        method=left_primary.label,
        paper_a_usage=left_primary.label,
        paper_b_usage=right_primary.label,
        dataset_a=left_dataset.label if left_dataset else None,
        dataset_b=right_dataset.label if right_dataset else None,
    )

    return PatrolInsight(
        insight_id=METHOD_OVERLAP_INSIGHT_ID,
        title=METHOD_OVERLAP_TITLE,
        summary=summary,
        status=PatrolInsightStatus.READY,
        paper_ids=[left_id, right_id],
        node_refs=[
            NodeRef(paper_id=left_id, node_id=left_primary.id, label=left_primary.label),
            NodeRef(paper_id=right_id, node_id=right_primary.id, label=right_primary.label),
        ],
        structured_points=[point],
    )


async def _build_method_overlap_context(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    vector_store: VectorStore | None = None,
) -> str:
    sections: list[str] = []
    for paper_id in paper_ids:
        graph = graphs.get(paper_id)
        if graph is None:
            continue
        method_labels = [node.label for node in method_nodes(graph)]
        dataset_labels = [node.label for node in dataset_nodes(graph)]
        section = (
            f"paper_id={paper_id}\n"
            f"Method: {', '.join(method_labels) or '（无）'}\n"
            f"Dataset: {', '.join(dataset_labels) or '（无）'}"
        )
        sections.append(section)

    if vector_store is not None:
        for paper_id in paper_ids:
            chunks = await vector_store.query_chunks(
                METHOD_OVERLAP_QUERY_TEXT,
                paper_id=paper_id,
                top_k=METHOD_TOP_K,
            )
            if chunks:
                sections.append(f"paper_id={paper_id} 相关段落：\n" + "\n".join(f"- {chunk.text}" for chunk in chunks))

    return "\n\n".join(sections)


def _fallback_method_overlap_summary(left_method: str, right_method: str) -> str:
    if left_method == right_method:
        return f"两篇论文均使用了「{left_method}」方法，建议进一步比对具体使用场景、超参数配置与数据集差异。"
    return (
        f"两篇论文分别采用「{left_method}」与「{right_method}」方法，"
        "当前图谱中未检出显著方法重叠，建议结合实验段落进一步核验。"
    )
