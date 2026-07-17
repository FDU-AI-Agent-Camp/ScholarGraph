# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Application settings loaded from environment variables."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.config_clustering import (
    DEFAULT_EMBEDDING_MODEL_THRESHOLDS,
    DYNAMIC_CLUSTERING_THRESHOLDS,
)
from backend.config_clustering import (
    clustering_category as _clustering_category,
)
from backend.config_patrol import PatrolSettingsMixin
from backend.config_qa import QaSettingsMixin

AppProfile = Literal["ci", "demo", "prod"]


class Settings(PatrolSettingsMixin, QaSettingsMixin, BaseSettings):
    """Runtime configuration; values come from `.env` at repository root."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_profile: AppProfile | None = Field(default=None, validation_alias="APP_PROFILE")
    debug: bool = True
    log_level: str = "INFO"
    asyncio_slow_callback_ms: float = Field(
        default=-1.0,
        validation_alias="ASYNCIO_SLOW_CALLBACK_MS",
        description=(
            "Loop block detector: set_debug + slow_callback_duration (ms). "
            "-1 = auto (100ms in development/test, off in staging/production); "
            "0 = force off; >0 = explicit threshold."
        ),
    )
    startup_reranker_probe_enabled: bool = Field(
        default=True,
        validation_alias="STARTUP_RERANKER_PROBE",
        description="demo/prod 启动时是否对 Reranker 做微量握手探针",
    )

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
    seed_demo_papers: bool = Field(default=False, validation_alias="SEED_DEMO_PAPERS")
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
    mineru_api_url: str = Field(default="", validation_alias="MINERU_API_URL")

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
    embedding_batch_size: int = Field(
        default=32,
        ge=1,
        le=1024,
        validation_alias="EMBEDDING_BATCH_SIZE",
    )

    # ------------------------------------------------------------------
    # Cloud reranker for fine-grained semantic merge verification
    # ------------------------------------------------------------------
    reranker_enabled: bool = Field(
        default=False,
        validation_alias="RERANKER_ENABLED",
    )
    reranker_model: str = Field(
        default="",
        validation_alias="RERANKER_MODEL",
    )
    reranker_api_base_url: str | None = Field(
        default=None,
        validation_alias="RERANKER_API_BASE_URL",
    )
    reranker_api_key: str = Field(
        default="",
        validation_alias="RERANKER_API_KEY",
    )
    reranker_batch_size: int = Field(
        default=32,
        ge=1,
        le=256,
        validation_alias="RERANKER_BATCH_SIZE",
    )
    reranker_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        validation_alias="RERANKER_THRESHOLD",
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
    classifier_two_phase_enabled: bool = Field(
        default=True,
        validation_alias="CLASSIFIER_TWO_PHASE_ENABLED",
        description="Run profile generation (Stage A) before paradigm judgment (Stage B).",
    )
    classifier_core_contribution_enabled: bool = Field(
        default=True,
        validation_alias="CLASSIFIER_CORE_CONTRIBUTION_ENABLED",
        description="Run core-contribution interrogation (Stage B.1) between profile and final judgment.",
    )
    classifier_profile_llm_model: str = Field(
        default="",
        validation_alias="CLASSIFIER_PROFILE_LLM_MODEL",
        description="Lightweight model for Stage A profile generation; empty means use primary model.",
    )
    classifier_profile_llm_timeout_seconds: int = Field(
        default=60,
        validation_alias="CLASSIFIER_PROFILE_LLM_TIMEOUT_SECONDS",
    )

    @field_validator("app_profile", mode="before")
    @classmethod
    def normalize_app_profile(cls, value: object) -> AppProfile | None:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized:
                return None
            return normalized  # type: ignore[return-value]
        return value  # type: ignore[return-value]

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
    def reranker_api_base_url_effective(self) -> str | None:
        return self.reranker_api_base_url or self.llm_api_base_url or None

    @property
    def reranker_api_key_effective(self) -> str:
        return self.reranker_api_key.strip() or self.require_llm_key()

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


def _resolve_profile_env_files() -> tuple[str, ...] | None:
    """Return layered env files for demo/prod; ``None`` lets pydantic use model default."""
    profile = os.environ.get("APP_PROFILE", "").strip().lower()
    if profile == "demo":
        return (".env", ".env.demo")
    if profile == "prod":
        return (".env", ".env.prod")
    return (".env",)


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
        # _env_file=None prevents pydantic-settings from loading repository .env
        # during tests, so monkeypatched environment variables stay deterministic.
        # pydantic_settings accepts _env_file at runtime but pyright cannot see it.
        return Settings(_env_file=None)  # type: ignore[call-arg]
    env_files = _resolve_profile_env_files()
    return Settings(_env_file=env_files)  # type: ignore[call-arg]
