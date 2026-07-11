"""Method overlap patrol logic (RAG Phase 3)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from backend.config import get_settings
from backend.llm.client import LlmClient
from backend.llm.embeddings import EmbeddingClient, get_embedding_client
from backend.patrol.llm_summary import generate_method_overlap_summary
from backend.patrol.method_overlap_semantic import find_semantic_method_overlap
from backend.patrol.overlap_anchor import _OverlapAnchor
from backend.patrol.rag_service import PatrolRAGService
from backend.patrol.similarity import normalize_label
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol import (
    MethodOverlapPoint,
    NodeRef,
    OverlapType,
    PatrolInsight,
    PatrolInsightStatus,
    PatrolMode,
)
from backend.schemas.patrol_llm import MethodComparativeDetail, MethodOverlapOutput

if TYPE_CHECKING:
    from backend.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

METHOD_OVERLAP_INSIGHT_ID = "ins-method-overlap-001"
METHOD_OVERLAP_TITLE = "方法重叠（Method Overlap）"


def method_nodes(graph: UnifiedPaperGraph | None) -> list[GraphNode]:
    if graph is None:
        return []
    return [node for node in graph.nodes if node.type == NodeType.METHOD]


def dataset_nodes(graph: UnifiedPaperGraph | None) -> list[GraphNode]:
    if graph is None:
        return []
    return [node for node in graph.nodes if node.type == NodeType.DATASET]


def _extract_usage(node: GraphNode) -> str:
    """Extract a usage description for a method node.

    Priority:
    1. ``node.data["usage"]`` if present and non-empty.
    2. ``node.data["description"]`` if present and non-empty.
    3. MVP fallback template ``"用于 {label}"``.
    """
    data = node.data or {}
    for key in ("usage", "description"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"用于 {node.label}"


def _find_overlap_pairs(
    left_nodes: list[GraphNode],
    right_nodes: list[GraphNode],
    overlap_kind: OverlapType,
) -> list[_OverlapAnchor]:
    """Return all literal-label overlap anchors between two node lists.

    For each shared normalized label we create one anchor using the first
    occurrence on each side.  Additional occurrences are tracked via node_refs
    by the caller.
    """
    right_by_label: dict[str, list[GraphNode]] = {}
    for node in right_nodes:
        right_by_label.setdefault(normalize_label(node.label), []).append(node)

    seen: set[str] = set()
    anchors: list[_OverlapAnchor] = []
    for left_node in left_nodes:
        normalized = normalize_label(left_node.label)
        if normalized in seen:
            continue
        right_matches = right_by_label.get(normalized)
        if not right_matches:
            continue
        seen.add(normalized)
        anchors.append(
            _OverlapAnchor(
                left_node=left_node,
                right_node=right_matches[0],
                overlap_kind=overlap_kind,
                match_type="literal",
                overlap_score=1.0,
            )
        )
    return anchors


def _dedupe_node_refs(refs: list[NodeRef]) -> list[NodeRef]:
    seen: set[tuple[str, str]] = set()
    unique: list[NodeRef] = []
    for ref in refs:
        key = (ref.paper_id, ref.node_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def _node_refs_for_anchors(
    anchors: list[_OverlapAnchor],
    left_nodes: list[GraphNode],
    right_nodes: list[GraphNode],
    left_id: str,
    right_id: str,
) -> list[NodeRef]:
    """Collect node refs for all literal occurrences sharing each anchor label."""
    refs: list[NodeRef] = []
    for anchor in anchors:
        normalized = normalize_label(anchor.left_node.label)
        for node in left_nodes:
            if normalize_label(node.label) == normalized:
                refs.append(NodeRef(paper_id=left_id, node_id=node.id, label=node.label))
        right_normalized = normalize_label(anchor.right_node.label)
        for node in right_nodes:
            if normalize_label(node.label) == right_normalized:
                refs.append(NodeRef(paper_id=right_id, node_id=node.id, label=node.label))
    return _dedupe_node_refs(refs)


async def build_method_overlap_insight(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    vector_store: VectorStore | None = None,
    llm_client: LlmClient | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> PatrolInsight | None:
    """Compare methods and datasets across two STEM papers."""
    if len(paper_ids) != 2:
        return None

    left_id, right_id = paper_ids
    left_graph = graphs.get(left_id)
    right_graph = graphs.get(right_id)

    # Paradigm gate: method overlap is only semantically meaningful for STEM.
    # HSS papers are centred around AnalyticalLens / Thesis, so short-circuit.
    if (left_graph is not None and left_graph.paradigm == Paradigm.HSS) or (
        right_graph is not None and right_graph.paradigm == Paradigm.HSS
    ):
        logger.info("skipped_due_to_paradigm_mismatch", extra={"paper_ids": [left_id, right_id]})
        summary = (
            f"方法重叠（Method Overlap）模式仅适用于 STEM 范式论文；"
            f"当前文献 {left_id} 或 {right_id} 属于 HSS 范式，不进行方法重叠分析。"
        )
        return PatrolInsight(
            insight_id=METHOD_OVERLAP_INSIGHT_ID,
            title=METHOD_OVERLAP_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[],
        )

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

    left_datasets = dataset_nodes(left_graph)
    right_datasets = dataset_nodes(right_graph)

    method_anchors = _find_overlap_pairs(left_methods, right_methods, OverlapType.METHOD)
    dataset_anchors = _find_overlap_pairs(left_datasets, right_datasets, OverlapType.DATASET)

    if not method_anchors:
        settings = get_settings()
        if settings.enable_patrol_semantic_path:
            client = embedding_client or get_embedding_client()
            assert left_graph is not None and right_graph is not None
            semantic_anchor = await find_semantic_method_overlap(
                left_graph,
                right_graph,
                left_methods,
                right_methods,
                client,
                settings.patrol_semantic_threshold,
                settings.patrol_max_matrix_size,
                rq_threshold=settings.patrol_claim_rq_threshold_effective(
                    *(node.label for node in left_methods + right_methods),
                ),
            )
            if semantic_anchor is not None:
                method_anchors = [semantic_anchor]
        else:
            logger.info(
                "skipped_due_to_semantic_path_disabled",
                extra={"paper_ids": [left_id, right_id]},
            )

    active_dataset_anchors = dataset_anchors if method_anchors else []

    if not method_anchors and dataset_anchors:
        active_dataset_anchors = dataset_anchors

    if not method_anchors and not active_dataset_anchors:
        summary = f"两篇论文 {left_id} 与 {right_id} 的方法与数据集均无显著重合，无法生成方法重叠巡检报告。"
        return PatrolInsight(
            insight_id=METHOD_OVERLAP_INSIGHT_ID,
            title=METHOD_OVERLAP_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[],
        )

    algorithm_anchors = method_anchors + active_dataset_anchors

    context, meta = await _build_method_overlap_context(
        graphs,
        paper_ids,
        algorithm_anchors=algorithm_anchors,
        vector_store=vector_store,
    )
    llm_output = await generate_method_overlap_summary(
        context,
        llm_client=llm_client,
    )

    summary = _derive_summary(
        method_anchors,
        active_dataset_anchors,
        llm_output,
        left_id,
        right_id,
    )

    points = _build_method_overlap_points(
        method_anchors,
        active_dataset_anchors,
        left_id=left_id,
        right_id=right_id,
        left_methods=left_methods,
        right_methods=right_methods,
        left_datasets=left_datasets,
        right_datasets=right_datasets,
        llm_output=llm_output,
    )

    node_refs = _dedupe_node_refs([ref for point in points for ref in point.node_refs])

    return PatrolInsight(
        insight_id=METHOD_OVERLAP_INSIGHT_ID,
        title=METHOD_OVERLAP_TITLE,
        summary=summary,
        status=PatrolInsightStatus.READY,
        paper_ids=[left_id, right_id],
        node_refs=node_refs,
        structured_points=points,
        meta=meta,
    )


def _render_method_overlap_query(
    graph: UnifiedPaperGraph,
    template: str,
    anchors: list[_OverlapAnchor],
) -> str:
    """Render the VectorStore query from aligned anchors and graph labels.

    The aligned anchor labels (e.g. the overlapping method/dataset) are injected
    as {anchor_labels} so the recall focuses on the intersection entity rather
    than all methods/datasets in the paper.
    """
    method_labels = " ".join(node.label for node in method_nodes(graph))
    dataset_labels = " ".join(node.label for node in dataset_nodes(graph))

    anchor_labels = " ".join(
        dict.fromkeys(node.label for anchor in anchors for node in (anchor.left_node, anchor.right_node) if node.label)
    )
    return template.format(
        anchor_labels=anchor_labels,
        method_labels=method_labels,
        dataset_labels=dataset_labels,
    )


async def _build_method_overlap_context(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    algorithm_anchors: list[_OverlapAnchor],
    vector_store: VectorStore | None = None,
) -> tuple[str, dict[str, Any]]:
    settings = get_settings()
    sections: list[str] = []
    paper_queries: dict[str, str] = {}
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
        paper_queries[paper_id] = _render_method_overlap_query(
            graph,
            settings.patrol_method_overlap_query_template,
            algorithm_anchors,
        )

    if algorithm_anchors:
        pair_lines = [f"- {anchor.pair_label} ({anchor.overlap_kind.value})" for anchor in algorithm_anchors]
        sections.append(
            "以下重叠对已由算法确认存在显著重合，请在 comparison_details 中为每一对生成结构化对比：\n"
            + "\n".join(pair_lines)
        )

    rag_service = PatrolRAGService(vector_store)
    rag_sections, meta = await rag_service.enrich_context(
        PatrolMode.METHOD_OVERLAP,
        paper_queries,
    )
    sections.extend(rag_sections)

    return "\n\n".join(sections), meta


def _match_llm_detail(
    anchor: _OverlapAnchor,
    details: list[MethodComparativeDetail],
) -> MethodComparativeDetail | None:
    """Align an algorithm-discovered anchor with an LLM-generated detail."""
    if anchor.overlap_kind == OverlapType.DATASET:
        return _match_llm_detail_dataset(anchor, details)
    return _match_llm_detail_method(anchor, details)


def _match_llm_detail_method(
    anchor: _OverlapAnchor,
    details: list[MethodComparativeDetail],
) -> MethodComparativeDetail | None:
    """Match method anchors to LLM comparison_details without dataset cross-talk."""
    left_label = anchor.left_node.label
    right_label = anchor.right_node.label
    expected = anchor.pair_label

    for detail in details:
        if detail.method_pair_name == expected:
            return detail

    for detail in details:
        name = detail.method_pair_name
        if left_label in name and right_label in name:
            return detail

    for detail in details:
        name = detail.method_pair_name
        if left_label in name or right_label in name:
            return detail

    return None


def _match_llm_detail_dataset(
    anchor: _OverlapAnchor,
    details: list[MethodComparativeDetail],
) -> MethodComparativeDetail | None:
    """Match dataset anchors only when the LLM names the dataset pair explicitly."""
    expected = anchor.pair_label
    label = anchor.overlap_label

    for detail in details:
        if detail.method_pair_name == expected:
            return detail

    for detail in details:
        name = detail.method_pair_name
        if label in name and normalize_label(label) in {normalize_label(token) for token in name.split("<->")}:
            return detail

    return None


def _derive_summary(
    method_anchors: list[_OverlapAnchor],
    dataset_anchors: list[_OverlapAnchor],
    llm_output: MethodOverlapOutput | None,
    left_id: str,
    right_id: str,
) -> str:
    """Return the patrol summary, preferring LLM output and falling back to templates."""
    if llm_output is not None and llm_output.summary.strip():
        return llm_output.summary.strip()

    if method_anchors and dataset_anchors:
        method_pairs = "; ".join(anchor.pair_label for anchor in method_anchors)
        dataset_labels = "; ".join(dict.fromkeys(anchor.overlap_label for anchor in dataset_anchors))
        return (
            f"两篇论文 {left_id} 与 {right_id} 在方法层面存在重叠（{method_pairs}），"
            f"且共享数据集（{dataset_labels}）。建议分别比对方法使用场景与实验数据语境。"
        )

    if not method_anchors and dataset_anchors:
        dataset_labels = "; ".join(dict.fromkeys(anchor.overlap_label for anchor in dataset_anchors))
        return f"两篇论文均使用「{dataset_labels}」数据集，建议结合实验段落进一步核验数据重叠的具体含义。"

    pair_labels = [anchor.pair_label for anchor in method_anchors]
    return (
        f"两篇论文 {left_id} 与 {right_id} 在方法层面存在显著重叠："
        f"{'; '.join(pair_labels)}。建议进一步比对具体使用场景与实验差异。"
    )


def _build_method_overlap_points(
    method_anchors: list[_OverlapAnchor],
    dataset_anchors: list[_OverlapAnchor],
    *,
    left_id: str,
    right_id: str,
    left_methods: list[GraphNode],
    right_methods: list[GraphNode],
    left_datasets: list[GraphNode],
    right_datasets: list[GraphNode],
    llm_output: MethodOverlapOutput | None,
) -> list[MethodOverlapPoint]:
    """Flatten dual overlaps into isolated method and dataset points."""
    details = llm_output.comparison_details if llm_output is not None else []
    points: list[MethodOverlapPoint] = []
    for anchor in method_anchors:
        detail = _match_llm_detail_method(anchor, details)
        points.append(
            _build_single_method_overlap_point(
                anchor,
                node_refs=_node_refs_for_anchors([anchor], left_methods, right_methods, left_id, right_id),
                detail=detail,
            )
        )
    for anchor in dataset_anchors:
        detail = _match_llm_detail_dataset(anchor, details)
        points.append(
            _build_single_method_overlap_point(
                anchor,
                node_refs=_node_refs_for_anchors([anchor], left_datasets, right_datasets, left_id, right_id),
                detail=detail,
            )
        )
    return points


def _build_single_method_overlap_point(
    anchor: _OverlapAnchor,
    *,
    node_refs: list[NodeRef],
    detail: MethodComparativeDetail | None,
) -> MethodOverlapPoint:
    """Create one MethodOverlapPoint anchored to a single overlap kind."""
    if detail is not None:
        paper_a_usage = detail.paper_a_usage.strip()
        paper_b_usage = detail.paper_b_usage.strip()
        evidence_summary = detail.evidence_summary.strip() or None
    else:
        paper_a_usage = _extract_usage(anchor.left_node)
        paper_b_usage = _extract_usage(anchor.right_node)
        evidence_summary = None

    overlap_kind = anchor.overlap_kind
    return MethodOverlapPoint(
        mode="method_overlap",
        overlap_type=overlap_kind,
        overlap_label=anchor.overlap_label,
        overlap_score=anchor.overlap_score,
        match_type=anchor.match_type,
        node_refs=node_refs,
        paper_a_usage=paper_a_usage,
        paper_b_usage=paper_b_usage,
        dataset_a=anchor.left_node.label if overlap_kind == OverlapType.DATASET else None,
        dataset_b=anchor.right_node.label if overlap_kind == OverlapType.DATASET else None,
        evidence_summary=evidence_summary,
    )
