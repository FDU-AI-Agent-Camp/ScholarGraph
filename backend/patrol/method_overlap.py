"""Method overlap patrol logic (RAG Phase 3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

import numpy as np

from backend.config import get_settings
from backend.llm.client import LlmClient
from backend.llm.embeddings import EmbeddingClient, get_embedding_client
from backend.patrol.llm_summary import generate_method_overlap_summary
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.patrol import (
    MethodOverlapPoint,
    NodeRef,
    PatrolInsight,
    PatrolInsightStatus,
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


def _normalize(label: str) -> str:
    """Normalize a node label for overlap comparison."""
    return label.strip().lower()


def _extract_usage(node: GraphNode) -> str:
    """Extract a usage description for a method node.

    Priority:
    1. ``node.data["usage"]`` if present and non-empty.
    2. ``node.data["description"]`` if present and non-empty.
    3. MVP fallback template ``"用于 {label}"``.

    TODO: enrich with LLM-structured usage extraction once the summary
    generator returns per-paper usage fields.
    """
    data = node.data or {}
    for key in ("usage", "description"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"用于 {node.label}"


def _embed_text_for_node(node: GraphNode) -> str:
    """Build a single embedding text from a node's label and description."""
    parts = [node.label]
    description = (node.data or {}).get("description")
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    return " ".join(parts)


def _find_overlap(left_nodes: list[GraphNode], right_nodes: list[GraphNode]) -> list[str]:
    """Return overlapping labels (preserving left-side casing) between two node lists."""
    right_labels = {_normalize(node.label) for node in right_nodes}
    seen: set[str] = set()
    overlaps: list[str] = []
    for node in left_nodes:
        normalized = _normalize(node.label)
        if normalized in right_labels and normalized not in seen:
            overlaps.append(node.label)
            seen.add(normalized)
    return overlaps


def _cosine_similarity_matrix(
    left_vectors: list[list[float]],
    right_vectors: list[list[float]],
) -> np.ndarray:
    """Compute the cross cosine-similarity matrix between two vector sets."""
    left = np.asarray(left_vectors, dtype=np.float64)
    right = np.asarray(right_vectors, dtype=np.float64)
    left_norms = np.linalg.norm(left, axis=1, keepdims=True)
    right_norms = np.linalg.norm(right, axis=1, keepdims=True)
    # Avoid division by zero; zero vectors will produce all-zero similarities.
    left_norms[left_norms == 0] = 1.0
    right_norms[right_norms == 0] = 1.0
    left_normalized = left / left_norms
    right_normalized = right / right_norms
    return left_normalized @ right_normalized.T


