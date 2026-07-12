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
