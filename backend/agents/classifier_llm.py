"""LLM structured paradigm classification (Phase G primary path)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, SecretStr

from backend.agents.classifier_types import ClassifierProfile, CoreContributionAnalysis
from backend.config import Settings, get_settings
from backend.llm.client import LlmClient, get_llm_client
from backend.llm.mock_chat import MockChat
from backend.llm.structured_output import _parse_model_response
from backend.schemas.paradigm import Paradigm, ParadigmClassification

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
CLASSIFIER_PROMPT_PATH = PROMPTS_DIR / "classifier.md"
CLASSIFIER_PROFILE_PROMPT_PATH = PROMPTS_DIR / "classifier_profile.md"
CLASSIFIER_CORE_CONTRIBUTION_PROMPT_PATH = PROMPTS_DIR / "classifier_core_contribution.md"

T = TypeVar("T", bound=BaseModel)


def load_classifier_prompt() -> str:
    """Load system prompt from ``backend/prompts/classifier.md``."""
    if CLASSIFIER_PROMPT_PATH.is_file():
        return CLASSIFIER_PROMPT_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Missing classifier prompt: {CLASSIFIER_PROMPT_PATH}")


def load_classifier_profile_prompt() -> str:
    """Load Stage A system prompt from ``backend/prompts/classifier_profile.md``."""
    if CLASSIFIER_PROFILE_PROMPT_PATH.is_file():
        return CLASSIFIER_PROFILE_PROMPT_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"Missing classifier profile prompt: {CLASSIFIER_PROFILE_PROMPT_PATH}",
    )


def load_classifier_core_contribution_prompt() -> str:
    """Load Stage B.1 system prompt from ``backend/prompts/classifier_core_contribution.md``."""
    if CLASSIFIER_CORE_CONTRIBUTION_PROMPT_PATH.is_file():
        return CLASSIFIER_CORE_CONTRIBUTION_PROMPT_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"Missing classifier core contribution prompt: {CLASSIFIER_CORE_CONTRIBUTION_PROMPT_PATH}",
    )


def _extract_raw_json_from_error(exc: Exception) -> str | None:
    """Pull the raw LLM output out of a Pydantic json_invalid ValidationError."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return None
    try:
        error_list = errors()
        if not isinstance(error_list, list):
            return None
        for err in error_list:
            if isinstance(err, dict) and err.get("type") == "json_invalid":
                return err.get("input")
    except Exception:
        return None
    return None


def _build_chat_for_model(settings: Settings, model_name: str) -> LlmClient | None:
    """Build a one-off chat for a specific model name (live only)."""
    if settings.is_llm_mock:
        return None
    api_key = settings.require_llm_key()
    base_url = settings.llm_api_base_url or settings.openai_api_base or None
    timeout = settings.classifier_profile_llm_timeout_seconds
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(  # type: ignore[return-value]
        api_key=SecretStr(api_key),
        base_url=base_url,
        model=model_name,
        timeout=timeout,
    )


def _resolve_profile_chat(client: LlmClient, settings: Settings) -> MockChat | object:
    """Return the chat backend for Stage A profile generation."""
    configured_model = settings.classifier_profile_llm_model.strip()
    if not configured_model:
        return client.chat
    if configured_model == settings.llm_model_primary:
        return client.chat
    if client.is_mock:
        return MockChat(model=configured_model)
    chat = _build_chat_for_model(settings, configured_model)
    if chat is None:
        return client.chat
    return chat


def _format_profile_user_content(
    profile: ClassifierProfile,
    classifier_input: str,
    core_contribution: CoreContributionAnalysis | None = None,
) -> str:
    parts = [
        "Profile:",
        f"Goal: {profile.goal}",
        f"Tools: {profile.tools}",
        f"Domain: {profile.domain}",
    ]
    if core_contribution is not None:
        parts.extend(
            [
                "",
                "Core Contribution Interrogation:",
                f"Summary: {core_contribution.core_contribution_summary}",
                f"Substitution Test: {core_contribution.substitution_test}",
                f"Target Journal Test: {core_contribution.target_journal_test}",
            ]
        )
    parts.extend(
        [
            "",
            f"Original paper snippets:\n{classifier_input.strip()}",
        ]
    )
    return "\n".join(parts)


