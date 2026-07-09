"""Claim evolution patrol logic (RAG Phase 3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from backend.llm.client import LlmClient
from backend.patrol.llm_summary import generate_patrol_summary
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.patrol import (
    ClaimEvolutionPoint,
    NodeRef,
    PatrolInsight,
    PatrolInsightStatus,
    PatrolMode,
)

if TYPE_CHECKING:
    from backend.rag.vector_store import VectorStore

CLAIM_EVOLUTION_INSIGHT_ID = "ins-claim-evolution-001"
CLAIM_EVOLUTION_TITLE = "观点演进（Claim Evolution）"
CLAIM_EVOLUTION_QUERY_TEXT = "research question thesis conclusion claim finding"
CLAIM_TOP_K = 3
# MVP threshold for question similarity using character-set Jaccard.
# Works across Chinese (character-level) and English (letter-level).
QUESTION_SIMILARITY_THRESHOLD = 0.3


def research_question_nodes(graph: UnifiedPaperGraph | None) -> list[GraphNode]:
    if graph is None:
        return []
    return [node for node in graph.nodes if node.type == NodeType.RESEARCH_QUESTION]


def thesis_nodes(graph: UnifiedPaperGraph | None) -> list[GraphNode]:
    if graph is None:
        return []
    return [node for node in graph.nodes if node.type == NodeType.THESIS]


def claim_nodes(graph: UnifiedPaperGraph | None) -> list[GraphNode]:
    if graph is None:
        return []
    return [node for node in graph.nodes if node.type in (NodeType.CLAIM, NodeType.FINDING)]


def _primary_node(nodes: list[GraphNode]) -> GraphNode | None:
    return nodes[0] if nodes else None


def _normalize(label: str) -> str:
    """Normalize a node label for similarity comparison."""
    return label.strip().lower()


def _char_jaccard(left: str, right: str) -> float:
    """Return character-set Jaccard similarity between two labels."""
    left_chars = set(_normalize(left))
    right_chars = set(_normalize(right))
    if not left_chars or not right_chars:
        return 0.0
    intersection = left_chars & right_chars
    union = left_chars | right_chars
    return len(intersection) / len(union)


def _questions_are_similar(left: str, right: str, threshold: float = QUESTION_SIMILARITY_THRESHOLD) -> bool:
    """Check whether two research questions/theses are similar enough to compare."""
    if _normalize(left) == _normalize(right):
        return True
    return _char_jaccard(left, right) >= threshold


def _claims_are_different(left: GraphNode | None, right: GraphNode | None) -> bool:
    """Return True when both claims exist and are not normalized-equal."""
    if left is None or right is None:
        return False
    return _normalize(left.label) != _normalize(right.label)


async def build_claim_evolution_insight(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    vector_store: VectorStore | None = None,
    llm_client: LlmClient | None = None,
) -> PatrolInsight | None:
    """Compare research questions and claims across two papers."""
    if len(paper_ids) != 2:
        return None

    left_id, right_id = paper_ids
    left_graph = graphs.get(left_id)
    right_graph = graphs.get(right_id)

    left_questions = research_question_nodes(left_graph)
    right_questions = research_question_nodes(right_graph)
    left_theses = thesis_nodes(left_graph)
    right_theses = thesis_nodes(right_graph)

    missing: list[str] = []
    if not left_questions and not left_theses:
        missing.append(left_id)
    if not right_questions and not right_theses:
        missing.append(right_id)
    if missing:
        summary = (
            f"由于对比文献 {'、'.join(missing)} 中缺乏研究问题（ResearchQuestion）或论点（Thesis）数据，"
            "无法生成观点演进巡检报告。建议补充文献内容或重新解析。"
        )
        return PatrolInsight(
            insight_id=CLAIM_EVOLUTION_INSIGHT_ID,
            title=CLAIM_EVOLUTION_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[],
        )

    left_question = _primary_node(left_questions) or _primary_node(left_theses)
    right_question = _primary_node(right_questions) or _primary_node(right_theses)
    assert left_question is not None and right_question is not None

    left_claims = claim_nodes(left_graph)
    right_claims = claim_nodes(right_graph)
    left_claim = _primary_node(left_claims)
    right_claim = _primary_node(right_claims)

    if not _questions_are_similar(left_question.label, right_question.label):
        summary = (
            f"两篇论文 {left_id} 与 {right_id} 的研究问题/论点相似度不足，"
            "无法生成观点演进巡检报告。"
        )
        return PatrolInsight(
            insight_id=CLAIM_EVOLUTION_INSIGHT_ID,
            title=CLAIM_EVOLUTION_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[],
        )

    if left_claim is not None and right_claim is not None:
        if not _claims_are_different(left_claim, right_claim):
            summary = (
                f"两篇论文 {left_id} 与 {right_id} 的研究问题相似，但结论相同，"
                "不存在观点演进差异。"
            )
            return PatrolInsight(
                insight_id=CLAIM_EVOLUTION_INSIGHT_ID,
                title=CLAIM_EVOLUTION_TITLE,
                summary=summary,
                status=PatrolInsightStatus.INSUFFICIENT_DATA,
                paper_ids=[left_id, right_id],
                node_refs=[],
            )

    context = await _build_claim_evolution_context(
        graphs,
        paper_ids,
        vector_store=vector_store,
    )
    llm_summary = await generate_patrol_summary(
        PatrolMode.CLAIM_EVOLUTION,
        context,
        llm_client=llm_client,
    )
    summary = llm_summary or _fallback_claim_evolution_summary(
        left_question.label,
        right_question.label,
    )
    evidence_summary = llm_summary or _fallback_evidence_summary(
        left_claim.label if left_claim else None,
        right_claim.label if right_claim else None,
    )

    point = ClaimEvolutionPoint(
        mode="claim_evolution",
        research_question=left_question.label,
        paper_a_claim=left_claim.label if left_claim else "未检出明确结论",
        paper_b_claim=right_claim.label if right_claim else "未检出明确结论",
        evidence_summary=evidence_summary,
    )

    return PatrolInsight(
        insight_id=CLAIM_EVOLUTION_INSIGHT_ID,
        title=CLAIM_EVOLUTION_TITLE,
        summary=summary,
        status=PatrolInsightStatus.READY,
        paper_ids=[left_id, right_id],
        node_refs=[
            NodeRef(paper_id=left_id, node_id=left_question.id, label=left_question.label),
            NodeRef(paper_id=right_id, node_id=right_question.id, label=right_question.label),
        ],
        structured_points=[point],
    )


async def _build_claim_evolution_context(
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
        question_labels = [node.label for node in research_question_nodes(graph)]
        thesis_labels = [node.label for node in thesis_nodes(graph)]
        claim_labels = [node.label for node in claim_nodes(graph)]
        section = (
            f"paper_id={paper_id}\n"
            f"ResearchQuestion: {', '.join(question_labels) or '（无）'}\n"
            f"Thesis: {', '.join(thesis_labels) or '（无）'}\n"
            f"Claim/Finding: {', '.join(claim_labels) or '（无）'}"
        )
        sections.append(section)

    if vector_store is not None:
        for paper_id in paper_ids:
            chunks = await vector_store.query_chunks(
                CLAIM_EVOLUTION_QUERY_TEXT,
                paper_id=paper_id,
                top_k=CLAIM_TOP_K,
            )
            if chunks:
                sections.append(f"paper_id={paper_id} 相关段落：\n" + "\n".join(f"- {chunk.text}" for chunk in chunks))

    return "\n\n".join(sections)


def _fallback_claim_evolution_summary(left_question: str, right_question: str) -> str:
    if left_question == right_question:
        return f"两篇论文围绕同一问题「{left_question}」展开，建议进一步比对其结论、证据与实验设计差异。"
    return (
        f"两篇论文分别关注「{left_question}」与「{right_question}」，"
        "研究问题存在相似性，建议对照结论与证据链进一步研判。"
    )


def _fallback_evidence_summary(left_claim: str | None, right_claim: str | None) -> str:
    """Return a claim-focused fallback when the LLM does not provide a structured evidence summary."""
    if left_claim and right_claim:
        return (
            f"论文 A 的结论为「{left_claim}」，论文 B 的结论为「{right_claim}」，"
            "两者围绕相似问题给出了不同判断，建议结合证据链分析差异来源。"
        )
    if left_claim:
        return f"论文 A 的结论为「{left_claim}」，论文 B 未检出明确结论。"
    if right_claim:
        return f"论文 B 的结论为「{right_claim}」，论文 A 未检出明确结论。"
    return "两篇论文均未检出明确结论，建议结合原文进一步提取核心主张。"
