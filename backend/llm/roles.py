"""Role-based LLM binding for Generator (QA) vs Judge decoupling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.config import Settings


class LlmRole(StrEnum):
    """Which workload an ``LlmClient`` instance serves."""

    DEFAULT = "default"
    QA = "qa"
    JUDGE = "judge"


@dataclass(frozen=True, slots=True)
class LlmBinding:
    """Resolved model + transport credentials for one LLM role."""

    role: LlmRole
    model: str
    api_key: str
    base_url: str | None
    timeout_seconds: int
    enable_fallback: bool


def resolve_llm_binding(settings: Settings, role: LlmRole) -> LlmBinding:
    """Map a logical role to model name, API key, base URL, and timeout."""
    if role is LlmRole.QA:
        return LlmBinding(
            role=role,
            model=settings.qa_model_effective,
            api_key=settings.qa_api_key_effective,
            base_url=settings.qa_api_base_url_effective,
            timeout_seconds=settings.qa_timeout_seconds_effective,
            enable_fallback=False,
        )
    if role is LlmRole.JUDGE:
        return LlmBinding(
            role=role,
            model=settings.judge_model_effective,
            api_key=settings.judge_api_key_effective,
            base_url=settings.judge_api_base_url_effective,
            timeout_seconds=settings.judge_timeout_seconds,
            enable_fallback=False,
        )
    return LlmBinding(
        role=role,
        model=settings.llm_model_primary,
        api_key=settings.require_llm_key(),
        base_url=settings.llm_api_base_url or settings.openai_api_base or None,
        timeout_seconds=settings.llm_timeout_seconds,
        enable_fallback=True,
    )


def clients_are_isolated(left: object, right: object) -> bool:
    """Return True when two clients do not share the same model/endpoint/key fingerprint."""
    left_fp = getattr(left, "identity_fingerprint", None)
    right_fp = getattr(right, "identity_fingerprint", None)
    if left_fp is None or right_fp is None:
        return True
    return left_fp != right_fp