async def _invoke_structured(
    chat: object,
    *,
    system_prompt: str,
    user_content: str,
    response_model: type[T],
) -> T:
    # _invoke_structured is only called with live ChatOpenAI instances in practice;
    # the mock path goes through MockChat.with_structured_output instead.
    structured = chat.with_structured_output(response_model)  # type: ignore[union-attr]
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    try:
        if hasattr(structured, "ainvoke"):
            result = await structured.ainvoke(messages)
        else:
            result = structured.invoke(messages)  # type: ignore[attr-defined]
    except Exception as exc:
        raw = _extract_raw_json_from_error(exc)
        if raw is not None:
            try:
                return _parse_model_response(raw, response_model)  # type: ignore[return-value]
            except Exception:
                pass
        raise

    if isinstance(result, response_model):
        return result
    if isinstance(result, str):
        return _parse_model_response(result, response_model)  # type: ignore[return-value]
    return response_model.model_validate(result)


def _validate_llm_classification(classification: ParadigmClassification) -> None:
    if classification.paradigm not in (Paradigm.STEM, Paradigm.HSS):
        raise ValueError(f"Invalid paradigm: {classification.paradigm}")
    if not classification.reason.strip():
        raise ValueError("LLM classification reason is empty.")


def _validate_profile(profile: ClassifierProfile) -> None:
    if not profile.goal.strip():
        raise ValueError("Profile goal is empty.")
    if not profile.domain.strip():
        raise ValueError("Profile domain is empty.")


async def generate_profile_with_llm(
    classifier_input: str,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
) -> ClassifierProfile:
    """Stage A: semantic dehydration — produce goal/tools/domain profile."""
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    system_prompt = load_classifier_profile_prompt()
    user_content = classifier_input.strip()
    chat = _resolve_profile_chat(client, cfg)

    profile = await _invoke_structured(
        chat,
        system_prompt=system_prompt,
        user_content=user_content,
        response_model=ClassifierProfile,
    )
    _validate_profile(profile)
    return profile


async def interrogate_core_contribution_with_llm(
    classifier_input: str,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
) -> CoreContributionAnalysis:
    """Stage B.1: interrogate the core contribution before final judgment."""
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    system_prompt = load_classifier_core_contribution_prompt()
    user_content = classifier_input.strip()

    chat = _resolve_profile_chat(client, cfg)
    analysis = await _invoke_structured(
        chat,
        system_prompt=system_prompt,
        user_content=user_content,
        response_model=CoreContributionAnalysis,
    )
    if not analysis.core_contribution_summary.strip():
        raise ValueError("Core contribution summary is empty.")
    return analysis


async def judge_with_llm(
    classifier_input: str,
    profile: ClassifierProfile,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
    core_contribution: CoreContributionAnalysis | None = None,
) -> ParadigmClassification:
    """Stage B/Stage C: paradigm judgment given the Stage A profile and optional Stage B.1 interrogation."""
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    system_prompt = load_classifier_prompt()
    user_content = _format_profile_user_content(profile, classifier_input, core_contribution)

    last_error: Exception | None = None
    for use_fallback in (False, True):
        chat = client.fallback_chat if use_fallback and client.fallback_chat is not None else client.chat
        try:
            classification = await _invoke_structured(
                chat,
                system_prompt=system_prompt,
                user_content=user_content,
                response_model=ParadigmClassification,
            )
            _validate_llm_classification(classification)
            return classification
        except Exception as exc:
            last_error = exc
            model_label = "fallback" if use_fallback else "primary"
            logger.warning(
                "judge_llm attempt failed (%s): %s",
                model_label,
                exc,
            )

    assert last_error is not None
    raise last_error


async def classify_with_llm(
    classifier_input: str,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
    profile: ClassifierProfile | None = None,
) -> ParadigmClassification:
    """
    Classify via structured LLM.

    When ``profile`` is supplied, run Stage C (judge) directly.
    When ``profile`` is None and two-phase mode is enabled in settings,
    run Stage A (profile generation), optional Stage B.1 (core contribution
    interrogation), then Stage C (judgment).
    Otherwise fall back to a single-stage judgment call.
    """
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()

    if profile is not None:
        return await judge_with_llm(
            classifier_input,
            profile,
            settings=cfg,
            llm_client=client,
        )

    if not cfg.classifier_two_phase_enabled:
        return await judge_with_llm(
            classifier_input,
            ClassifierProfile(),
            settings=cfg,
            llm_client=client,
        )

    generated_profile = await generate_profile_with_llm(
        classifier_input,
        settings=cfg,
        llm_client=client,
    )

    core_contribution: CoreContributionAnalysis | None = None
    if cfg.classifier_core_contribution_enabled:
        core_contribution = await interrogate_core_contribution_with_llm(
            classifier_input,
            settings=cfg,
            llm_client=client,
        )

    return await judge_with_llm(
        classifier_input,
        generated_profile,
        settings=cfg,
        llm_client=client,
        core_contribution=core_contribution,
    )
