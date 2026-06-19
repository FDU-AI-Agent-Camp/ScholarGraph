"""Stage 1 node extraction for two-phase graph extraction (v2)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agents.extract_heuristic import extract_title
from backend.config import Settings, get_settings
from backend.llm.client import LlmClient, get_llm_client
from backend.schemas.extract_phase import ExtractedNodeList
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_NODE_PROMPT_FILES = {
    Paradigm.HSS: PROMPTS_DIR / "extract_nodes_hss.md",
    Paradigm.STEM: PROMPTS_DIR / "extract_nodes_stem.md",
}


def _load_base_prompt() -> str:
    base_path = PROMPTS_DIR / "extract_base.md"
    if base_path.is_file():
        return base_path.read_text(encoding="utf-8")
    return ""


def load_node_prompt(paradigm: Paradigm) -> str:
    """Load base + paradigm-specific node extraction prompt."""
    specific_path = _NODE_PROMPT_FILES[paradigm]
    specific = ""
    if specific_path.is_file():
        specific = specific_path.read_text(encoding="utf-8")
    parts = [part for part in (_load_base_prompt(), specific) if part.strip()]
    return "\n\n".join(parts)


def _build_user_payload(
    full_text: str,
    paradigm: Paradigm,
    paper_id: str,
    title: str | None,
    head_context: str | None,
    max_chars: int,
) -> str:
    """Build the JSON user payload for node extraction."""
    if max_chars > 0 and len(full_text) > max_chars:
        text = full_text[:max_chars]
        truncated = True
    else:
        text = full_text
        truncated = False

    payload: dict[str, object] = {
        "paper_id": paper_id,
        "paradigm": paradigm.value,
        "title": title or "",
        "full_text": text,
        "truncated": truncated,
    }
    if head_context and head_context.strip():
        payload["document_head"] = head_context.strip()
    return json.dumps(payload, ensure_ascii=False)


def _resolve_title(full_text: str, title: str | None) -> str:
    if title and title.strip():
        return title.strip()
    return extract_title(full_text)


async def extract_nodes_with_llm(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str | None = None,
    head_context: str | None = None,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
    previous_error: str | None = None,
) -> ExtractedNodeList:
    """Extract nodes via structured LLM call (Stage 1).

    Args:
        full_text: Paper full text.
        paradigm: STEM or HSS.
        paper_id: Paper identifier.
        title: Optional paper title.
        head_context: Optional refined document head (title/abstract/intro).
        settings: Optional settings override.
        llm_client: Optional LLM client override (for tests).
        previous_error: When set, the prompt asks the LLM to fix this error.

    Returns:
        Validated ExtractedNodeList.
    """
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    resolved_title = _resolve_title(full_text, title)
    system_prompt = load_node_prompt(paradigm)
    if previous_error:
        system_prompt += (
            f"\n\n## Previous Error to Fix\n\n{previous_error}\n\nPlease fix the above error when extracting nodes."
        )

    user_content = _build_user_payload(
        full_text=full_text,
        paradigm=paradigm,
        paper_id=paper_id,
        title=resolved_title,
        head_context=head_context,
        max_chars=cfg.extract_max_input_chars,
    )

    chat = client.chat
    structured = chat.with_structured_output(ExtractedNodeList)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    started_at = time.perf_counter()
    try:
        result = await structured.ainvoke(messages)
    except Exception as exc:
        logger.warning(
            "extract_nodes_failed",
            extra={"paper_id": paper_id, "paradigm": paradigm.value, "error": str(exc)},
        )
        raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    if not isinstance(result, ExtractedNodeList):
        result = ExtractedNodeList.model_validate(result)

    logger.info(
        "extract_nodes_success",
        extra={
            "paper_id": paper_id,
            "paradigm": paradigm.value,
            "node_count": len(result.nodes),
            "elapsed_ms": elapsed_ms,
        },
    )
    return result
