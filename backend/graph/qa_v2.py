"""V2 QA helpers — citation dispatch and retrieval-context formatting.

Extracted from ``backend/graph/qa.py`` to keep that module under the 500-line
god-file budget (D-12 governance gate).

Uses lazy imports for ``QaEvent`` to avoid a circular import with ``qa.py``:
``qa.py`` imports from here → here lazily imports ``QaEvent`` → no conflict.

``RetrievalContext`` is the single source of truth (SSOT) for hybrid QA prompts:
``RC.nodes/edges`` → template ``{nodes}/{edges}``; ``RC.entities/relations/chunks``
→ vector sections via ``format_retrieval_context()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.schemas.chunk_preview import ResolvedChunkPreview

if TYPE_CHECKING:
    from backend.graph.qa import QaEvent
    from backend.graph.query import GraphQuery
    from backend.rag.chunk_preview import ChunkPreviewContext
    from backend.rag.models import RetrievalContext
    from backend.schemas.graph import UnifiedPaperGraph


def build_chunk_text_cache(chunks: list | None) -> dict[str, str]:
    """Build a mapping from chunk_id → text for citation text_preview."""
    if not chunks:
        return {}
    cache: dict[str, str] = {}
    for c in chunks:
        cid = getattr(c, "chunk_id", None)
        text = getattr(c, "text", None)
        if cid and text:
            cache[cid] = text
    return cache


def dispatch_citation(
    prefix: str,
    cite_value: str,
    paper_id: str,
    node_label_cache: dict[str, str],
    edge_label_cache: dict[str, str],
    chunk_text_cache: dict[str, str],
    *,
    chunk_preview: ResolvedChunkPreview | None = None,
    chunk_text_preview: str | None = None,
) -> QaEvent:
    """Build one ``citation`` SSE event from a matched [CITE:...] marker."""
    from backend.graph.qa import QaEvent  # lazy – avoids circular import
    from backend.schemas.chunk_preview import ChunkPreviewState

    if prefix == "edge:":
        label = edge_label_cache.get(cite_value, cite_value)
        return QaEvent(
            "citation",
            {
                "type": "edge",
                "paper_id": paper_id,
                "edge_id": cite_value,
                "label": label,
            },
        )
    if prefix == "chunk:":
        from backend.rag.chunk_preview import preview_from_cache

        if chunk_preview is not None:
            resolved = chunk_preview
        elif chunk_text_preview is not None:
            resolved = ResolvedChunkPreview.ready(chunk_text_preview)
        else:
            cached = preview_from_cache(chunk_text_cache, cite_value)
            resolved = (
                ResolvedChunkPreview.ready(cached)
                if cached
                else ResolvedChunkPreview.degraded(ChunkPreviewState.HALLUCINATED_ID)
            )
        return QaEvent(
            "citation",
            {
                "type": "chunk",
                "paper_id": paper_id,
                "chunk_id": cite_value,
                "label": f"片段 {cite_value}",
                "text_preview": resolved.text_preview,
                "preview_state": resolved.preview_state.value,
            },
        )
    if prefix == "page:":
        try:
            page_num = int(cite_value)
        except (ValueError, TypeError):
            page_num = cite_value
        return QaEvent(
            "citation",
            {
                "type": "page",
                "paper_id": paper_id,
                "page": page_num,
                "label": f"第{cite_value}页",
            },
        )

    # Default: bare [CITE:node_id] (V1 backward-compatible).
    label = node_label_cache.get(cite_value, cite_value)
    return QaEvent(
        "citation",
        {
            "type": "node",
            "paper_id": paper_id,
            "node_id": cite_value,
            "label": label,
        },
    )


async def dispatch_citation_async(
    prefix: str,
    cite_value: str,
    paper_id: str,
    node_label_cache: dict[str, str],
    edge_label_cache: dict[str, str],
    chunk_text_cache: dict[str, str],
    *,
    preview_ctx: ChunkPreviewContext | None = None,
) -> QaEvent:
    """Async citation dispatch with L2 chunk preview resolution on cache miss (B10)."""
    if prefix == "chunk:":
        from backend.rag.chunk_preview import resolve_chunk_text_preview

        resolved = await resolve_chunk_text_preview(cite_value, chunk_text_cache, preview_ctx)
        return dispatch_citation(
            prefix,
            cite_value,
            paper_id,
            node_label_cache,
            edge_label_cache,
            chunk_text_cache,
            chunk_preview=resolved,
        )
    return dispatch_citation(
        prefix,
        cite_value,
        paper_id,
        node_label_cache,
        edge_label_cache,
        chunk_text_cache,
    )


_CONTEXT_TRUNCATED_SUFFIX = "…（检索上下文已截断，请优先依据上文与图谱节点作答）"
_EMPTY_ENTITIES_PLACEHOLDER = "（暂无向量召回实体，请依据上方图谱节点作答）"
_EMPTY_RELATIONS_PLACEHOLDER = "（暂无向量召回关系）"
_EMPTY_CHUNKS_PLACEHOLDER = "（暂无原文片段 — 论文向量索引尚未就绪或无匹配结果，请依据图谱节点与关系作答）"
_EMPTY_SUBGRAPH_NODES_PLACEHOLDER = "（图谱中暂无匹配节点）"
_EMPTY_SUBGRAPH_EDGES_PLACEHOLDER = "（无匹配关系）"


def retrieval_context_has_subgraph(rc: RetrievalContext | None) -> bool:
    """True when *rc* carries any A-scale topology (nodes and/or edges)."""
    if rc is None:
        return False
    return bool(rc.nodes or rc.edges)


def retrieval_context_has_complete_subgraph(rc: RetrievalContext | None) -> bool:
    """True when both ``nodes`` and ``edges`` are present — no partial fallback needed."""
    if rc is None:
        return False
    return bool(rc.nodes and rc.edges)


def subgraph_dict_from_retrieval_context(rc: RetrievalContext) -> dict[str, list]:
    """Copy ``RC.nodes/edges`` into the legacy subgraph dict consumed by prompt rendering."""
    return {"nodes": list(rc.nodes), "edges": list(rc.edges)}


def freeze_retrieval_context(rc: RetrievalContext) -> RetrievalContext:
    """Return a deep snapshot of *rc* for prompt assembly (async-stream safety).

    ``QaEngine.stream()`` calls this at entry so concurrent consumers (logging,
    metrics, SSE hooks) cannot mutate shared list/dict references mid-flight.
    """
    return rc.model_copy(deep=True)


def resolve_prompt_subgraph(
    graph: UnifiedPaperGraph,
    question: str,
    retrieval_context: RetrievalContext | None,
    *,
    graph_query: GraphQuery,
) -> dict[str, list]:
    """Resolve A-scale subgraph for QA prompt rendering (SSOT with V1 fallback).

    V2 hybrid path: when ``retrieval_context`` already contains **both** nodes and edges
    (typically from ``HybridRetriever.retrieve()``), reuse them and skip a second
    ``GraphQuery`` round-trip.

    Partial degradation: when only one side is present (e.g. nodes populated but
    ``edges`` is ``[]`` after a flaky retrieval), reuse the available RC slice and
    backfill the missing half via a single ``GraphQuery`` call.

    V1 / legacy path: when RC is ``None`` or both subgraph lists are empty, fall
    back to ``graph_query.subgraph_for_question()`` for backward compatibility.
    """
    if retrieval_context is None or not retrieval_context_has_subgraph(retrieval_context):
        return graph_query.subgraph_for_question(graph, question)

    if retrieval_context_has_complete_subgraph(retrieval_context):
        return subgraph_dict_from_retrieval_context(retrieval_context)

    fallback = graph_query.subgraph_for_question(graph, question)

    if retrieval_context.nodes and not retrieval_context.edges:
        return {
            "nodes": list(retrieval_context.nodes),
            "edges": list(fallback.get("edges", [])),
        }

    if retrieval_context.edges and not retrieval_context.nodes:
        return {
            "nodes": list(fallback.get("nodes", [])),
            "edges": list(retrieval_context.edges),
        }

    return fallback


def format_subgraph_sections(subgraph: dict) -> tuple[str, str]:
    """Format subgraph dict into ``{nodes}`` / ``{edges}`` prompt placeholder strings."""
    nodes_desc = "\n".join(f"- [{n['id']}] {n['label']} (类型: {n['type']})" for n in subgraph.get("nodes", []))
    edges_desc = "\n".join(f"- {e['source']} --[{e['label']}]--> {e['target']}" for e in subgraph.get("edges", []))
    if not nodes_desc:
        nodes_desc = _EMPTY_SUBGRAPH_NODES_PLACEHOLDER
    if not edges_desc:
        edges_desc = _EMPTY_SUBGRAPH_EDGES_PLACEHOLDER
    return nodes_desc, edges_desc


def extract_prompt_section(prompt: str, heading: str) -> str:
    """Slice one ``### {heading}`` block from a rendered QA prompt."""
    marker = f"### {heading}"
    start = prompt.find(marker)
    if start < 0:
        return ""
    rest = prompt[start + len(marker) :]
    end = rest.find("\n### ")
    if end < 0:
        end = rest.find("\n## ")
    return rest[:end] if end >= 0 else rest


