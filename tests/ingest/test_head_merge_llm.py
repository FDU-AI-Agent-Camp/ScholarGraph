# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Head merge LLM gate: structured output path and optional live cloud probe."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from backend.config import Settings, get_settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.head_merge import IngestHeadLlmOutput, merge_with_llm
from backend.llm.client import reset_llm_client_cache
from langchain_core.messages import HumanMessage, SystemMessage


class _RecordingStructuredRunnable:
    """Captures LLM messages and returns a fixed structured payload."""

    def __init__(self, *, output: IngestHeadLlmOutput) -> None:
        self.output = output
        self.messages: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> IngestHeadLlmOutput:
        self.messages = list(messages)
        return self.output


class _FakeChat:
    def __init__(self, runnable: _RecordingStructuredRunnable) -> None:
        self._runnable = runnable

    def with_structured_output(self, schema: type[Any]) -> _RecordingStructuredRunnable:
        assert schema is IngestHeadLlmOutput
        return self._runnable


class _FakeLlmClient:
    def __init__(self, runnable: _RecordingStructuredRunnable) -> None:
        self.chat = _FakeChat(runnable)
        self.fallback_chat = None
        self.is_mock = False


def _live_head_merge_settings() -> Settings:
    get_settings.cache_clear()
    reset_llm_client_cache()
    return get_settings()


def _has_valid_live_key(settings: Settings) -> bool:
    return settings.is_llm_live and bool(settings.scholargraph_api_key.strip())


@pytest.fixture
def live_head_merge_env(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Load repository ``.env`` for optional live head-merge probes."""
    monkeypatch.delenv("SCHOLARGRAPH_IGNORE_DOTENV", raising=False)
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "0")
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("INGEST_HEAD_LLM_ENABLED", "true")
    settings = _live_head_merge_settings()
    yield settings
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_merge_with_llm_invokes_structured_output_and_maps_fields() -> None:
    snippets = HeadCandidate(
        title="Snippet Title",
        abstract="Snippet abstract",
        keywords="alpha",
        intro="Snippet intro",
        source="pymupdf",
    )
    path_b = HeadCandidate(
        title="Path B Title",
        abstract="Path B abstract",
        keywords="beta",
        intro="Path B intro",
        source="grobid",
    )
    llm_output = IngestHeadLlmOutput(
        title="Path B Title",
        abstract="Path B abstract",
        keywords="beta",
        intro="Path B intro",
    )
    recorder = _RecordingStructuredRunnable(output=llm_output)
    settings = Settings(
        _env_file=None,
        llm_mode="live",
        scholargraph_api_key="unit-test-key",
        ingest_head_llm_enabled=True,
    )

    with patch("backend.ingest.head_merge.get_llm_client", return_value=_FakeLlmClient(recorder)):
        merged = await merge_with_llm(snippets, path_b, is_short=False, settings=settings)

    assert merged.title == "Path B Title"
    assert merged.abstract == "Path B abstract"
    assert merged.keywords == "beta"
    assert merged.intro == "Path B intro"
    assert all(source == "llm" for source in merged.sources.values())

    assert len(recorder.messages) == 2
    assert isinstance(recorder.messages[0], SystemMessage)
    human = recorder.messages[1]
    assert isinstance(human, HumanMessage)
    payload = json.loads(str(human.content))
    assert payload["route"] == "long"
    assert len(payload["candidates"]) == 2
    assert payload["candidates"][0]["label"] == "snippets"
    assert payload["candidates"][1]["label"] == "path_b"


@pytest.mark.asyncio
async def test_merge_with_llm_falls_back_to_rules_on_structured_failure() -> None:
    snippets = HeadCandidate(title="Snippet Only", source="pymupdf")
    path_b = HeadCandidate(title="GROBID Preferred", source="grobid")

    class _FailingStructured:
        async def ainvoke(self, messages: list[Any]) -> IngestHeadLlmOutput:
            raise RuntimeError("structured output unavailable")

    class _FailingChat:
        def with_structured_output(self, schema: type[Any]) -> _FailingStructured:
            return _FailingStructured()

    settings = Settings(
        _env_file=None,
        llm_mode="live",
        scholargraph_api_key="unit-test-key",
        ingest_head_llm_enabled=True,
    )

    class _FailingClient:
        chat = _FailingChat()
        fallback_chat = None
        is_mock = False

    with patch("backend.ingest.head_merge.get_llm_client", return_value=_FailingClient()):
        merged = await merge_with_llm(snippets, path_b, is_short=False, settings=settings)

    assert merged.title == "GROBID Preferred"
    assert merged.sources["title"] == "grobid"


@pytest.mark.asyncio
async def test_merge_with_llm_recovers_from_markdown_fenced_json() -> None:
    """LLM wrapped JSON in ```json fences should be parsed by the shared cleaner."""
    snippets = HeadCandidate(title="Snippet", source="pymupdf")
    path_b = HeadCandidate(title="Path B", source="grobid")
    raw_json = (
        "```json\n"
        '{"title": "Fenced Title", "abstract": "Fenced abstract", "keywords": "", '
        '"intro": "", "conclusion": "", "journal": "", "funding": "", '
        '"affiliation": "", "research_object": "object", "methodology_tool": "tool", '
        '"core_intellectual_contribution": "finding"}\n'
        "```"
    )

    class _JsonInvalidError(Exception):
        def errors(self) -> list[dict[str, Any]]:
            return [{"type": "json_invalid", "input": raw_json}]

    class _FencedStructured:
        async def ainvoke(self, messages: list[Any]) -> IngestHeadLlmOutput:
            raise _JsonInvalidError("json invalid")

    class _FencedChat:
        def with_structured_output(self, schema: type[Any]) -> _FencedStructured:
            return _FencedStructured()

    settings = Settings(
        _env_file=None,
        llm_mode="live",
        scholargraph_api_key="unit-test-key",
        ingest_head_llm_enabled=True,
    )

    class _FencedClient:
        chat = _FencedChat()
        fallback_chat = None
        is_mock = False

    with patch("backend.ingest.head_merge.get_llm_client", return_value=_FencedClient()):
        merged = await merge_with_llm(snippets, path_b, is_short=False, settings=settings)

    assert merged.title == "Fenced Title"
    assert merged.research_object == "object"
    assert merged.methodology_tool == "tool"
    assert merged.core_intellectual_contribution == "finding"
    assert all(source == "llm" for source in merged.sources.values())


