"""Hash-indexed Judge snapshot replay for zero-cost CI (VCR-style contract playback)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage

from backend.rag.models import JudgeMicroOutput

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SNAPSHOT_PATH = _REPO_ROOT / "tests" / "fixtures" / "qa_judge_snapshot_replay.json"
_REPLAY_ENV = "JUDGE_SNAPSHOT_REPLAY"
_RECORD_ENV = "JUDGE_SNAPSHOT_RECORD"
_SNAPSHOT_PATH_ENV = "JUDGE_SNAPSHOT_PATH"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def hash_judge_messages(messages: Sequence[BaseMessage]) -> str:
    """Stable SHA-256 over system + user Judge prompts."""
    parts: list[str] = []
    for message in messages:
        content = getattr(message, "content", "")
        parts.append(str(content).strip())
    payload = "\n---\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JudgeSnapshotStore:
    """Persist and replay Judge micro-output keyed by prompt hash."""

    def __init__(self, path: Path, payload: dict[str, Any]) -> None:
        self._path = path
        self._payload = payload

    @classmethod
    def load(cls, path: Path | None = None) -> JudgeSnapshotStore:
        resolved = path or _resolve_snapshot_path()
        if not resolved.is_file():
            return cls(resolved, {"version": 1, "default_micro": None, "entries": {}})
        data = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {"version": 1, "default_micro": None, "entries": {}}
        data.setdefault("version", 1)
        data.setdefault("entries", {})
        return cls(resolved, data)

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def replay_enabled() -> bool:
        return _env_truthy(_REPLAY_ENV)

    @staticmethod
    def record_enabled() -> bool:
        return _env_truthy(_RECORD_ENV)

    def lookup(self, prompt_hash: str, *, allow_default: bool = True) -> JudgeMicroOutput | None:
        entries = self._payload.get("entries", {})
        if isinstance(entries, dict):
            raw = entries.get(prompt_hash)
            if isinstance(raw, dict):
                return JudgeMicroOutput.model_validate(raw)

        if allow_default:
            default_micro = self._payload.get("default_micro")
            if isinstance(default_micro, dict):
                return JudgeMicroOutput.model_validate(default_micro)
        return None

    def record(self, prompt_hash: str, micro: JudgeMicroOutput) -> None:
        entries = self._payload.setdefault("entries", {})
        if not isinstance(entries, dict):
            entries = {}
            self._payload["entries"] = entries
        entries[prompt_hash] = micro.model_dump()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.info("Recorded Judge snapshot entry hash=%s path=%s", prompt_hash[:12], self._path)


def _resolve_snapshot_path() -> Path:
    override = os.environ.get(_SNAPSHOT_PATH_ENV, "").strip()
    if override:
        return Path(override)
    return _DEFAULT_SNAPSHOT_PATH


def try_replay_judge(messages: Sequence[BaseMessage]) -> JudgeMicroOutput | None:
    """Return replayed micro output when snapshot replay is enabled."""
    if not JudgeSnapshotStore.replay_enabled():
        return None
    store = JudgeSnapshotStore.load()
    prompt_hash = hash_judge_messages(messages)
    replay = store.lookup(prompt_hash, allow_default=True)
    if replay is not None:
        logger.info("Judge snapshot replay hit hash=%s", prompt_hash[:12])
    return replay


def maybe_record_judge(messages: Sequence[BaseMessage], micro: JudgeMicroOutput) -> None:
    """Persist live Judge output when ``JUDGE_SNAPSHOT_RECORD=1``."""
    if not JudgeSnapshotStore.record_enabled():
        return
    store = JudgeSnapshotStore.load()
    prompt_hash = hash_judge_messages(messages)
    store.record(prompt_hash, micro)
