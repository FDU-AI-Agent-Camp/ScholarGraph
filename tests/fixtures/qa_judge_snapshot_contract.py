"""Canonical Judge snapshot input contract for hash-lock drift detection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from backend.rag.qa_judge import JUDGE_SYSTEM_PROMPT, format_judge_user_content
from backend.rag.qa_judge_replay import hash_judge_messages
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

JUDGE_SNAPSHOT_CONTRACT: dict[str, Any] = {
    "question": "STEM F1 是多少？",
    "paradigm": "STEM",
    "answer_text": "F1 达到 15% 在 ImageNet 上验证，引用节点与金标一致。",
    "citations": [{"type": "node", "node_id": "n1"}],
    "gold": {
        "nodes": ["n1"],
        "edges": [],
        "paragraphs": [],
        "required_patterns": ["15%", "ImageNet"],
        "forbidden_patterns": [],
    },
}


def build_judge_messages_for_contract(
    contract: dict[str, Any] | None = None,
) -> list[SystemMessage | HumanMessage]:
    """Build Judge messages exactly as ``invoke_qa_judge`` would for the fixture contract."""
    payload = contract or JUDGE_SNAPSHOT_CONTRACT
    user_content = format_judge_user_content(
        question=str(payload["question"]),
        paradigm=str(payload.get("paradigm")),
        answer_text=str(payload["answer_text"]),
        citations=list(payload.get("citations", [])),
        gold=dict(payload.get("gold", {})),
    )
    return [
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]


def compute_contract_prompt_sha256(contract: dict[str, Any] | None = None) -> str:
    """SHA-256 hash lock for the committed Judge snapshot contract."""
    return hash_judge_messages(build_judge_messages_for_contract(contract))


def assert_messages_match_contract_hash(
    messages: Sequence[BaseMessage],
    expected_sha256: str,
) -> None:
    current = hash_judge_messages(messages)
    if current != expected_sha256:
        raise AssertionError(
            f"Judge snapshot prompt hash drift: expected={expected_sha256}, current={current}",
        )
