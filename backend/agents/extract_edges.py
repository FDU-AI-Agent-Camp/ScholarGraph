"""Stage 2 edge extraction for two-phase graph extraction (v2)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import Settings, get_settings
from backend.llm.client import LlmClient, get_llm_client
from backend.llm.structured_output import ainvoke_structured
from backend.schemas.extract_phase import ExtractedEdgeList, ExtractedNodeList
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_EDGE_PROMPT_FILES = {
    Paradigm.HSS: PROMPTS_DIR / "extract_edges_hss.md",
    Paradigm.STEM: PROMPTS_DIR / "extract_edges_stem.md",
}


def _load_base_prompt() -> str:
    base_path = PROMPTS_DIR / "extract_base.md"
    if base_path.is_file():
        return base_path.read_text(encoding="utf-8")
    return ""


def load_edge_prompt(paradigm: Paradigm) -> str:
    """Load base + paradigm-specific edge extraction prompt."""
    specific_path = _EDGE_PROMPT_FILES[paradigm]
    specific = ""
    if specific_path.is_file():
        specific = specific_path.read_text(encoding="utf-8")
    parts = [part for part in (_load_base_prompt(), specific) if part.strip()]
    return "\n\n".join(parts)


def _format_nodes_for_prompt(nodes: ExtractedNodeList) -> str:
    """Render available nodes as JSON for the edge extraction prompt."""
    simplified = [
        {
            "id": node.id,
            "label": node.label,
            "type": node.type,
        }
        for node in nodes.nodes
    ]
    return json.dumps(simplified, ensure_ascii=False, indent=2)


def _build_user_payload(
    nodes: ExtractedNodeList,
    full_text: str,
    paper_id: str,
    title: str | None,
    head_context: str | None,
    max_chars: int,
) -> str:
    """Build the JSON user payload for edge extraction."""
    if max_chars > 0 and len(full_text) > max_chars:
        text = full_text[:max_chars]
        truncated = True
    else:
        text = full_text
        truncated = False

    payload: dict[str, object] = {
        "paper_id": paper_id,
        "paradigm": nodes.paradigm.value,
        "title": title or "",
        "full_text": text,
        "truncated": truncated,
        "available_nodes": [{"id": node.id, "label": node.label, "type": node.type} for node in nodes.nodes],
    }
    if head_context and head_context.strip():
        payload["document_head"] = head_context.strip()
    return json.dumps(payload, ensure_ascii=False)


async def build_edges_with_llm(
    nodes: ExtractedNodeList,
    full_text: str,
    *,
    paper_id: str,
    title: str | None = None,
    head_context: str | None = None,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
    previous_error: str | None = None,
) -> ExtractedEdgeList:
    """Build edges from extracted nodes via structured LLM call (Stage 2).

    Args:
        nodes: Validated node list from Stage 1.
        full_text: Paper full text.
        paper_id: Paper identifier.
        title: Optional paper title.
        head_context: Optional refined document head.
        settings: Optional settings override.
        llm_client: Optional LLM client override (for tests).
        previous_error: When set, the prompt asks the LLM to fix this error.

    Returns:
        Validated ExtractedEdgeList.
    """
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    system_prompt = load_edge_prompt(nodes.paradigm)
    system_prompt = system_prompt.replace("{nodes_json}", _format_nodes_for_prompt(nodes))
    if previous_error:
        system_prompt += (
            f"\n\n## Previous Error to Fix\n\n{previous_error}\n\nPlease fix the above error when building edges."
        )

    user_content = _build_user_payload(
        nodes=nodes,
        full_text=full_text,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
        max_chars=cfg.extract_max_input_chars,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    started_at = time.perf_counter()
    try:
        result = await ainvoke_structured(
            client,
            ExtractedEdgeList,
            messages,
            context={"warnings": []},
        )
    except Exception as exc:
        logger.warning(
            "build_edges_failed",
            extra={"paper_id": paper_id, "paradigm": nodes.paradigm.value, "error": str(exc)},
        )
        raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "build_edges_success",
        extra={
            "paper_id": paper_id,
            "paradigm": nodes.paradigm.value,
            "edge_count": len(result.edges),
            "elapsed_ms": elapsed_ms,
        },
    )
    return result
