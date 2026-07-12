"""V2 QA helpers — citation dispatch and retrieval-context formatting.

Extracted from ``backend/graph/qa.py`` to keep that module under the 500-line
god-file budget (D-12 governance gate).

Uses lazy imports for ``QaEvent`` to avoid a circular import with ``qa.py``:
``qa.py`` imports from here → here lazily imports ``QaEvent`` → no conflict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.graph.qa import QaEvent
    from backend.rag.models import RetrievalContext


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
) -> QaEvent:
    """Build one ``citation`` SSE event from a matched [CITE:...] marker."""
    from backend.graph.qa import QaEvent  # lazy – avoids circular import

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
        text_preview = chunk_text_cache.get(cite_value, "")[:120]
        return QaEvent(
            "citation",
            {
                "type": "chunk",
                "paper_id": paper_id,
                "chunk_id": cite_value,
                "label": f"片段 {cite_value}",
                "text_preview": text_preview,
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


_CONTEXT_TRUNCATED_SUFFIX = "…（检索上下文已截断，请优先依据上文与图谱节点作答）"
_EMPTY_ENTITIES_PLACEHOLDER = "（暂无向量召回实体，请依据上方图谱节点作答）"
_EMPTY_RELATIONS_PLACEHOLDER = "（暂无向量召回关系）"
_EMPTY_CHUNKS_PLACEHOLDER = "（暂无原文片段 — 论文向量索引尚未就绪或无匹配结果，请依据图谱节点与关系作答）"


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
