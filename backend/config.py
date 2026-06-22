"""Application settings loaded from environment variables."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Different embedding models train with different vector-space densities.
# Hard-coding a single threshold would break when switching models, so we keep
# per-model defaults and allow explicit env overrides.
DEFAULT_EMBEDDING_MODEL_THRESHOLDS: dict[str, dict[str, float]] = {
    "bge-m3": {
        "similarity": 0.85,
        "knn": 0.75,
    },
    "text-embedding-3-small": {
        "similarity": 0.65,
        "knn": 0.55,
    },
    "default": {
        "similarity": 0.80,
        "knn": 0.70,
    },
}

# Per-paradigm, per-node-category similarity thresholds for semantic clustering.
# A single global threshold causes over-merging for Method nodes (too loose) and
# under-merging for Dataset nodes (too strict).  Categories are intentionally
# coarse-grained so the matrix stays small and maintainable; unknown types fall
# back to the "Concept" bucket.
DYNAMIC_CLUSTERING_THRESHOLDS: dict[str, dict[str, float]] = {
    "STEM": {
        "Method": 0.92,
        "Dataset": 0.82,
        "Metric": 0.88,
        "Baseline": 0.88,
        "Concept": 0.88,
    },
    "HSS": {
        "Method": 0.86,
        "Dataset": 0.80,
        "Concept": 0.82,
    },
}


def _clustering_category(node_type: str) -> str:
    """Map a concrete node type to its coarse threshold category."""
    category_map: dict[str, str] = {
        "Method": "Method",
        "Dataset": "Dataset",
        "Metric": "Metric",
        "Baseline": "Baseline",
    }
    return category_map.get(node_type, "Concept")


class Settings(BaseSettings):
    """Runtime configuration; values come from `.env` at repository root."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_v1_prefix: str = "/api/v1"

    scholargraph_api_key: str = Field(default="", validation_alias="SCHOLARGRAPH_API_KEY")
    llm_mode: Literal["mock", "live"] = Field(default="mock", validation_alias="LLM_MODE")
    llm_api_base_url: str | None = Field(default=None, validation_alias="LLM_API_BASE_URL")
    llm_model_primary: str = Field(
        default="DeepSeek-V3-64K",
        validation_alias=AliasChoices("LLM_MODEL_PRIMARY", "LLM_MODEL"),
    )
    llm_model_fallback: str = Field(default="Qwen3-32B-64K", validation_alias="LLM_MODEL_FALLBACK")
    llm_timeout_seconds: int = Field(default=120, validation_alias="LLM_TIMEOUT_SECONDS")

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_api_base: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="OPENAI_API_BASE",
    )

    database_url: str = Field(
        default="sqlite:///./data/scholargraph.db",
        validation_alias="DATABASE_URL",
    )
    graph_data_dir: str = Field(default="./data/graphs", validation_alias="GRAPH_DATA_DIR")
    upload_dir: str = Field(default="./uploads", validation_alias="UPLOAD_DIR")

    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ORIGINS",
    )

    ingest_route: Literal["auto", "pymupdf_only"] = Field(
        default="auto",
        validation_alias="INGEST_ROUTE",
    )
    ingest_short_page_limit: int = Field(default=25, validation_alias="INGEST_SHORT_PAGE_LIMIT")
    ingest_mineru_enabled: bool = Field(default=True, validation_alias="INGEST_MINERU_ENABLED")
    ingest_mineru_lang: str = Field(default="auto", validation_alias="INGEST_MINERU_LANG")
    ingest_mineru_model_source: str = Field(
        default="modelscope",
        validation_alias="INGEST_MINERU_MODEL_SOURCE",
    )
    ingest_mineru_timeout_seconds: int = Field(
        default=600,
        validation_alias="INGEST_MINERU_TIMEOUT_SECONDS",
    )

    grobid_url: str = Field(default="http://127.0.0.1:8070", validation_alias="GROBID_URL")
    grobid_timeout_seconds: int = Field(default=300, validation_alias="GROBID_TIMEOUT_SECONDS")
    grobid_fallback_pymupdf: bool = Field(default=True, validation_alias="GROBID_FALLBACK_PYMUPDF")

    ingest_head_llm_enabled: bool = Field(default=True, validation_alias="INGEST_HEAD_LLM_ENABLED")
    ingest_head_llm_model: str = Field(default="", validation_alias="INGEST_HEAD_LLM_MODEL")
    ingest_head_llm_timeout_seconds: int = Field(
        default=60,
        validation_alias="INGEST_HEAD_LLM_TIMEOUT_SECONDS",
    )

    extract_llm_enabled: bool = Field(default=True, validation_alias="EXTRACT_LLM_ENABLED")
    extract_max_input_chars: int = Field(default=20_000, validation_alias="EXTRACT_MAX_INPUT_CHARS")
    extract_heuristic_fallback: bool = Field(
        default=True,
        validation_alias="EXTRACT_HEURISTIC_FALLBACK",
    )
    extract_two_phase_enabled: bool = Field(
        default=True,
        validation_alias="EXTRACT_TWO_PHASE_ENABLED",
    )
    extract_chunked_enabled: bool = Field(
        default=True,
        validation_alias="EXTRACT_CHUNKED_ENABLED",
    )
    extract_chunk_max_chars: int = Field(
        default=12_000,
        ge=1_000,
        validation_alias="EXTRACT_CHUNK_MAX_CHARS",
    )
    extract_chunk_overlap_ratio: float = Field(
        default=0.12,
        ge=0.0,
        le=0.5,
        validation_alias="EXTRACT_CHUNK_OVERLAP_RATIO",
        description="Sliding-window overlap between consecutive chunks (0.0 = no overlap).",
    )
    extract_chunk_concurrency: int = Field(
        default=2,
        ge=1,
        le=10,
        validation_alias="EXTRACT_CHUNK_CONCURRENCY",
    )
    extract_chunk_max_chunks: int = Field(
        default=1000,
        ge=1,
        validation_alias="EXTRACT_CHUNK_MAX_CHUNKS",
    )
    extract_chunk_rpm_limit: int = Field(
        default=60,
        ge=0,
        validation_alias="EXTRACT_CHUNK_RPM_LIMIT",
    )
    extract_chunk_tpm_limit: int = Field(
        default=1_000_000,
        ge=0,
        validation_alias="EXTRACT_CHUNK_TPM_LIMIT",
    )
    extract_chunk_retry_attempts: int = Field(
        default=3,
        ge=0,
        validation_alias="EXTRACT_CHUNK_RETRY_ATTEMPTS",
    )
    extract_chunk_retry_delay_s: float = Field(
        default=3.0,
        ge=0,
        validation_alias="EXTRACT_CHUNK_RETRY_DELAY_S",
    )
    extract_structured_output_repair: bool = Field(
        default=True,
        validation_alias="EXTRACT_STRUCTURED_OUTPUT_REPAIR",
    )
    extract_min_supports_rationale_coverage: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        validation_alias="EXTRACT_MIN_SUPPORTS_RATIONALE_COVERAGE",
    )
    extract_max_isolated_node_ratio: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        validation_alias="EXTRACT_MAX_ISOLATED_NODE_RATIO",
    )
    extract_max_generic_edge_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        validation_alias="EXTRACT_MAX_GENERIC_EDGE_RATIO",
        description="Maximum allowed fraction of generic RELATES_TO-like edges. "
        "1.0 disables the check; set lower (e.g. 0.25) to enforce dynamic relation invention.",
    )

    # ------------------------------------------------------------------
    # Semantic clustering / graph dehydration (Slice 2 second-order)
    # ------------------------------------------------------------------
    semantic_clustering_enabled: bool = Field(
        default=False,
        validation_alias="SEMANTIC_CLUSTERING_ENABLED",
    )
    # When negative, fall back to model-specific defaults defined below.
    # Explicit env values always take precedence.
    semantic_similarity_threshold: float = Field(
        default=-1.0,
        ge=-1.0,
        le=1.0,
        validation_alias="SEMANTIC_SIMILARITY_THRESHOLD",
    )
    semantic_clustering_dynamic_thresholds_enabled: bool = Field(
        default=True,
        validation_alias="SEMANTIC_CLUSTERING_DYNAMIC_THRESHOLDS_ENABLED",
        description="Use per-paradigm, per-node-category thresholds instead of a single global threshold.",
    )
    semantic_knn_threshold: float = Field(
        default=-1.0,
        ge=-1.0,
        le=1.0,
        validation_alias="SEMANTIC_KNN_THRESHOLD",
    )
    embedding_provider: Literal["openai", "ollama"] = Field(
        default="openai",
        validation_alias="EMBEDDING_PROVIDER",
    )
    embedding_model: str = Field(
        default="bge-m3",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_api_base_url: str | None = Field(
        default=None,
        validation_alias="EMBEDDING_API_BASE_URL",
    )
    embedding_api_key: str = Field(
        default="",
        validation_alias="EMBEDDING_API_KEY",
    )
    embedding_ollama_url: str = Field(
        default="http://localhost:11434",
        validation_alias="EMBEDDING_OLLAMA_URL",
    )

    extract_repair_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias="EXTRACT_REPAIR_MAX_RETRIES",
    )

    classifier_llm_enabled: bool = Field(default=True, validation_alias="CLASSIFIER_LLM_ENABLED")
    classifier_heuristic_fallback: bool = Field(
        default=True,
        validation_alias="CLASSIFIER_HEURISTIC_FALLBACK",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> str:
        if isinstance(value, list):
            return ",".join(value)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_model(self) -> str:
        """Backward-compatible alias for the primary model name."""
        return self.llm_model_primary

    @property
    def is_llm_mock(self) -> bool:
        return self.llm_mode == "mock"

    @property
    def is_llm_live(self) -> bool:
        return self.llm_mode == "live"

    @property
    def embedding_api_key_effective(self) -> str:
        return self.embedding_api_key.strip() or self.require_llm_key()

    @property
    def embedding_api_base_url_effective(self) -> str | None:
        return self.embedding_api_base_url or self.llm_api_base_url or None

    @property
    def semantic_similarity_threshold_effective(self) -> float:
        """Return the entity-resolution threshold.

        Explicit ``SEMANTIC_SIMILARITY_THRESHOLD`` values win; otherwise we
        look up a per-model default.
        """
        if self.semantic_similarity_threshold >= 0:
            return self.semantic_similarity_threshold
        thresholds = DEFAULT_EMBEDDING_MODEL_THRESHOLDS.get(
            self.embedding_model,
            DEFAULT_EMBEDDING_MODEL_THRESHOLDS["default"],
        )
        return thresholds["similarity"]

    def semantic_similarity_threshold_for(
        self,
        node_type_a: str,
        node_type_b: str,
        paradigm: str,
    ) -> float:
        """Return the pairwise merge threshold for two node types.

        Priority:
        1. Explicit ``SEMANTIC_SIMILARITY_THRESHOLD`` (global override).
        2. Dynamic matrix when ``semantic_clustering_dynamic_thresholds_enabled``.
        3. Per-model default fallback.

        For cross-category pairs the stricter of the two category thresholds is
        used, so a Method-Dataset pair uses the Method threshold.
        """
        if self.semantic_similarity_threshold >= 0:
            return self.semantic_similarity_threshold

        if self.semantic_clustering_dynamic_thresholds_enabled:
            category_a = _clustering_category(node_type_a)
            category_b = _clustering_category(node_type_b)
            matrix = DYNAMIC_CLUSTERING_THRESHOLDS.get(
                paradigm,
                DYNAMIC_CLUSTERING_THRESHOLDS["STEM"],
            )
            threshold_a = matrix.get(category_a, matrix["Concept"])
            threshold_b = matrix.get(category_b, matrix["Concept"])
            return max(threshold_a, threshold_b)

        return self.semantic_similarity_threshold_effective

    @property
    def semantic_knn_threshold_effective(self) -> float:
        """Return the K-NN island-bridging threshold.

        Explicit ``SEMANTIC_KNN_THRESHOLD`` values win; otherwise we look up a
        per-model default.
        """
        if self.semantic_knn_threshold >= 0:
            return self.semantic_knn_threshold
        thresholds = DEFAULT_EMBEDDING_MODEL_THRESHOLDS.get(
            self.embedding_model,
            DEFAULT_EMBEDDING_MODEL_THRESHOLDS["default"],
        )
        return thresholds["knn"]

    @property
    def llm_model_fallback_effective(self) -> str | None:
        """Return fallback model when set and distinct from primary; else None."""
        fallback = self.llm_model_fallback.strip()
        primary = self.llm_model_primary.strip()
        if not fallback or fallback == primary:
            return None
        return fallback

    def require_llm_key(self) -> str:
        """Return the primary LLM API key or raise a clear error (live mode only)."""
        if self.is_llm_mock:
            return ""
        key = self.scholargraph_api_key.strip() or self.openai_api_key.strip()
        if not key:
            msg = "缺少 LLM API Key：请在仓库根目录 .env 中设置 SCHOLARGRAPH_API_KEY 或 OPENAI_API_KEY"
            raise ValueError(msg)
        return key


def _should_ignore_dotenv() -> bool:
    """Whether ``get_settings()`` should skip loading repository ``.env``.

    Under pytest, ``tests/conftest.py`` sets ``SCHOLARGRAPH_IGNORE_DOTENV=1`` so
    defaults and ``monkeypatch.setenv`` stay deterministic. Opt in with ``0`` for
    live probes that need a real ``.env``.
    """
    raw = os.environ.get("SCHOLARGRAPH_IGNORE_DOTENV")
    if raw is not None:
        return raw.lower() in ("1", "true", "yes")
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


@lru_cache
def get_settings() -> Settings:
    if _should_ignore_dotenv():
        return Settings(_env_file=None)
    return Settings()
