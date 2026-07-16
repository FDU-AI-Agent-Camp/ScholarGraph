"""Patrol profile / Settings invariants — fail-fast must not regress.

Uses monkeypatched environment variables and ``get_settings()`` (no real models).
"""

from __future__ import annotations

import pytest
from backend.config import Settings, _resolve_profile_env_files, get_settings
from backend.startup.profile_validation import (
    ConfigurationError,
    assert_app_profile_declared,
    probe_reranker_connectivity,
    run_startup_profile_validation,
    should_run_reranker_startup_probe,
    validate_demo_prod_invariants,
)


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def _settings_from_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _clear_settings_cache()
    return get_settings()


def test_monkeypatch_demo_profile_reranker_disabled_blocks_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_PROFILE=demo + RERANKER_ENABLED=false must raise ConfigurationError."""
    settings = _settings_from_env(
        monkeypatch,
        APP_PROFILE="demo",
        RERANKER_ENABLED="false",
        RERANKER_MODEL="bge-reranker-large",
        LLM_MODE="live",
    )
    assert settings.app_profile == "demo"
    assert settings.reranker_enabled is False
    with pytest.raises(ConfigurationError, match="RERANKER_ENABLED=false"):
        run_startup_profile_validation(settings)


def test_monkeypatch_prod_profile_reranker_disabled_blocks_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings_from_env(
        monkeypatch,
        APP_PROFILE="prod",
        RERANKER_ENABLED="false",
        RERANKER_MODEL="bge-reranker-large",
        LLM_MODE="live",
    )
    with pytest.raises(ConfigurationError, match="RERANKER_ENABLED=false"):
        run_startup_profile_validation(settings)


def test_monkeypatch_ci_profile_allows_reranker_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings_from_env(
        monkeypatch,
        APP_PROFILE="ci",
        RERANKER_ENABLED="false",
        LLM_MODE="mock",
    )
    profile = run_startup_profile_validation(settings)
    assert profile == "ci"


def test_monkeypatch_demo_ready_profile_passes_static_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings_from_env(
        monkeypatch,
        APP_PROFILE="demo",
        RERANKER_ENABLED="true",
        RERANKER_MODEL="bge-reranker-large",
        LLM_MODE="live",
        STARTUP_RERANKER_PROBE="false",
    )
    profile = run_startup_profile_validation(settings)
    assert profile == "demo"
    assert settings.patrol_claim_rq_funnel_enabled() is True


def test_create_app_blocks_demo_profile_without_reranker(monkeypatch: pytest.MonkeyPatch) -> None:
    """``create_app()`` must invoke the same fail-fast gate as manual validation."""
    _settings_from_env(
        monkeypatch,
        APP_PROFILE="demo",
        RERANKER_ENABLED="false",
        RERANKER_MODEL="bge-reranker-large",
        LLM_MODE="live",
    )
    from backend.main import create_app

    with pytest.raises(ConfigurationError, match="RERANKER_ENABLED=false"):
        create_app()


def test_assert_app_profile_declared_blocks_missing_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_PROFILE", raising=False)
    _clear_settings_cache()
    settings = get_settings()
    with pytest.raises(ConfigurationError, match="APP_PROFILE 未设置"):
        assert_app_profile_declared(settings)


def test_demo_profile_requires_reranker_model_via_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_profile="demo",
        llm_mode="live",
        reranker_enabled=True,
        reranker_model="",
    )
    with pytest.raises(ConfigurationError, match="RERANKER_MODEL 为空"):
        validate_demo_prod_invariants(settings)


def test_resolve_profile_env_files_demo_and_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PROFILE", "demo")
    assert _resolve_profile_env_files() == (".env", ".env.demo")

    monkeypatch.setenv("APP_PROFILE", "prod")
    assert _resolve_profile_env_files() == (".env", ".env.prod")

    monkeypatch.setenv("APP_PROFILE", "ci")
    assert _resolve_profile_env_files() == (".env",)


def test_should_run_reranker_startup_probe_only_for_live_demo_prod() -> None:
    ci = Settings(_env_file=None, app_profile="ci", llm_mode="live", reranker_enabled=True, reranker_model="m")
    assert should_run_reranker_startup_probe(ci) is False

    demo_mock = Settings(
        _env_file=None,
        app_profile="demo",
        llm_mode="mock",
        reranker_enabled=True,
        reranker_model="bge-reranker-large",
        startup_reranker_probe_enabled=True,
    )
    assert should_run_reranker_startup_probe(demo_mock) is False

    demo_live = Settings(
        _env_file=None,
        app_profile="demo",
        llm_mode="live",
        reranker_enabled=True,
        reranker_model="bge-reranker-large",
        startup_reranker_probe_enabled=True,
    )
    assert should_run_reranker_startup_probe(demo_live) is True


@pytest.mark.asyncio
async def test_probe_reranker_connectivity_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        app_profile="demo",
        llm_mode="live",
        reranker_enabled=True,
        reranker_model="bge-reranker-large",
        startup_reranker_probe_enabled=True,
    )

    async def _boom(_self: object, _a: str, _b: str) -> float:
        raise ConnectionError("reranker unreachable")

    monkeypatch.setattr("backend.llm.reranker.RerankerClient.rerank_pair", _boom)

    with pytest.raises(ConfigurationError, match="Reranker 启动握手失败"):
        await probe_reranker_connectivity(settings)
