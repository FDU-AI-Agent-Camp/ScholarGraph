"""LLM structured paradigm classification (Phase G primary path)."""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import Settings, get_settings
from backend.llm.client import LlmClient, get_llm_client
from backend.schemas.paradigm import Paradigm, ParadigmClassification

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
CLASSIFIER_PROMPT_PATH = PROMPTS_DIR / "classifier.md"


def load_classifier_prompt() -> str:
    """Load system prompt from ``backend/prompts/classifier.md``."""
    if CLASSIFIER_PROMPT_PATH.is_file():
        return CLASSIFIER_PROMPT_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Missing classifier prompt: {CLASSIFIER_PROMPT_PATH}")


async def _invoke_structured(
    client: LlmClient,
    *,
    system_prompt: str,
    user_content: str,
    use_fallback_model: bool,
) -> ParadigmClassification:
    chat = client.fallback_chat if use_fallback_model and client.fallback_chat is not None else client.chat
    structured = chat.with_structured_output(ParadigmClassification)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    if hasattr(structured, "ainvoke"):
        result = await structured.ainvoke(messages)
    else:
        result = structured.invoke(messages)  # type: ignore[attr-defined]
    if isinstance(result, ParadigmClassification):
        return result
    return ParadigmClassification.model_validate(result)


def _validate_llm_classification(classification: ParadigmClassification) -> None:
    if classification.paradigm not in (Paradigm.STEM, Paradigm.HSS):
        raise ValueError(f"Invalid paradigm: {classification.paradigm}")
    if not classification.reason.strip():
        raise ValueError("LLM classification reason is empty.")


async def classify_with_llm(
    classifier_input: str,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
) -> ParadigmClassification:
    """Classify via a single structured LLM call."""
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    system_prompt = load_classifier_prompt()
    user_content = classifier_input.strip()

    last_error: Exception | None = None
    for use_fallback in (False, True):
        if use_fallback and client.fallback_chat is None:
            continue
        try:
            classification = await _invoke_structured(
                client,
                system_prompt=system_prompt,
                user_content=user_content,
                use_fallback_model=use_fallback,
            )
            _validate_llm_classification(classification)
            return classification
        except Exception as exc:
            last_error = exc
            model_label = "fallback" if use_fallback else "primary"
            logger.warning(
                "classify_llm attempt failed (%s): %s",
                model_label,
                exc,
            )

    assert last_error is not None
    raise last_error