def normalize_subgraph_prompt_section(section: str) -> str:
    """Collapse whitespace and sort lines for order-independent shadow diffing."""
    collapsed_lines = ["".join(line.split()) for line in section.splitlines() if line.strip()]
    collapsed_lines.sort()
    return "".join(collapsed_lines)


def subgraph_sections_shadow_fingerprint(prompt: str) -> tuple[str, str]:
    """Return normalized ``(nodes, edges)`` fingerprints for V1/V2 shadow comparison."""
    nodes = normalize_subgraph_prompt_section(extract_prompt_section(prompt, "节点"))
    edges = normalize_subgraph_prompt_section(extract_prompt_section(prompt, "关系"))
    return nodes, edges


def _context_sections_total_len(entities_desc: str, relations_desc: str, chunks_desc: str) -> int:
    return len(entities_desc) + len(relations_desc) + len(chunks_desc)


def _trim_section_tail(section: str, *, excess: int) -> str:
    if excess <= 0 or not section:
        return section
    lines = section.split("\n")
    if len(lines) > 1:
        return "\n".join(lines[:-1])
    return section[: max(0, len(section) - excess)]


def _apply_context_char_budget(
    entities_desc: str,
    relations_desc: str,
    chunks_desc: str,
    max_total_chars: int,
) -> tuple[str, str, str]:
    """Trim retrieval prompt sections when their combined length exceeds the budget."""
    if _context_sections_total_len(entities_desc, relations_desc, chunks_desc) <= max_total_chars:
        return entities_desc, relations_desc, chunks_desc

    marker = _CONTEXT_TRUNCATED_SUFFIX
    budget = max(max_total_chars - len(marker), 0)

    while _context_sections_total_len(entities_desc, relations_desc, chunks_desc) > budget:
        excess = _context_sections_total_len(entities_desc, relations_desc, chunks_desc) - budget
        if chunks_desc:
            chunks_desc = _trim_section_tail(chunks_desc, excess=excess)
            continue
        if relations_desc:
            relations_desc = _trim_section_tail(relations_desc, excess=excess)
            continue
        if entities_desc:
            entities_desc = _trim_section_tail(entities_desc, excess=excess)
            continue
        break

    if chunks_desc:
        chunks_desc = chunks_desc.rstrip() + marker
    elif relations_desc:
        relations_desc = relations_desc.rstrip() + marker
    elif entities_desc:
        entities_desc = entities_desc.rstrip() + marker

    while _context_sections_total_len(entities_desc, relations_desc, chunks_desc) > max_total_chars:
        excess = _context_sections_total_len(entities_desc, relations_desc, chunks_desc) - max_total_chars
        if chunks_desc:
            chunks_desc = chunks_desc[: max(0, len(chunks_desc) - excess)]
            continue
        if relations_desc:
            relations_desc = relations_desc[: max(0, len(relations_desc) - excess)]
            continue
        if entities_desc:
            entities_desc = entities_desc[: max(0, len(entities_desc) - excess)]
            continue
        break

    return entities_desc, relations_desc, chunks_desc


