"""LLM gate and rule-based head merge (§2.4)."""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.ingest.head_candidates import HeadCandidate
from backend.llm.client import get_llm_client
from backend.schemas.ingest_head import IngestHead

logger = logging.getLogger(__name__)

HEAD_FIELDS = ("title", "abstract", "keywords", "intro")
MAX_LLM_CANDIDATE_CHARS = 12_000

HEAD_MERGE_SYSTEM_PROMPT = (
    "You merge academic paper header fields from two PDF extraction paths. "
    "For each field, pick the most accurate text from the candidates. "
    "Do NOT invent or paraphrase metadata; use empty string when absent."
)


class IngestHeadLlmOutput(BaseModel):
    """Structured LLM output for head merge (no provenance)."""

    title: str = ""
    abstract: str = ""
    keywords: str = ""
    intro: str = ""


def _candidate_payload(label: str, candidate: HeadCandidate) -> dict[str, str]:
    return {
        "label": label,
        "source": candidate.source,
        "title": candidate.title,
        "abstract": candidate.abstract,
        "keywords": candidate.keywords,
        "intro": candidate.intro,
    }


def _truncate_candidate(candidate: HeadCandidate) -> HeadCandidate:
    def clip(value: str) -> str:
        if len(value) <= MAX_LLM_CANDIDATE_CHARS:
            return value
        return value[:MAX_LLM_CANDIDATE_CHARS].rstrip()

    return HeadCandidate(
        title=clip(candidate.title),
        abstract=clip(candidate.abstract),
        keywords=clip(candidate.keywords),
        intro=clip(candidate.intro),
        source=candidate.source,
    )


def merge_with_rules(
    snippets: HeadCandidate,
    path_b: HeadCandidate | None,
    *,
    is_short: bool,
) -> IngestHead:
    """
    Field-level priority fallback when LLM is disabled or fails.

    Short PDF: MinerU > snippets; long PDF: GROBID > snippets.
    """
    sources: dict[str, str] = {}
    merged: dict[str, str] = {}

    for field in HEAD_FIELDS:
        snippet_value = getattr(snippets, field, "").strip()
        path_b_value = getattr(path_b, field, "").strip() if path_b else ""
        if path_b_value:
            merged[field] = path_b_value
            sources[field] = path_b.source if path_b else "path_b"
        elif snippet_value:
            merged[field] = snippet_value
            sources[field] = snippets.source
        else:
            merged[field] = ""
            sources[field] = "empty"

    _ = is_short
    return IngestHead(
        title=merged["title"],
        abstract=merged["abstract"],
        keywords=merged["keywords"],
        intro=merged["intro"],
        sources=sources,
    )


def _resolve_head_llm_model(settings: Settings) -> str:
    configured = settings.ingest_head_llm_model.strip()
    if configured:
        return configured
    fallback = settings.llm_model_fallback_effective
    if fallback:
        return fallback
    return settings.llm_model_primary


async def merge_with_llm(
    snippets: HeadCandidate,
    path_b: HeadCandidate | None,
    *,
    is_short: bool,
    settings: Settings | None = None,
) -> IngestHead:
    """Call structured LLM merge; fall back to rules on any failure."""
    cfg = settings or get_settings()
    if cfg.is_llm_mock or not cfg.ingest_head_llm_enabled:
        return merge_with_rules(snippets, path_b, is_short=is_short)

    payload = {
        "route": "short" if is_short else "long",
        "candidates": [
            _candidate_payload("snippets", _truncate_candidate(snippets)),
        ],
    }
    if path_b is not None:
        payload["candidates"].append(_candidate_payload("path_b", _truncate_candidate(path_b)))

    messages = [
        SystemMessage(content=HEAD_MERGE_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]

    client = get_llm_client()
    model_name = _resolve_head_llm_model(cfg)
    timeout = cfg.ingest_head_llm_timeout_seconds

    try:
        chat = client.chat
        if model_name != cfg.llm_model_primary and client.fallback_chat is not None:
            chat = client.fallback_chat
        structured = chat.with_structured_output(IngestHeadLlmOutput)
        if hasattr(structured, "ainvoke"):
            result = await structured.ainvoke(messages)
        else:
            result = structured.invoke(messages)  # type: ignore[attr-defined]
        if not isinstance(result, IngestHeadLlmOutput):
            result = IngestHeadLlmOutput.model_validate(result)
        return IngestHead(
            title=result.title.strip(),
            abstract=result.abstract.strip(),
            keywords=result.keywords.strip(),
            intro=result.intro.strip(),
            sources={field: "llm" for field in HEAD_FIELDS},
        )
    except Exception:
        logger.exception("Head merge LLM failed (model=%s, timeout=%ss)", model_name, timeout)
        return merge_with_rules(snippets, path_b, is_short=is_short)


async def merge_head_candidates(
    snippets: HeadCandidate,
    path_b: HeadCandidate | None,
    *,
    is_short: bool,
    mode: Literal["auto", "rules", "llm"] = "auto",
    settings: Settings | None = None,
) -> IngestHead:
    """Merge path-A and path-B candidates using LLM gate with rule fallback."""
    cfg = settings or get_settings()
    if mode == "rules" or cfg.is_llm_mock or not cfg.ingest_head_llm_enabled:
        return merge_with_rules(snippets, path_b, is_short=is_short)
    if mode == "llm":
        return await merge_with_llm(snippets, path_b, is_short=is_short, settings=cfg)
    return await merge_with_llm(snippets, path_b, is_short=is_short, settings=cfg)
