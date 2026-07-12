"""Tests for hash-indexed Judge snapshot replay (VCR-style)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from backend.rag.models import JudgeMicroOutput, SentenceJudgment, SentenceLabel
from backend.rag.qa_judge import format_judge_user_content, invoke_qa_judge
from backend.rag.qa_judge_replay import JudgeSnapshotStore, hash_judge_messages, maybe_record_judge, try_replay_judge
from langchain_core.messages import HumanMessage, SystemMessage

from tests.fixtures.qa_judge_snapshot import load_qa_judge_micro_snapshot


def _sample_messages() -> list[SystemMessage | HumanMessage]:
    user_content = format_judge_user_content(
        question="STEM F1?",
        paradigm="STEM",
        answer_text="F1 达到 15%",
        citations=[],
        gold={"required_patterns": ["15%"], "forbidden_patterns": [], "nodes": [], "edges": []},
    )
    return [
        SystemMessage(content="judge-system"),
        HumanMessage(content=user_content),
    ]


def test_hash_judge_messages_is_stable() -> None:
    messages = _sample_messages()
    assert hash_judge_messages(messages) == hash_judge_messages(messages)


def test_judge_snapshot_store_records_and_replays(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "replay.json"
    store = JudgeSnapshotStore.load(path)
    micro = JudgeMicroOutput(
        sentence_judgments=[SentenceJudgment(sentence="ok", label=SentenceLabel.SUPPORTED)],
    )
    prompt_hash = "abc123"
    store.record(prompt_hash, micro)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert prompt_hash in payload["entries"]

    reloaded = JudgeSnapshotStore.load(path)
    replay = reloaded.lookup(prompt_hash, allow_default=False)
    assert replay == micro


@pytest.mark.asyncio
async def test_invoke_qa_judge_replays_without_live_api(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.config import get_settings
    from backend.llm.client import get_judge_llm_client, reset_llm_client_cache

    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("JUDGE_SNAPSHOT_REPLAY", "1")
    get_settings.cache_clear()
    reset_llm_client_cache()

    expected = load_qa_judge_micro_snapshot()

    with patch("backend.rag.qa_judge.try_replay_judge", return_value=expected):
        with patch("backend.rag.qa_judge.invoke_judge_structured_output", new_callable=AsyncMock) as live_call:
            result = await invoke_qa_judge(
                get_judge_llm_client(),
                question="STEM F1?",
                paradigm="STEM",
                answer_text="F1 达到 15%",
                citations=[],
                gold={"required_patterns": ["15%"], "forbidden_patterns": [], "nodes": [], "edges": []},
            )

    live_call.assert_not_awaited()
    assert result.sentence_judgments


def test_try_replay_judge_uses_default_micro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_SNAPSHOT_REPLAY", "1")
    replay = try_replay_judge(_sample_messages())
    assert replay is not None
    assert replay.sentence_judgments


def test_maybe_record_judge_writes_entry(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "replay.json"
    monkeypatch.setenv("JUDGE_SNAPSHOT_PATH", str(path))
    monkeypatch.setenv("JUDGE_SNAPSHOT_RECORD", "1")

    messages = _sample_messages()
    micro = load_qa_judge_micro_snapshot()
    maybe_record_judge(messages, micro)

    store = JudgeSnapshotStore.load(path)
    replay = store.lookup(hash_judge_messages(messages), allow_default=False)
    assert replay == micro
