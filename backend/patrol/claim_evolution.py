"""Claim evolution patrol logic (RAG Phase 3)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from backend.config import get_settings
from backend.llm.client import LlmClient
from backend.llm.embeddings import EmbeddingClient, get_embedding_client
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair
from backend.patrol.exclusion import (
    PHASE_CLAIM_RECALL,
    PHASE_NODE_PRECHECK,
    PHASE_RQ_ALIGNMENT,
    make_exclusion_logic,
)
from backend.patrol.llm_summary import generate_claim_evolution_summary
from backend.patrol.node_selection import select_primary_node
from backend.patrol.rag_service import PatrolRAGService, attach_degradation_fields
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.patrol import (
    ClaimEvolutionPoint,
    EvolutionType,
    NodeRef,
    PatrolDegradationProfile,
    PatrolExclusionReason,
    PatrolInsight,
    PatrolInsightStatus,
    PatrolMode,
)

if TYPE_CHECKING:
    from backend.llm.reranker import RerankerClient
    from backend.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

CLAIM_EVOLUTION_INSIGHT_ID = "ins-claim-evolution-001"
CLAIM_EVOLUTION_TITLE = "观点演进（Claim Evolution）"


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


def _dedupe_question_nodes(nodes: list[GraphNode]) -> list[GraphNode]:
    seen: set[str] = set()
    unique: list[GraphNode] = []
    for node in nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        unique.append(node)
    return unique


async def _retrieve_claim_backfill_chunks(
    paper_id: str,
    question: GraphNode,
    vector_store: VectorStore,
    top_k: int,
) -> list[str]:
    """Retrieve conclusion-related chunks from VectorStore when Claim nodes are missing."""
    query = question.label
    chunks = await vector_store.query_chunks(
        query,
        paper_id=paper_id,
        top_k=top_k,
    )
    return [chunk.text for chunk in chunks if chunk.text.strip()]


def _format_claim(label: str | None, chunks: list[str]) -> str | None:
    """Prefer graph node label; fall back to retrieved chunk texts."""
    if label:
        return label
    if chunks:
        return "\n".join(chunks)
    return None


async def build_claim_evolution_insight(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    vector_store: VectorStore | None = None,
    llm_client: LlmClient | None = None,
    embedding_client: EmbeddingClient | None = None,
    reranker_client: RerankerClient | None = None,
) -> PatrolInsight | None:
    """Compare research questions and claims across two papers.

    Pipeline:
    1. Require ResearchQuestion or Thesis on both sides.
    2. Two-stage RQ gate: bi-encoder coarse recall → cross-encoder rerank (when enabled).
    3. Backfill missing Claim nodes from VectorStore using the research question as query.
    4. Ask LLM for structured NLI-style output (evolution_type, problem_fit_score, summary).
    """
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
            exclusion_logic=make_exclusion_logic(
                PatrolExclusionReason.MISSING_REQUIRED_NODES,
                phase=PHASE_NODE_PRECHECK,
                description=summary,
                metrics={
                    "missing_node_types": ["ResearchQuestion", "Thesis"],
                    "affected_papers": missing,
                },
            ),
        )

    left_question_pool = _dedupe_question_nodes(left_questions + left_theses)
    right_question_pool = _dedupe_question_nodes(right_questions + right_theses)

    settings = get_settings()
    embed_client = embedding_client or get_embedding_client()

    aligned_pair = await align_research_question_pair(
        left_question_pool,
        right_question_pool,
        embedding_client=embed_client,
        settings=settings,
        reranker_client=reranker_client,
    )
    if aligned_pair is None:
        summary = f"两篇论文 {left_id} 与 {right_id} 的研究问题/论点相似度不足，无法生成观点演进巡检报告。"
        return PatrolInsight(
            insight_id=CLAIM_EVOLUTION_INSIGHT_ID,
            title=CLAIM_EVOLUTION_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[],
            exclusion_logic=make_exclusion_logic(
                PatrolExclusionReason.RQ_GATE_FAILED,
                phase=PHASE_RQ_ALIGNMENT,
                description=summary,
                metrics={
                    "coarse_threshold": settings.patrol_claim_rq_coarse_threshold,
                    "rerank_threshold": settings.patrol_claim_rq_rerank_threshold,
                    "reranker_enabled": settings.reranker_enabled,
                },
            ),
        )

    left_question, right_question = aligned_pair

    # Backfill missing claims from VectorStore when available.
    left_claim = select_primary_node(claim_nodes(left_graph), graph=left_graph)
    right_claim = select_primary_node(claim_nodes(right_graph), graph=right_graph)

    left_claim_chunks: list[str] = []
    right_claim_chunks: list[str] = []
    if left_claim is None and vector_store is not None:
        left_claim_chunks = await _retrieve_claim_backfill_chunks(
            left_id,
            left_question,
            vector_store,
            settings.patrol_claim_chunk_top_k,
        )
    if right_claim is None and vector_store is not None:
        right_claim_chunks = await _retrieve_claim_backfill_chunks(
            right_id,
            right_question,
            vector_store,
            settings.patrol_claim_chunk_top_k,
        )

    left_claim_text = _format_claim(left_claim.label if left_claim else None, left_claim_chunks)
    right_claim_text = _format_claim(right_claim.label if right_claim else None, right_claim_chunks)

    if left_claim_text is None and right_claim_text is None:
        summary = (
            f"两篇论文 {left_id} 与 {right_id} 均未检出明确结论（Claim/Finding），"
            "且向量索引中无可召回的相关段落，无法生成观点演进巡检报告。"
        )
        return PatrolInsight(
            insight_id=CLAIM_EVOLUTION_INSIGHT_ID,
            title=CLAIM_EVOLUTION_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=[left_id, right_id],
            node_refs=[
                NodeRef(paper_id=left_id, node_id=left_question.id, label=left_question.label),
                NodeRef(paper_id=right_id, node_id=right_question.id, label=right_question.label),
            ],
            exclusion_logic=make_exclusion_logic(
                PatrolExclusionReason.NO_RECALLABLE_CLAIMS,
                phase=PHASE_CLAIM_RECALL,
                description=summary,
                metrics={"claim_chunk_top_k": settings.patrol_claim_chunk_top_k},
            ),
        )

    context, degradation = await _build_claim_evolution_context(
        graphs,
        paper_ids,
        vector_store=vector_store,
        extra_claim_chunks={
            left_id: left_claim_chunks,
            right_id: right_claim_chunks,
        },
        anchor_nodes={
            left_id: left_question,
            right_id: right_question,
        },
    )

    llm_output = await generate_claim_evolution_summary(
        context,
        llm_client=llm_client,
    )

    if llm_output is not None:
        summary = llm_output.comparison_summary
        evidence_summary = llm_output.evidence_summary
        evolution_type = EvolutionType(llm_output.evolution_type)
        problem_fit_score = llm_output.problem_fit_score
    else:
        summary = _fallback_claim_evolution_summary(left_question.label, right_question.label)
        evidence_summary = _fallback_evidence_summary(left_claim_text, right_claim_text)
        evolution_type = None
        problem_fit_score = None

    point = ClaimEvolutionPoint(
        mode="claim_evolution",
        research_question=left_question.label,
        paper_a_claim=left_claim_text,
        paper_b_claim=right_claim_text,
        evolution_type=evolution_type,
        problem_fit_score=problem_fit_score,
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
        **attach_degradation_fields(degradation),
    )


def _render_claim_evolution_query(
    graph: UnifiedPaperGraph,
    template: str,
    anchor_node: GraphNode | None,
) -> str:
    """Render the VectorStore query from the aligned anchor node and graph labels.

    The aligned question/thesis label is injected as {anchor_labels} so recall
    focuses on the intersection problem rather than every question in the paper.
    """
    question_labels = " ".join(node.label for node in research_question_nodes(graph))
    thesis_labels = " ".join(node.label for node in thesis_nodes(graph))
    anchor_labels = anchor_node.label if anchor_node is not None else ""
    return template.format(
        anchor_labels=anchor_labels,
        question_labels=question_labels,
        thesis_labels=thesis_labels,
    )


async def _build_claim_evolution_context(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    vector_store: VectorStore | None = None,
    extra_claim_chunks: dict[str, list[str]] | None = None,
    anchor_nodes: dict[str, GraphNode] | None = None,
) -> tuple[str, PatrolDegradationProfile | None]:
    settings = get_settings()
    sections: list[str] = []
    extra_claim_chunks = extra_claim_chunks or {}
    anchor_nodes = anchor_nodes or {}
    paper_queries: dict[str, str] = {}
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
        backfill = extra_claim_chunks.get(paper_id, [])
        if backfill:
            section += "\n召回结论候选段落：\n" + "\n".join(f"- {text}" for text in backfill)
        sections.append(section)
        paper_queries[paper_id] = _render_claim_evolution_query(
            graph,
            settings.patrol_claim_evolution_query_template,
            anchor_nodes.get(paper_id),
        )

    rag_service = PatrolRAGService(vector_store)
    rag_sections, degradation = await rag_service.enrich_context(
        PatrolMode.CLAIM_EVOLUTION,
        paper_queries,
    )
    sections.extend(rag_sections)

    return "\n\n".join(sections), degradation


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
            "两者围绕相似问题给出了判断，建议结合证据链分析差异来源。"
        )
    if left_claim:
        return f"论文 A 的结论为「{left_claim}」，论文 B 未检出明确结论。"
    if right_claim:
        return f"论文 B 的结论为「{right_claim}」，论文 A 未检出明确结论。"
    return "两篇论文均未检出明确结论，建议结合原文进一步提取核心主张。"
