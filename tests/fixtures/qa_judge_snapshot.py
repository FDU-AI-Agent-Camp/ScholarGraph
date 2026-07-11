"""Static Judge JSON snapshot for repeatable mock benchmark tests."""

from __future__ import annotations

import json
from pathlib import Path

from backend.rag.models import JudgeMicroOutput, QAJudgeResult
from backend.rag.qa_judge_aggregate import aggregate_sentence_judgments

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "qa_judge_snapshot.json"


def load_qa_judge_micro_snapshot() -> JudgeMicroOutput:
    """Load persisted Step-1 Judge micro output (no live token cost)."""
    data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return JudgeMicroOutput.model_validate(data)


def load_qa_judge_snapshot() -> QAJudgeResult:
    """Load snapshot micro labels and aggregate to full Track B result."""
    return aggregate_sentence_judgments(load_qa_judge_micro_snapshot().sentence_judgments)
