"""Static Judge JSON snapshot for repeatable mock benchmark tests."""

from __future__ import annotations

import json
from pathlib import Path

from backend.rag.models import JudgeMicroOutput, QAJudgeResult
from backend.rag.qa_judge_aggregate import aggregate_sentence_judgments
from backend.rag.qa_judge_replay import JudgeSnapshotStore
from tests.fixtures.qa_judge_snapshot_contract import (
    assert_messages_match_contract_hash,
    build_judge_messages_for_contract,
    compute_contract_prompt_sha256,
)

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "qa_judge_snapshot.json"
_REPLAY_PATH = Path(__file__).resolve().parent / "qa_judge_snapshot_replay.json"


def load_snapshot_prompt_sha256() -> str:
    """Load committed prompt hash lock from legacy snapshot fixture."""
    data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    prompt_sha256 = data.get("prompt_sha256")
    if not prompt_sha256:
        raise ValueError(f"missing prompt_sha256 in {_SNAPSHOT_PATH}")
    return str(prompt_sha256)


def load_qa_judge_micro_snapshot() -> JudgeMicroOutput:
    """Load persisted Step-1 Judge micro output (no live token cost)."""
    replay_store = JudgeSnapshotStore.load(_REPLAY_PATH)
    contract_hash = compute_contract_prompt_sha256()
    replay_store.assert_contract_hash(contract_hash)
    replay = replay_store.lookup(contract_hash, allow_default=True)
    if replay is not None:
        return replay

    data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    expected_hash = str(data.get("prompt_sha256", "")).strip()
    if expected_hash:
        assert_messages_match_contract_hash(build_judge_messages_for_contract(), expected_hash)
    micro_raw = data.get("micro", data)
    return JudgeMicroOutput.model_validate(micro_raw)


def load_qa_judge_snapshot() -> QAJudgeResult:
    """Load snapshot micro labels and aggregate to full Track B result."""
    return aggregate_sentence_judgments(load_qa_judge_micro_snapshot().sentence_judgments)