def format_retrieval_context(
    rc: RetrievalContext | None,
    *,
    max_total_chars: int | None = None,
) -> tuple[str, str, str]:
    """Format retrieval context into three prompt-section strings.

    Returns ``(entities_desc, relations_desc, chunks_desc)``.  When *rc* is
    ``None`` (V1 graph-only mode), all three are empty strings.  When *rc* is
    provided but collections are empty — e.g. vector index not ready — human-
    readable placeholders guide the LLM to rely on graph nodes.

    When *max_total_chars* is set, sections are trimmed in priority order:
    chunks first, then relations, then entities.
    """
    if rc is None:
        return ("", "", "")

    entities_desc = ""
    if rc.entities:
        lines = [f"- [{e.entity_id}] {e.label} ({e.node_type})" for e in rc.entities]
        entities_desc = "\n".join(lines)
    else:
        entities_desc = _EMPTY_ENTITIES_PLACEHOLDER

    relations_desc = ""
    if rc.relations:
        lines = [f"- [{r.relation_id}] {r.text[:200]}" for r in rc.relations]
        relations_desc = "\n".join(lines)
    else:
        relations_desc = _EMPTY_RELATIONS_PLACEHOLDER

    chunks_desc = ""
    if rc.chunks:
        lines = []
        for c in rc.chunks:
            page_info = ""
            if c.page_start is not None:
                page_info = f" [page {c.page_start}]"
            lines.append(f"- [{c.chunk_id}]{page_info} {c.text[:300]}")
        chunks_desc = "\n".join(lines)
    else:
        chunks_desc = _EMPTY_CHUNKS_PLACEHOLDER

    if max_total_chars is not None:
        entities_desc, relations_desc, chunks_desc = _apply_context_char_budget(
            entities_desc,
            relations_desc,
            chunks_desc,
            max_total_chars,
        )

    return (entities_desc, relations_desc, chunks_desc)
