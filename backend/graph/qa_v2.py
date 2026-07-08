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


def format_retrieval_context(
    rc: RetrievalContext | None,
) -> tuple[str, str, str]:
    """Format retrieval context into three prompt-section strings.

    Returns ``(entities_desc, relations_desc, chunks_desc)``.  Each is an
    empty string when the context is ``None`` or the corresponding collection
    is empty.
    """
    if rc is None:
        return ("", "", "")

    entities_desc = ""
    if rc.entities:
        lines = [f"- [{e.entity_id}] {e.label} ({e.node_type})" for e in rc.entities]
        entities_desc = "\n".join(lines)

    relations_desc = ""
    if rc.relations:
        lines = [f"- [{r.relation_id}] {r.text[:200]}" for r in rc.relations]
        relations_desc = "\n".join(lines)

    chunks_desc = ""
    if rc.chunks:
        lines = []
        for c in rc.chunks:
            page_info = ""
            if c.page_start is not None:
                page_info = f" [page {c.page_start}]"
            lines.append(f"- [{c.chunk_id}]{page_info} {c.text[:300]}")
        chunks_desc = "\n".join(lines)

    return (entities_desc, relations_desc, chunks_desc)
