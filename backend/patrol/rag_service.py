"""Unified RAG enrichment facade for all patrol modes.

This module centralises VectorStore interactions so individual analysers do not
repeat `query_chunks` boilerplate.  It also records degradation metadata when the
index is missing for any paper.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from backend.config import get_settings
from backend.schemas.patrol import PatrolMode

if TYPE_CHECKING:
    from backend.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

RAG_DEGRADED_META_KEY = "patrol_rag_context_degraded"

_DEGRADATION_REASON_LABELS: dict[str, str] = {
    "index_not_ready": "向量索引尚未就绪，检索上下文可能不完整",
    "vector_store_unavailable": "向量库不可用，结果仅基于图谱结构",
    "query_failed": "向量检索部分失败，结果可能不完整",
}


def append_rag_degradation_notice(summary: str, meta: dict[str, Any]) -> str:
    """Append a human-readable RAG degradation hint to an insight summary."""
    payload = meta.get(RAG_DEGRADED_META_KEY)
    if not payload:
        return summary

    reason = str(payload.get("reason", "unknown"))
    paper_ids = payload.get("paper_ids") or []
    label = _DEGRADATION_REASON_LABELS.get(reason, f"RAG 上下文降级（{reason}）")
    if paper_ids:
        suffix = f"（提示：{label}；受影响论文：{', '.join(paper_ids)}）"
    else:
        suffix = f"（提示：{label}）"

    if suffix in summary:
        return summary
    return f"{summary.rstrip()} {suffix}"


class PatrolRAGService:
    """High-level facade for cross-paper RAG context enrichment.

    The service is stateless: it borrows a ``VectorStore`` instance per call and
    renders mode-specific queries from graph node labels supplied by the caller.
    """

    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self._vector_store = vector_store

    async def enrich_context(
        self,
        mode: PatrolMode,
        paper_queries: dict[str, str],
        *,
        top_k: int | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        """Return per-paper RAG context sections plus degradation metadata.

        Args:
            mode: Patrol mode used to resolve default top_k when not supplied.
            paper_queries: Mapping from paper_id to the VectorStore query text.
            top_k: Override the default recall count for this mode.

        Returns:
            A tuple of (context_sections, meta).  ``meta`` is empty when the
            index is ready for every paper; otherwise it contains
            ``patrol_rag_context_degraded``.
        """
        settings = get_settings()
        resolved_top_k = top_k if top_k is not None else self._default_top_k(mode, settings)

        meta = await self._check_index_ready(list(paper_queries.keys()))
        if self._vector_store is None or resolved_top_k <= 0:
            return [], meta

        sections: list[str] = []
        for paper_id, query in paper_queries.items():
            try:
                chunks = await self._vector_store.query_chunks(
                    query,
                    paper_id=paper_id,
                    top_k=resolved_top_k,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("patrol_rag_query_failed", extra={"paper_id": paper_id, "error": str(exc)})
                if RAG_DEGRADED_META_KEY not in meta:
                    meta[RAG_DEGRADED_META_KEY] = {"paper_ids": [], "reason": "query_failed"}
                meta[RAG_DEGRADED_META_KEY]["paper_ids"].append(paper_id)
                continue
            if chunks:
                sections.append(f"paper_id={paper_id} 相关段落：\n" + "\n".join(f"- {chunk.text}" for chunk in chunks))
        return sections, meta

    async def _check_index_ready(self, paper_ids: list[str]) -> dict[str, Any]:
        """Return degradation metadata when VectorStore index is missing."""
        if self._vector_store is None:
            return {
                RAG_DEGRADED_META_KEY: {
                    "paper_ids": paper_ids,
                    "reason": "vector_store_unavailable",
                },
            }

        degraded: list[str] = []
        for paper_id in paper_ids:
            try:
                if not await self._vector_store.exists(paper_id):
                    degraded.append(paper_id)
            except Exception:  # noqa: BLE001
                degraded.append(paper_id)

        if degraded:
            logger.warning("patrol_rag_context_degraded", extra={"paper_ids": degraded, "reason": "index_not_ready"})
            return {
                RAG_DEGRADED_META_KEY: {
                    "paper_ids": degraded,
                    "reason": "index_not_ready",
                },
            }
        return {}

    @staticmethod
    def _default_top_k(mode: PatrolMode, settings: Any) -> int:
        if mode == PatrolMode.METHOD_OVERLAP:
            return settings.patrol_method_overlap_top_k
        if mode == PatrolMode.CLAIM_EVOLUTION:
            return settings.patrol_claim_evolution_top_k
        # Legacy modes share the claim_evolution default until dedicated knobs are added.
        return settings.patrol_claim_evolution_top_k
