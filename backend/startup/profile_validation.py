# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""APP_PROFILE topology and startup invariant validation for demo/prod."""

from __future__ import annotations

import sys
from typing import Literal

from backend.config import Settings

AppProfile = Literal["ci", "demo", "prod"]

_PROFILE_LABELS: dict[AppProfile, str] = {
    "ci": "CI / 本地轻量化",
    "demo": "验收演示",
    "prod": "生产环境",
}


class ConfigurationError(RuntimeError):
    """Raised when mandatory profile invariants are violated at startup."""


def profile_label(profile: AppProfile) -> str:
    return _PROFILE_LABELS[profile]


def assert_app_profile_declared(settings: Settings) -> AppProfile:
    """Require an explicit APP_PROFILE so runtime topology is never ambiguous."""
    if settings.app_profile is not None:
        return settings.app_profile
    message = (
        "APP_PROFILE 未设置，已阻断启动。\n"
        "  - 本地开发 / pytest：APP_PROFILE=ci（见 .env.example）\n"
        "  - 验收演示：APP_PROFILE=demo 并加载 .env.demo（RERANKER 必开）\n"
        "  - 生产部署：APP_PROFILE=prod 并加载 .env.prod（RERANKER 必开）"
    )
    _emit_configuration_error(message)
    raise ConfigurationError(message)


def validate_demo_prod_invariants(settings: Settings) -> None:
    """Static fail-fast checks for demo/prod profiles."""
    profile = settings.app_profile
    if profile not in {"demo", "prod"}:
        return

    violations: list[str] = []
    if not settings.reranker_enabled:
        violations.append(
            f"当前处于 {profile_label(profile)} 模式，检测到 RERANKER_ENABLED=false。\n"
            "claim_evolution 将无法走粗筛 + Cross-Encoder 精排漏斗。\n"
            f"修复：在 .env.{profile} 中设置 RERANKER_ENABLED=true。"
        )
    if not settings.reranker_model.strip():
        violations.append(
            f"当前处于 {profile_label(profile)} 模式，检测到 RERANKER_MODEL 为空。\n"
            "修复：在 .env.{profile} 中设置 RERANKER_MODEL（如 bge-reranker-v2-m3）。"
        )

    if violations:
        message = "\n\n".join(violations)
        _emit_configuration_error(message)
        raise ConfigurationError(message)


def should_run_reranker_startup_probe(settings: Settings) -> bool:
    """Return True when demo/prod should perform a live reranker handshake."""
    if settings.app_profile not in {"demo", "prod"}:
        return False
    if not settings.startup_reranker_probe_enabled:
        return False
    if settings.is_llm_mock:
        return False
    return settings.reranker_enabled and bool(settings.reranker_model.strip())


async def probe_reranker_connectivity(settings: Settings) -> None:
    """Optional live handshake — fail-fast when reranker endpoint is unreachable."""
    if not should_run_reranker_startup_probe(settings):
        return

    from backend.llm.reranker import RerankerClient

    profile = settings.app_profile
    assert profile in {"demo", "prod"}

    client = RerankerClient(settings)
    try:
        await client.rerank_pair("__startup_probe__", "__startup_probe__")
    except Exception as exc:  # noqa: BLE001 — startup guard must surface any transport failure
        message = (
            f"当前处于 {profile_label(profile)} 模式，Reranker 启动握手失败：{exc}\n"
            "请检查 RERANKER_API_BASE_URL、RERANKER_API_KEY（或 SCHOLARGRAPH_API_KEY）"
            "以及 Reranker 服务是否已正确挂载。"
        )
        _emit_configuration_error(message)
        raise ConfigurationError(message) from exc


def run_startup_profile_validation(settings: Settings) -> AppProfile:
    """Synchronous startup gate — profile declaration + demo/prod invariants."""
    profile = assert_app_profile_declared(settings)
    validate_demo_prod_invariants(settings)
    return profile


def _emit_configuration_error(message: str) -> None:
    print(f"[ConfigurationError] {message}", file=sys.stderr)
