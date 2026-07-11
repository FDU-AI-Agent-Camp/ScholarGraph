"""Static Judge JSON snapshot for repeatable mock benchmark tests."""

from __future__ import annotations

import json
from pathlib import Path

from backend.rag.models import JudgeSchema

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "qa_judge_snapshot.json"


def load_qa_judge_snapshot() -> JudgeSchema:
    """Load persisted Judge structured output (no live token cost)."""
    data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return JudgeSchema.model_validate(data)
