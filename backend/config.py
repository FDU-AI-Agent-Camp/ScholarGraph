"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; values come from `.env` at repository root."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
