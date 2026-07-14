"""Unified RAG enrichment facade for all patrol modes.

This module centralises VectorStore interactions so individual analysers do not
repeat ``query_chunks`` boilerplate.  It probes ``exists`` before heavy recall
and bubbles a typed ``PatrolDegradationProfile`` when context must be thinned.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from backend.config import get_settings
from backend.patrol.circuit_breaker import VectorStoreCircuitBreaker
from backend.patrol.degradation import (
    RAG_DEGRADED_META_KEY,
    is_vector_store_connectivity_error,
    is_vector_store_probe_outage,
    legacy_meta_from_profile,
    make_degradation_profile,
    merge_degradation_profiles,
)
from backend.schemas.patrol import PatrolDegradationProfile, PatrolDegradationReason, PatrolMode

if TYPE_CHECKING:
    from backend.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

_DEGRADATION_REASON_LABELS: dict[str, str] = {
    "index_not_ready": "向量索引尚未就绪，检索上下文可能不完整",
    "INDEX_NOT_READY": "向量索引尚未就绪，检索上下文可能不完整",
    "vector_store_unavailable": "向量库不可用，结果仅基于图谱结构",
    "VECTOR_STORE_UNAVAILABLE": "向量库不可用，结果仅基于图谱结构",
    "query_failed": "向量检索部分失败，结果可能不完整",
    "QUERY_FAILED": "向量检索部分失败，结果可能不完整",
}


def append_rag_degradation_notice(summary: str, meta: dict[str, Any]) -> str:
    """Append a human-readable RAG degradation hint to an insight summary.

    Deprecated for new UI paths: prefer ``is_degraded`` + ``degradation_profile``.
    Kept for backward-compatible tooling and older tests.
    """
    payload = meta.get(RAG_DEGRADED_META_KEY)
    if not payload:
        return summary

    reason = str(payload.get("reason_code") or payload.get("reason", "unknown"))
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

    The service is stateless aside from an optional circuit breaker that fail-fasts
    after VectorStore connectivity collapses.
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        *,
        circuit_breaker: VectorStoreCircuitBreaker | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._circuit = circuit_breaker or VectorStoreCircuitBreaker()

    @property
    def circuit_breaker(self) -> VectorStoreCircuitBreaker:
        return self._circuit

    async def enrich_context(
        self,
        mode: PatrolMode,
        paper_queries: dict[str, str],
        *,
        top_k: int | None = None,
    ) -> tuple[list[str], PatrolDegradationProfile | None]:
        """Return per-paper RAG context sections plus an optional degradation profile.

        Flow:
            1. Circuit OPEN → immediate ``VECTOR_STORE_UNAVAILABLE`` (no I/O).
            2. Fast ``exists`` probe per paper (skip heavy recall when index missing).
            3. Map connection refused to ``VECTOR_STORE_UNAVAILABLE``; trip breaker.
            4. Query only index-ready papers; map query ``TimeoutError`` to ``QUERY_FAILED``.
        """
        settings = get_settings()
        resolved_top_k = top_k if top_k is not None else self._default_top_k(mode, settings)
        paper_ids = list(paper_queries.keys())

        if self._vector_store is None:
            return [], make_degradation_profile(
                PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE,
                paper_ids,
            )

        if not self._circuit.allow_request():
            logger.warning(
                "patrol_rag_circuit_open",
                extra={"paper_ids": paper_ids, "state": self._circuit.state.value},
            )
            return [], make_degradation_profile(
                PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE,
                paper_ids,
            )

        degradation, ready_ids = await self._probe_index_readiness(paper_ids)
        if (
            degradation is not None
            and degradation.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
        ):
            self._circuit.record_failure()
            return [], degradation

        if resolved_top_k <= 0 or not ready_ids:
            if degradation is None:
                self._circuit.record_success()
            return [], degradation

        sections: list[str] = []
        for paper_id in ready_ids:
            query = paper_queries[paper_id]
            try:
                chunks = await self._vector_store.query_chunks(
                    query,
                    paper_id=paper_id,
                    top_k=resolved_top_k,
                )
            except Exception as exc:  # noqa: BLE001 — bubble typed degradation, keep funnel alive
                logger.warning("patrol_rag_query_failed", extra={"paper_id": paper_id, "error": str(exc)})
                if is_vector_store_connectivity_error(exc):
                    self._circuit.record_failure()
                    reason = PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
                else:
                    # TimeoutError and generic query errors → QUERY_FAILED
                    reason = PatrolDegradationReason.QUERY_FAILED
                degradation = merge_degradation_profiles(
                    degradation,
                    make_degradation_profile(reason, [paper_id]),
                )
                continue
            if chunks:
                sections.append(f"paper_id={paper_id} 相关段落：\n" + "\n".join(f"- {chunk.text}" for chunk in chunks))

        if degradation is None or degradation.reason_code != PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE:
            self._circuit.record_success()
        return sections, degradation

    async def _probe_index_readiness(
        self,
        paper_ids: list[str],
    ) -> tuple[PatrolDegradationProfile | None, list[str]]:
        """Fast exists check; skip heavy recall for missing indexes."""
        assert self._vector_store is not None

        missing: list[str] = []
        ready: list[str] = []
        store_unavailable = False

        for paper_id in paper_ids:
            try:
                if await self._vector_store.exists(paper_id):
                    ready.append(paper_id)
                else:
                    missing.append(paper_id)
            except Exception as exc:  # noqa: BLE001 — classify connectivity vs probe failure
                logger.warning(
                    "patrol_rag_exists_probe_failed",
                    extra={"paper_id": paper_id, "error": str(exc)},
                )
                if is_vector_store_probe_outage(exc):
                    store_unavailable = True
                    missing.append(paper_id)
                else:
                    missing.append(paper_id)

        if store_unavailable:
            profile = make_degradation_profile(
                PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE,
                missing or paper_ids,
            )
            logger.warning(
                "patrol_rag_context_degraded",
                extra={"paper_ids": profile.affected_papers, "reason": profile.reason_code.value},
            )
            return profile, []

        if missing:
            profile = make_degradation_profile(PatrolDegradationReason.INDEX_NOT_READY, missing)
            logger.warning(
                "patrol_rag_context_degraded",
                extra={"paper_ids": profile.affected_papers, "reason": profile.reason_code.value},
            )
            return profile, ready

        return None, ready

    @staticmethod
    def _default_top_k(mode: PatrolMode, settings: Any) -> int:
        if mode == PatrolMode.METHOD_OVERLAP:
            return settings.patrol_method_overlap_top_k
        if mode == PatrolMode.CLAIM_EVOLUTION:
            return settings.patrol_claim_evolution_top_k
        # Legacy modes share the claim_evolution default until dedicated knobs are added.
        return settings.patrol_claim_evolution_top_k


def attach_degradation_fields(
    degradation: PatrolDegradationProfile | None,
) -> dict[str, Any]:
    """Kwargs to spread onto ``PatrolInsight`` for first-class + legacy meta."""
    return {
        "is_degraded": degradation is not None,
        "degradation_profile": degradation,
        "meta": legacy_meta_from_profile(degradation),
    }
