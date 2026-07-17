# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Hash-lock drift tests for committed Judge snapshot fixtures."""

from __future__ import annotations

import json

import pytest
from backend.rag.qa_judge_replay import (
    JudgeSnapshotContractDriftError,
    JudgeSnapshotStore,
    hash_judge_messages,
    try_replay_judge,
)
from langchain_core.messages import HumanMessage, SystemMessage

from tests.fixtures.qa_judge_snapshot import load_snapshot_prompt_sha256
from tests.fixtures.qa_judge_snapshot_contract import (
    JUDGE_SNAPSHOT_CONTRACT,
    build_judge_messages_for_contract,
    compute_contract_prompt_sha256,
)


def test_snapshot_contract_hash_matches_legacy_fixture() -> None:
    current_hash = compute_contract_prompt_sha256()
    fixture_hash = load_snapshot_prompt_sha256()
    assert current_hash == fixture_hash


def test_snapshot_replay_fixture_hash_lock_matches_contract() -> None:
    store = JudgeSnapshotStore.load()
    current_hash = compute_contract_prompt_sha256()
    assert store.contract_prompt_sha256 == current_hash
    store.assert_contract_hash(current_hash)
    replay = store.lookup(current_hash, allow_default=True)
    assert replay is not None
    assert replay.sentence_judgments


def test_snapshot_replay_rejects_stale_hash_without_silent_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_SNAPSHOT_REPLAY", "1")
    stale_messages = [
        SystemMessage(content="mutated-system-prompt"),
        HumanMessage(content="mutated-user-payload"),
    ]
    with pytest.raises(JudgeSnapshotContractDriftError):
        try_replay_judge(stale_messages)


def test_snapshot_hash_lock_fails_when_fixture_hash_mutated(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    drifted_path = tmp_path / "drifted_replay.json"
    current_hash = compute_contract_prompt_sha256()
    payload = {
        "version": 2,
        "prompt_sha256": "0" * 64,
        "default_micro": {
            "sentence_judgments": [
                {"sentence": "stale", "label": "supported"},
            ],
        },
        "entries": {},
    }
    drifted_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    store = JudgeSnapshotStore.load(drifted_path)
    with pytest.raises(JudgeSnapshotContractDriftError):
        store.assert_contract_hash(current_hash)

    assert store.lookup(current_hash, allow_default=True) is None


def test_golden_question_change_changes_prompt_hash() -> None:
    baseline = compute_contract_prompt_sha256()
    mutated_contract = {
        **JUDGE_SNAPSHOT_CONTRACT,
        "question": "STEM F1 是多少？（标点漂移）",
    }
    mutated = compute_contract_prompt_sha256(mutated_contract)
    assert mutated != baseline
    assert hash_judge_messages(build_judge_messages_for_contract()) == baseline
