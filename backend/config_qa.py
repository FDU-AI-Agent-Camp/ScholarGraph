# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""QA / Judge LLM role bindings and RAG retrieval settings for :class:`backend.config.Settings`."""

from __future__ import annotations

from pydantic import AliasChoices, Field


class QaSettingsMixin:
    """Pydantic fields and helpers for multi-scale QA and benchmark Judge roles."""

    llm_model_qa: str = Field(default="", validation_alias="LLM_MODEL_QA")
    llm_model_judge: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_MODEL_JUDGE", "JUDGE_MODEL"),
    )
    qa_api_key: str = Field(default="", validation_alias="QA_API_KEY")
    judge_api_key: str = Field(default="", validation_alias="JUDGE_API_KEY")
    qa_api_base_url: str | None = Field(default=None, validation_alias="QA_API_BASE_URL")
    judge_api_base_url: str | None = Field(default=None, validation_alias="JUDGE_API_BASE_URL")
    qa_timeout_seconds: int = Field(default=0, validation_alias="QA_TIMEOUT_SECONDS")
    judge_timeout_seconds: int = Field(default=120, validation_alias="JUDGE_TIMEOUT_SECONDS")

    chromadb_path: str = Field(default="./data/chroma", validation_alias="CHROMADB_PATH")
    chromadb_chunk_collection: str = Field(default="paper_chunks", validation_alias="CHROMADB_CHUNK_COLLECTION")
    chromadb_entity_collection: str = Field(default="paper_entities", validation_alias="CHROMADB_ENTITY_COLLECTION")
    chromadb_relation_collection: str = Field(
        default="paper_relations",
        validation_alias="CHROMADB_RELATION_COLLECTION",
    )
    rag_chunk_size_chars: int = Field(default=1500, ge=200, validation_alias="RAG_CHUNK_SIZE_CHARS")
    rag_chunk_overlap_ratio: float = Field(default=0.20, ge=0.0, lt=1.0, validation_alias="RAG_CHUNK_OVERLAP_RATIO")
    rag_chunk_min_chunk_chars: int = Field(default=200, ge=1, validation_alias="RAG_CHUNK_MIN_CHUNK_CHARS")
    rag_chunk_include_references: bool = Field(default=False, validation_alias="RAG_CHUNK_INCLUDE_REFERENCES")
    rag_chunk_min_soft_boundary_window_chars: int = Field(
        default=200,
        ge=50,
        validation_alias="RAG_CHUNK_MIN_SOFT_BOUNDARY_WINDOW_CHARS",
    )
    rag_top_k_chunks: int = Field(default=5, ge=1, validation_alias="RAG_TOP_K_CHUNKS")
    rag_top_k_entities: int = Field(default=5, ge=1, validation_alias="RAG_TOP_K_ENTITIES")
    rag_top_k_relations: int = Field(default=5, ge=1, validation_alias="RAG_TOP_K_RELATIONS")
    qa_retrieval_timeout_seconds: float = Field(
        default=3.0,
        gt=0.0,
        validation_alias="QA_RETRIEVAL_TIMEOUT_SECONDS",
    )
    qa_retrieval_context_max_chars: int = Field(
        default=12_000,
        ge=500,
        validation_alias="QA_RETRIEVAL_CONTEXT_MAX_CHARS",
    )
    # P13 dual-layer indexing watchdog (sync dedicated-thread macro + wait_for micro)
    rag_single_index_timeout_seconds: float = Field(
        default=120.0,
        gt=0.0,
        validation_alias="RAG_SINGLE_INDEX_TIMEOUT_SECONDS",
        description="Layer-1 asyncio.wait_for timeout around a single paper RAG index build.",
    )
    rag_indexing_watchdog_seconds: float = Field(
        default=300.0,
        gt=0.0,
        validation_alias="RAG_INDEXING_WATCHDOG_SECONDS",
        description="Layer-2: force-promote when indexing_started_at is older than this "
        "(and heartbeat is missing/stale).",
    )
    rag_indexing_watchdog_interval_seconds: float = Field(
        default=60.0,
        gt=0.0,
        validation_alias="RAG_INDEXING_WATCHDOG_INTERVAL_SECONDS",
        description="Layer-2 dedicated OS-thread sleep interval between sync DB scans.",
    )
    rag_indexing_watchdog_enabled: bool = Field(
        default=True,
        validation_alias="RAG_INDEXING_WATCHDOG_ENABLED",
        description="Enable cold-boot reconcile + out-of-loop macro watchdog thread.",
    )
    rag_indexing_heartbeat_interval_seconds: float = Field(
        default=15.0,
        gt=0.0,
        validation_alias="RAG_INDEXING_HEARTBEAT_INTERVAL_SECONDS",
        description="How often the indexing handler touches indexing_heartbeat.",
    )
    rag_indexing_heartbeat_stale_seconds: float = Field(
        default=90.0,
        gt=0.0,
        validation_alias="RAG_INDEXING_HEARTBEAT_STALE_SECONDS",
        description="Layer-2: only force-promote when indexing_heartbeat is missing "
        "or older than this (avoids killing slow-but-alive builds).",
    )
    # Processing / pending orphan heal (cold-boot + wall-clock daemon)
    process_watchdog_enabled: bool = Field(
        default=True,
        validation_alias="PROCESS_WATCHDOG_ENABLED",
        description="Enable cold-boot pending/processing reconcile + wall-clock watchdog.",
    )
    process_watchdog_seconds: float = Field(
        default=900.0,
        gt=0.0,
        validation_alias="PROCESS_WATCHDOG_SECONDS",
        description=(
            "PROCESSING candidate age (seconds) before vitality dual-check. "
            "Live in-memory Task renews the lease (no false kill on long LLM); "
            "true zombies get Cascading Kill then PROCESS_TIMEOUT. "
            "Need not cover the longest stage wall-clock — keep ~900s."
        ),
    )
    process_watchdog_interval_seconds: float = Field(
        default=60.0,
        gt=0.0,
        validation_alias="PROCESS_WATCHDOG_INTERVAL_SECONDS",
        description="Dedicated OS-thread sleep interval between sync processing scans.",
    )
    process_orphan_grace_seconds: float = Field(
        default=10.0,
        ge=0.0,
        validation_alias="PROCESS_ORPHAN_GRACE_SECONDS",
        description="Cold-boot tombstone grace ε: only fail pending/processing with "
        "updated_at older than boot_time − ε (rolling-update safety).",
    )
    pending_queue_timeout_seconds: float = Field(
        default=3600.0,
        gt=0.0,
        validation_alias="PENDING_QUEUE_TIMEOUT_SECONDS",
        description="Fail PENDING papers whose updated_at is older than this (queue backlog).",
    )
    paper_ops_claim_ttl_seconds: float = Field(
        default=600.0,
        gt=0.0,
        validation_alias="PAPER_OPS_CLAIM_TTL_SECONDS",
        description=(
            "TTL for durable paper_ops_claims rows (force delete ∪ reextract wipe mutex). "
            "Expired leases are stealable so a crashed worker cannot permanently 409."
        ),
    )
    paper_wipe_vector_sweep_delay_seconds: float = Field(
        default=120.0,
        gt=0.0,
        validation_alias="PAPER_WIPE_VECTOR_SWEEP_DELAY_SECONDS",
        description=(
            "Wave-2 compensate delay after force wipe: delete_run for revoked / prior "
            "active index_run_id after to_thread upsert stragglers are statistically dead. "
            "Must cover RAG_SINGLE_INDEX_TIMEOUT_SECONDS wait_for window (≥120s)."
        ),
    )

    @property
    def qa_model_effective(self) -> str:
        """Return the QA Generator model; falls back to the primary LLM."""
        return self.llm_model_qa.strip() or self.llm_model_primary  # type: ignore[attr-defined]

    @property
    def judge_model_effective(self) -> str:
        """Return the Judge model; falls back to the primary LLM."""
        return self.llm_model_judge.strip() or self.llm_model_primary  # type: ignore[attr-defined]

    @property
    def qa_timeout_seconds_effective(self) -> int:
        return self.qa_timeout_seconds if self.qa_timeout_seconds > 0 else self.llm_timeout_seconds  # type: ignore[attr-defined]

    @property
    def qa_api_base_url_effective(self) -> str | None:
        return self.qa_api_base_url or self.llm_api_base_url or self.openai_api_base or None  # type: ignore[attr-defined]

    @property
    def judge_api_base_url_effective(self) -> str | None:
        return self.judge_api_base_url or self.llm_api_base_url or self.openai_api_base or None  # type: ignore[attr-defined]

    @property
    def qa_api_key_effective(self) -> str:
        return self.qa_api_key.strip() or self.require_llm_key()  # type: ignore[attr-defined]

    @property
    def judge_api_key_effective(self) -> str:
        return self.judge_api_key.strip() or self.require_llm_key()  # type: ignore[attr-defined]
