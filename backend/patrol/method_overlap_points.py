"""MethodOverlapPoint construction and node_refs collection for method_overlap."""

from __future__ import annotations

from backend.patrol.overlap_anchor import _OverlapAnchor
from backend.patrol.similarity import normalize_label
from backend.schemas.graph import GraphNode
from backend.schemas.patrol import MethodOverlapPoint, NodeRef, OverlapType
from backend.schemas.patrol_llm import MethodComparativeDetail, MethodOverlapOutput


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


def dedupe_node_refs(refs: list[NodeRef]) -> list[NodeRef]:
    seen: set[tuple[str, str]] = set()
    unique: list[NodeRef] = []
    for ref in refs:
        key = (ref.paper_id, ref.node_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def node_refs_for_anchors(
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
    return dedupe_node_refs(refs)


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


def derive_method_overlap_summary(
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


def build_method_overlap_points(
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
                node_refs=node_refs_for_anchors([anchor], left_methods, right_methods, left_id, right_id),
                detail=detail,
            )
        )
    for anchor in dataset_anchors:
        detail = _match_llm_detail_dataset(anchor, details)
        points.append(
            _build_single_method_overlap_point(
                anchor,
                node_refs=node_refs_for_anchors([anchor], left_datasets, right_datasets, left_id, right_id),
                detail=detail,
            )
        )
    return points