@pytest.mark.asyncio
async def test_merge_head_candidates_skips_llm_when_disabled() -> None:
    from backend.ingest.head_merge import merge_head_candidates

    snippets = HeadCandidate(title="Snippet", source="pymupdf")
    path_b = HeadCandidate(title="Path B", source="grobid")
    settings = Settings(
        _env_file=None,
        llm_mode="live",
        scholargraph_api_key="key",
        ingest_head_llm_enabled=False,
    )
    merged = await merge_head_candidates(snippets, path_b, is_short=False, settings=settings)
    assert merged.title == "Path B"
    assert merged.sources["title"] == "grobid"


@pytest.mark.live_head_merge
@pytest.mark.asyncio
async def test_merge_with_llm_live_cloud_returns_structured_head(
    live_head_merge_env: Settings,
) -> None:
    """Optional live probe: requires ``SCHOLARGRAPH_API_KEY`` in repository ``.env``."""
    settings = live_head_merge_env
    if not _has_valid_live_key(settings):
        pytest.skip("SCHOLARGRAPH_API_KEY not configured for live_head_merge")

    snippets = HeadCandidate(
        title="Noisy OCR T1tl3 xx#$%",
        abstract="Short broken abstract.",
        keywords="",
        intro="",
        source="pymupdf",
    )
    path_b = HeadCandidate(
        title="Graph Neural Networks for Materials Science",
        abstract=(
            "This paper presents graph neural network methods for crystal property prediction using benchmark datasets."
        ),
        keywords="graph neural networks, materials science",
        intro="Deep learning has transformed computational materials discovery in recent years.",
        source="grobid",
    )

    merged = await merge_with_llm(snippets, path_b, is_short=False, settings=settings)

    assert merged.title.strip()
    assert merged.abstract.strip()
    assert merged.sources.get("title") == "llm"
    combined = merged.to_classifier_input()
    assert combined.startswith(("Meta-Information:", "Title:"))
    assert "Title:" in combined
    assert "Abstract:" in combined
    title_lower = merged.title.lower()
    abstract_lower = merged.abstract.lower()
    assert (
        "graph" in title_lower
        or "neural" in title_lower
        or "materials" in abstract_lower
        or "crystal" in abstract_lower
    )
