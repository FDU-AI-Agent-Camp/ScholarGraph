"""LLM structured graph extraction (Phase F primary path)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import Settings, get_settings
from backend.llm.client import LlmClient, get_llm_client
from backend.llm.structured_output import ainvoke_structured
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_PROMPT_FILES = {
    Paradigm.HSS: PROMPTS_DIR / "extract_hss.md",
    Paradigm.STEM: PROMPTS_DIR / "extract_stem.md",
}


def load_extract_prompt(paradigm: Paradigm) -> str:
    """Load paradigm-specific system prompt from ``backend/prompts/extract_*.md``."""
    path = _PROMPT_FILES[paradigm]
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Missing extract prompt: {path}")


def truncate_full_text(full_text: str, *, max_chars: int) -> tuple[str, bool]:
    """Return truncated text and whether truncation occurred."""
    if max_chars <= 0 or len(full_text) <= max_chars:
        return full_text, False
    return full_text[:max_chars], True


def build_user_payload(
    *,
    full_text: str,
    paradigm: Paradigm,
    paper_id: str,
    title: str | None,
    head_context: str | None,
    max_chars: int,
) -> str:
    truncated, was_truncated = truncate_full_text(full_text, max_chars=max_chars)
    payload: dict[str, object] = {
        "paper_id": paper_id,
        "paradigm": paradigm.value,
        "title": title or "",
        "full_text": truncated,
        "truncated": was_truncated,
    }
    if head_context and head_context.strip():
        payload["document_head"] = head_context.strip()
    return json.dumps(payload, ensure_ascii=False)


async def _invoke_structured(
    client: LlmClient,
    *,
    system_prompt: str,
    user_content: str,
    use_fallback_model: bool,
) -> UnifiedPaperGraph:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    return await ainvoke_structured(
        client,
        UnifiedPaperGraph,
        messages,
        use_fallback_model=use_fallback_model,
    )


def _validate_llm_graph(graph: UnifiedPaperGraph, *, expected_paradigm: Paradigm) -> None:
    if not graph.nodes:
        raise ValueError("LLM graph has no nodes.")
    if not graph.edges:
        raise ValueError("LLM graph has no edges.")
    if graph.paradigm != expected_paradigm:
        raise ValueError(f"LLM graph paradigm {graph.paradigm} != expected {expected_paradigm}.")


def _coerce_paradigm_to_expected(
    graph: UnifiedPaperGraph,
    *,
    expected_paradigm: Paradigm,
    paper_id: str,
) -> UnifiedPaperGraph:
    """Align LLM ``paradigm`` field with classify output; re-validate node/edge whitelist."""
    if graph.paradigm == expected_paradigm:
        return graph
    logger.warning(
        "extract_llm_paradigm_coerced",
        extra={
            "paper_id": paper_id,
            "llm_paradigm": graph.paradigm.value,
            "expected_paradigm": expected_paradigm.value,
        },
    )
    payload = graph.model_dump(mode="python")
    payload["paradigm"] = expected_paradigm
    return UnifiedPaperGraph.model_validate(payload)


async def extract_with_llm(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str | None = None,
    head_context: str | None = None,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
) -> UnifiedPaperGraph:
    """Extract a graph via a single structured LLM call."""
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    max_chars = cfg.extract_max_input_chars
    _, was_truncated = truncate_full_text(full_text, max_chars=max_chars)
    if was_truncated:
        logger.warning(
            "extract_input_truncated",
            extra={
                "paper_id": paper_id,
                "paradigm": paradigm.value,
                "original_chars": len(full_text),
                "max_chars": max_chars,
            },
        )

    system_prompt = load_extract_prompt(paradigm)
    user_content = build_user_payload(
        full_text=full_text,
        paradigm=paradigm,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
        max_chars=max_chars,
    )

    last_error: Exception | None = None
    for use_fallback in (False, True):
        if use_fallback and client.fallback_chat is None:
            continue
        model_label = "fallback" if use_fallback else "primary"
        started_at = time.perf_counter()
        try:
            graph = await _invoke_structured(
                client,
                system_prompt=system_prompt,
                user_content=user_content,
                use_fallback_model=use_fallback,
            )
            graph = _coerce_paradigm_to_expected(graph, expected_paradigm=paradigm, paper_id=paper_id)
            _validate_llm_graph(graph, expected_paradigm=paradigm)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "extract_llm_success",
                extra={
                    "paper_id": paper_id,
                    "paradigm": paradigm.value,
                    "model": model_label,
                    "elapsed_ms": elapsed_ms,
                    "node_count": len(graph.nodes),
                    "edge_count": len(graph.edges),
                },
            )
            return graph.model_copy(update={"paper_id": paper_id, "paradigm": paradigm})
        except Exception as exc:
            last_error = exc
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.warning(
                "extract_llm attempt failed (%s): %s",
                model_label,
                exc,
                extra={
                    "paper_id": paper_id,
                    "paradigm": paradigm.value,
                    "model": model_label,
                    "elapsed_ms": elapsed_ms,
                },
            )

    assert last_error is not None
    raise last_error