async def _find_semantic_method_overlap(
    left_methods: list[GraphNode],
    right_methods: list[GraphNode],
    embedding_client: EmbeddingClient,
    threshold: float,
    max_matrix_size: int,
) -> tuple[GraphNode, GraphNode, float] | None:
    """Find the strongest semantic method overlap across two papers.

    Returns the best matching left/right node pair plus the cosine score,
    or ``None`` when no pair exceeds the threshold or the matrix is too large.
    """
    if not left_methods or not right_methods:
        return None

    # Mock embeddings are deterministic but not semantically meaningful, so skip
    # the soft path to avoid false positives in test/local mock runs.
    if getattr(embedding_client, "is_mock", False):
        return None

    matrix_size = len(left_methods) * len(right_methods)
    if matrix_size > max_matrix_size:
        return None

    texts = [_embed_text_for_node(node) for node in left_methods + right_methods]
    vectors = await embedding_client.embed_texts(texts)
    if len(vectors) != len(texts):
        return None

    split_at = len(left_methods)
    similarity = _cosine_similarity_matrix(vectors[:split_at], vectors[split_at:])
    if similarity.size == 0:
        return None

    best_index = int(np.argmax(similarity))
    best_flat = np.unravel_index(best_index, similarity.shape)
    best_score = float(similarity[best_flat])
    if best_score < threshold:
        return None

    left_idx, right_idx = best_flat
    return left_methods[left_idx], right_methods[right_idx], best_score


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

    method_overlap = _find_overlap(left_methods, right_methods)
    dataset_overlap = _find_overlap(left_datasets, right_datasets)

    overlap_label: str | None = None
    overlap_score: float | None = None
    overlap_type: Literal["literal", "semantic"] | None = None
    left_primary: GraphNode | None = None
    right_primary: GraphNode | None = None
    node_refs: list[NodeRef] = []

    if method_overlap:
        # Hard path: literal label equality is considered fully significant.
        overlap_label = method_overlap[0]
        overlap_score = 1.0
        overlap_type = "literal"
        normalized_overlap = _normalize(overlap_label)
        matched_left = [node for node in left_methods if _normalize(node.label) == normalized_overlap]
        matched_right = [node for node in right_methods if _normalize(node.label) == normalized_overlap]
        left_primary = matched_left[0]
        right_primary = matched_right[0]
        node_refs.extend(
            NodeRef(paper_id=paper_id, node_id=node.id, label=node.label)
            for paper_id, nodes in ((left_id, matched_left), (right_id, matched_right))
            for node in nodes
        )
    else:
        # Soft path: use semantic embeddings for method nodes that do not match literally.
        settings = get_settings()
        client = embedding_client or get_embedding_client()
        semantic_match = await _find_semantic_method_overlap(
            left_methods,
            right_methods,
            client,
            settings.patrol_semantic_threshold,
            settings.patrol_max_matrix_size,
        )
        if semantic_match:
            left_primary, right_primary, overlap_score = semantic_match
            overlap_label = left_primary.label
            overlap_type = "semantic"
            node_refs.extend(
                [
                    NodeRef(paper_id=left_id, node_id=left_primary.id, label=left_primary.label),
                    NodeRef(paper_id=right_id, node_id=right_primary.id, label=right_primary.label),
                ]
            )
        elif dataset_overlap:
            # Fall back to dataset literal overlap when no method overlap is found.
            overlap_label = dataset_overlap[0]
            overlap_score = 1.0
            overlap_type = "literal"
            left_primary = _primary_node(left_methods)
            right_primary = _primary_node(right_methods)
            assert left_primary is not None and right_primary is not None
            node_refs.extend(
                [
                    NodeRef(paper_id=left_id, node_id=left_primary.id, label=left_primary.label),
                    NodeRef(paper_id=right_id, node_id=right_primary.id, label=right_primary.label),
                ]
            )

    if overlap_label is None or left_primary is None or right_primary is None:
        summary = f"两篇论文 {left_id} 与 {right_id} 的方法与数据集均无显著重合，无法生成方法重叠巡检报告。"
        return PatrolInsight(
            insight_id=METHOD_OVERLAP_INSIGHT_ID,
            title=METHOD_OVERLAP_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[],
        )

    left_dataset = _primary_node(left_datasets)
    right_dataset = _primary_node(right_datasets)

    context = await _build_method_overlap_context(
        graphs,
        paper_ids,
        vector_store=vector_store,
    )
    llm_output = await generate_method_overlap_summary(
        context,
        llm_client=llm_client,
    )

    summary: str
    paper_a_usage: str
    paper_b_usage: str
    evidence_summary: str | None = None

    if llm_output is not None and llm_output.comparison_details:
        summary = llm_output.summary.strip()
        detail = llm_output.comparison_details[0]
        paper_a_usage = detail.paper_a_usage.strip()
        paper_b_usage = detail.paper_b_usage.strip()
        evidence_summary = detail.evidence_summary.strip() or None
    else:
        summary = _fallback_method_overlap_summary(
            left_primary.label,
            right_primary.label,
            overlap_label=overlap_label,
            has_method_overlap=overlap_type in ("literal", "semantic"),
        )
        paper_a_usage = _extract_usage(left_primary)
        paper_b_usage = _extract_usage(right_primary)

    point = MethodOverlapPoint(
        mode="method_overlap",
        method=overlap_label,
        overlap_score=overlap_score,
        overlap_type=overlap_type,
        paper_a_usage=paper_a_usage,
        paper_b_usage=paper_b_usage,
        dataset_a=left_dataset.label if left_dataset else None,
        dataset_b=right_dataset.label if right_dataset else None,
        evidence_summary=evidence_summary,
    )

    return PatrolInsight(
        insight_id=METHOD_OVERLAP_INSIGHT_ID,
        title=METHOD_OVERLAP_TITLE,
        summary=summary,
        status=PatrolInsightStatus.READY,
        paper_ids=[left_id, right_id],
        node_refs=node_refs,
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


def _fallback_method_overlap_summary(
    left_method: str,
    right_method: str,
    *,
    overlap_label: str,
    has_method_overlap: bool,
) -> str:
    if has_method_overlap:
        return f"两篇论文均使用了「{overlap_label}」方法，建议进一步比对具体使用场景、超参数配置与数据集差异。"
    return (
        f"两篇论文分别采用「{left_method}」与「{right_method}」方法，"
        f"但在数据集「{overlap_label}」上存在重叠，建议结合实验段落进一步核验。"
    )
