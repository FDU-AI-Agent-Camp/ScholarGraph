"""Contradiction patrol logic (BE-4)."""

from collections.abc import Mapping

from backend.llm.client import LlmClient
from backend.patrol.llm_summary import generate_patrol_summary
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.patrol import NodeRef, PatrolInsight, PatrolInsightStatus, PatrolMode

THESIS_NODE_TYPE = "Thesis"
SUB_ARGUMENT_NODE_TYPE = "SubArgument"
CONTRADICTION_INSIGHT_ID = "ins-contradiction-001"
CONTRADICTION_TITLE = "核心论点张力（Contradiction）"


def thesis_nodes(graph: UnifiedPaperGraph) -> list[GraphNode]:
    return [node for node in graph.nodes if node.type == THESIS_NODE_TYPE]


def sub_argument_nodes(graph: UnifiedPaperGraph) -> list[GraphNode]:
    return [node for node in graph.nodes if node.type == SUB_ARGUMENT_NODE_TYPE]


async def build_contradiction_insight(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
    *,
    llm_client: LlmClient | None = None,
) -> PatrolInsight | None:
    """Compare thesis/sub-argument nodes across two papers and build one insight.

    If either paper lacks SubArgument nodes, the LLM chain is skipped and a
    templated "insufficient data" insight is returned instead. This keeps the
    response fast and avoids paying for a generator to explain why it cannot
    produce a meaningful contradiction report.
    """
    if len(paper_ids) != 2:
        return None

    left_id, right_id = paper_ids
    left_graph = graphs.get(left_id)
    right_graph = graphs.get(right_id)
    left_thesis = _primary_thesis(left_graph)
    right_thesis = _primary_thesis(right_graph)

    missing_paper_ids: list[str] = []
    if left_thesis is None:
        missing_paper_ids.append(left_id)
    if right_thesis is None:
        missing_paper_ids.append(right_id)
    if missing_paper_ids:
        summary = (
            f"由于对比文献 {'、'.join(missing_paper_ids)} 中缺乏核心论点（Thesis）数据，"
            "无法生成矛盾巡检报告。建议补充文献内容或重新解析。"
        )
        return PatrolInsight(
            insight_id=CONTRADICTION_INSIGHT_ID,
            title=CONTRADICTION_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            has_contradiction=False,
            paper_ids=[left_id, right_id],
            node_refs=[],
        )

    # Gatekeeper: both papers must provide SubArgument nodes for a meaningful
    # contradiction analysis. Without them, return a deterministic business
    # conclusion instead of calling the LLM.
    left_subs = sub_argument_nodes(left_graph)
    right_subs = sub_argument_nodes(right_graph)
    missing_subargument_paper_ids: list[str] = []
    if not left_subs:
        missing_subargument_paper_ids.append(left_id)
    if not right_subs:
        missing_subargument_paper_ids.append(right_id)
    if missing_subargument_paper_ids:
        summary = (
            f"由于对比文献 {'、'.join(missing_subargument_paper_ids)} 中缺乏显式子论点（SubArgument）数据，"
            "无法生成矛盾巡检报告。建议补充文献内容或重新解析。"
        )
        return PatrolInsight(
            insight_id=CONTRADICTION_INSIGHT_ID,
            title=CONTRADICTION_TITLE,
            summary=summary,
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            has_contradiction=False,
            paper_ids=[left_id, right_id],
            node_refs=[
                NodeRef(paper_id=left_id, node_id=left_thesis.id, label=left_thesis.label),
                NodeRef(paper_id=right_id, node_id=right_thesis.id, label=right_thesis.label),
            ],
        )

    context = _build_contradiction_context(graphs, paper_ids)
    llm_summary = await generate_patrol_summary(
        PatrolMode.CONTRADICTION,
        context,
        llm_client=llm_client,
    )
    summary = llm_summary or _fallback_contradiction_summary(left_thesis.label, right_thesis.label)

    return PatrolInsight(
        insight_id=CONTRADICTION_INSIGHT_ID,
        title=CONTRADICTION_TITLE,
        summary=summary,
        status=PatrolInsightStatus.READY,
        paper_ids=[left_id, right_id],
        node_refs=[
            NodeRef(paper_id=left_id, node_id=left_thesis.id, label=left_thesis.label),
            NodeRef(paper_id=right_id, node_id=right_thesis.id, label=right_thesis.label),
        ],
    )


def _primary_thesis(graph: UnifiedPaperGraph | None) -> GraphNode | None:
    if graph is None:
        return None
    theses = thesis_nodes(graph)
    if not theses:
        return None
    return theses[0]


def _build_contradiction_context(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
) -> str:
    sections: list[str] = []
    for paper_id in paper_ids:
        graph = graphs.get(paper_id)
        if graph is None:
            continue
        thesis_labels = [node.label for node in thesis_nodes(graph)]
        sub_labels = [node.label for node in sub_argument_nodes(graph)]
        sections.append(
            f"paper_id={paper_id}\n"
            f"Thesis: {', '.join(thesis_labels) or '（无）'}\n"
            f"SubArgument: {', '.join(sub_labels) or '（无）'}",
        )
    return "\n\n".join(sections)


def _fallback_contradiction_summary(left_label: str, right_label: str) -> str:
    if left_label == right_label:
        return (
            f"两篇论文的核心论点均为「{left_label}」，"
            "当前图谱中未检出显著论证矛盾，建议结合分论点与支持证据进一步比对。"
        )
    return (
        f"两篇论文的核心论点分别为「{left_label}」与「{right_label}」，"
        "存在潜在论证张力，建议对照分论点关系与证据链进一步核验。"
    )
