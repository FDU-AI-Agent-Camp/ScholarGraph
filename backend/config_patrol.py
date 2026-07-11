"""Patrol-mode configuration fields and helpers for :class:`backend.config.Settings`."""

from __future__ import annotations

from pydantic import Field


class PatrolSettingsMixin:
    """Pydantic fields and methods for ScholarGraph Patrol modes."""

    enable_patrol_semantic_path: bool = Field(
        default=True,
        validation_alias="ENABLE_PATROL_SEMANTIC_PATH",
        description="When false, method_overlap only uses literal label matching.",
    )
    patrol_semantic_threshold: float = Field(
        default=0.88,
        ge=0.0,
        le=1.0,
        validation_alias="PATROL_SEMANTIC_THRESHOLD",
        description="Cosine-similarity threshold for soft method-overlap matrix pre-screening.",
    )
    patrol_max_matrix_size: int = Field(
        default=500,
        ge=1,
        le=2000,
        validation_alias="PATROL_MAX_MATRIX_SIZE",
        description="Max M*N method-node pairs allowed for in-memory semantic similarity matrix.",
    )
    patrol_topology_rq_semantic_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        validation_alias="PATROL_TOPOLOGY_RQ_SEMANTIC_THRESHOLD",
        description="Cosine gate for RQ semantic resonance in method_overlap topology filter (Chinese default).",
    )
    patrol_topology_rq_semantic_threshold_english: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        validation_alias="PATROL_TOPOLOGY_RQ_SEMANTIC_THRESHOLD_ENGLISH",
        description="Relaxed cosine gate when either compared RQ label is predominantly English.",
    )
    patrol_claim_rq_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        validation_alias="PATROL_CLAIM_RQ_THRESHOLD",
        description="Strict cosine gate used when reranker is disabled (legacy fallback).",
    )
    patrol_claim_rq_coarse_threshold: float = Field(
        default=0.42,
        ge=0.0,
        le=1.0,
        validation_alias="PATROL_CLAIM_RQ_COARSE_THRESHOLD",
        description="Stage-1 bi-encoder coarse recall threshold for claim_evolution RQ pairing.",
    )
    patrol_claim_rq_rerank_threshold: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        validation_alias="PATROL_RERANK_THRESHOLD",
        description="Stage-2 cross-encoder rerank hard gate for claim_evolution RQ pairing.",
    )
    patrol_claim_rq_max_rerank_candidates: int = Field(
        default=8,
        ge=1,
        le=32,
        validation_alias="PATROL_CLAIM_RQ_MAX_RERANK_CANDIDATES",
        description="Max coarse RQ pairs forwarded to reranker per insight build.",
    )
    patrol_claim_rq_threshold_english: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        validation_alias="PATROL_CLAIM_RQ_THRESHOLD_ENGLISH",
        description=(
            "Lower cosine-similarity threshold applied when either research question label is predominantly English."
        ),
    )
    patrol_claim_chunk_top_k: int = Field(
        default=3,
        ge=1,
        le=20,
        validation_alias="PATROL_CLAIM_CHUNK_TOP_K",
        description="Top-k chunks retrieved from VectorStore to backfill missing Claim nodes in claim_evolution.",
    )
    patrol_method_overlap_query_template: str = Field(
        default="{anchor_labels} 具体应用场景 数据集配置 实验数值特征",
        min_length=1,
        validation_alias="PATROL_METHOD_OVERLAP_QUERY_TEMPLATE",
        description=(
            "Query template for VectorStore recall in method_overlap. "
            "Placeholders: {anchor_labels}, {method_labels}, {dataset_labels}."
        ),
    )
    patrol_method_overlap_top_k: int = Field(
        default=3,
        ge=0,
        le=20,
        validation_alias="PATROL_METHOD_OVERLAP_TOP_K",
        description="Top-k chunks retrieved from VectorStore for method_overlap context enhancement.",
    )
    patrol_claim_evolution_query_template: str = Field(
        default="{anchor_labels} 结论 证据 实验设计 差异",
        min_length=1,
        validation_alias="PATROL_CLAIM_EVOLUTION_QUERY_TEMPLATE",
        description=(
            "Query template for VectorStore recall in claim_evolution. "
            "Placeholders: {anchor_labels}, {question_labels}, {thesis_labels}."
        ),
    )
    patrol_claim_evolution_top_k: int = Field(
        default=3,
        ge=0,
        le=20,
        validation_alias="PATROL_CLAIM_EVOLUTION_TOP_K",
        description="Top-k chunks retrieved from VectorStore for claim_evolution context enhancement.",
    )

    def patrol_topology_rq_semantic_threshold_for(self, *labels: str) -> float:
        """Return the topology RQ semantic resonance threshold for a candidate RQ pair."""
        from backend.patrol.similarity import is_predominantly_english

        if any(is_predominantly_english(label) for label in labels if label.strip()):
            return self.patrol_topology_rq_semantic_threshold_english
        return self.patrol_topology_rq_semantic_threshold

    def patrol_claim_rq_threshold_effective(self, *labels: str) -> float:
        """Return the claim-evolution RQ gate threshold, with English-aware relaxation."""
        from backend.patrol.similarity import is_predominantly_english

        if any(is_predominantly_english(label) for label in labels if label.strip()):
            return self.patrol_claim_rq_threshold_english
        return self.patrol_claim_rq_threshold
