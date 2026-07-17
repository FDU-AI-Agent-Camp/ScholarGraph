# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""LLM-as-a-Judge evaluation helpers for QA benchmark (Phase 4, Track B)."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm.client import LlmClient
from backend.rag.models import JudgeMicroOutput, TrackBJudgeSchema
from backend.rag.qa_heuristics import HeuristicGuardrailResult, is_heuristic_hard_fuse_tripped
from backend.rag.qa_judge_replay import maybe_record_judge, try_replay_judge
from backend.rag.qa_judge_retry import run_with_judge_retry
from backend.rag.qa_judge_structured import invoke_judge_structured_output
from backend.rag.qa_judge_validate import resolve_judge_output

logger = logging.getLogger(__name__)

HALLUCINATION_RATE_CLEAR = 0.0
HALLUCINATION_RATE_TRIGGERED = 1.0


def compute_question_hallucination_rate(
    *,
    heuristic_hard_fuse_hit: bool,
    llm_judge_detected: bool,
) -> float:
    """Dual-track OR matrix: Final = TrackAHardFuse ∨ JudgeDetected → 0% or 100%."""
    if heuristic_hard_fuse_hit or llm_judge_detected:
        return HALLUCINATION_RATE_TRIGGERED
    return HALLUCINATION_RATE_CLEAR


def compute_mean_hallucination_rate(per_question_rates: list[float]) -> float:
    """Arithmetic mean of per-question hallucination rates over the golden set."""
    if not per_question_rates:
        return HALLUCINATION_RATE_CLEAR
    return sum(per_question_rates) / len(per_question_rates)


def hallucination_ci_pass(mean_rate: float) -> bool:
    """CI red-line: mean hallucination rate must be strictly 0%."""
    return mean_rate == HALLUCINATION_RATE_CLEAR


JUDGE_SYSTEM_PROMPT = """\
你是学术 QA 质量评估专家（LLM-as-a-Judge）。采用**自底向上（Bottom-Up）**评估：
先逐句标注，宏观指标由系统根据你的标注自动汇总。

## Step 1 — 句子切片与逐句标注（你唯一需要输出的内容）
1. 将 `answer_text` 切分为完整句子（保留原句文本，不要改写）。
2. 对每个句子给出 `label`：
   - **supported**：事实/数值/逻辑断言与金标 required_patterns、图谱期望、引用上下文一致。
   - **hallucinated**：与金标矛盾、命中 forbidden_patterns、或无依据编造。
   - **redundant**：重复、套话、绕圈，不增加有效信息（非幻觉，但冗余）。

## 标注规则（范式补丁）
- **STEM**：缺少金标要求的具体数值或 benchmark/dataset 的句子 → hallucinated。
- **HSS**：仅泛化表述、未体现 required_patterns 制度/论证术语的句子 → hallucinated 或 redundant。
- 若 `heuristic_guardrails.paradigm_aligned` 为 false，与范式相关的 unsupported 断言应标为 hallucinated。

## 禁止
- 不要输出 factual_consistency / hallucination_detected / reasoning — 系统会从 sentence_judgments 自动推导。
- 不要输出 markdown 代码块；只输出 JSON：
  `{"sentence_judgments": [{"sentence": "...", "label": "supported|hallucinated|redundant"}, ...]}`"""


def format_judge_user_content(
    *,
    question: str,
    paradigm: str | None,
    answer_text: str,
    citations: list[dict[str, Any]],
    gold: dict[str, Any],
    guardrails: HeuristicGuardrailResult | None = None,
) -> str:
    """Build the Judge user message with structured gold + answer context."""
    payload: dict[str, Any] = {
        "question": question,
        "paradigm": paradigm,
        "answer_text": answer_text,
        "citations": citations,
        "gold": {
            "nodes": gold.get("nodes", []),
            "edges": gold.get("edges", []),
            "paragraphs": gold.get("paragraphs", []),
            "required_patterns": gold.get("required_patterns", []),
            "forbidden_patterns": gold.get("forbidden_patterns", []),
            "expected_numbers": gold.get("expected_numbers", []),
            "expected_datasets": gold.get("expected_datasets", []),
        },
    }
    if guardrails is not None:
        payload["heuristic_guardrails"] = guardrails.to_dict()
    return f"请评估以下 QA 回答。\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def _evaluation_completeness(guardrails: HeuristicGuardrailResult) -> dict[str, Any]:
    completeness: dict[str, Any] = {
        "graph_element_recall": round(guardrails.graph_element_recall, 4),
    }
    if guardrails.chunk_recall is not None:
        completeness["chunk_recall"] = round(guardrails.chunk_recall, 4)
    return completeness


def build_dual_track_evaluation(
    guardrails: HeuristicGuardrailResult,
    judge: TrackBJudgeSchema,
) -> dict[str, Any]:
    """Merge Track A (heuristics) and Track B (LLM Judge) into one report block."""
    hallucination_rate = compute_question_hallucination_rate(
        heuristic_hard_fuse_hit=is_heuristic_hard_fuse_tripped(guardrails),
        llm_judge_detected=judge.hallucination_detected,
    )
    hallucination_fused = hallucination_rate == HALLUCINATION_RATE_TRIGGERED
    track_a_tripped = is_heuristic_hard_fuse_tripped(guardrails)
    return {
        "faithfulness": {
            "hallucination_rate": hallucination_rate,
            "entailment_rate": round(judge.factual_consistency, 4),
            "semantic_alignment": round(judge.factual_consistency, 4),
        },
        "completeness": _evaluation_completeness(guardrails),
        "directness": {
            "verbosity_rate": round(guardrails.verbosity_rate, 4),
            "paradigm_aligned": guardrails.paradigm_aligned,
        },
        "guardrails": guardrails.to_dict(),
        "judge": judge.model_dump(),
        "dual_track": {
            "heuristic_passed": guardrails.passed,
            "heuristic_hard_fuse_tripped": track_a_tripped,
            "semantic_factual_consistency": round(judge.factual_consistency, 4),
            "hallucination_fused": hallucination_fused,
            "forbidden_tripped": guardrails.forbidden_tripped,
            "judge_hallucination_detected": judge.hallucination_detected,
        },
    }


def build_evaluation_fallback(
    guardrails: HeuristicGuardrailResult,
    *,
    judge_error: str | None = None,
) -> dict[str, Any]:
    """Heuristic-only evaluation when Judge invocation fails."""
    hallucination_rate = compute_question_hallucination_rate(
        heuristic_hard_fuse_hit=is_heuristic_hard_fuse_tripped(guardrails),
        llm_judge_detected=False,
    )
    track_a_tripped = is_heuristic_hard_fuse_tripped(guardrails)
    payload: dict[str, Any] = {
        "faithfulness": {
            "hallucination_rate": hallucination_rate,
            "entailment_rate": 0.0,
            "semantic_alignment": 0.0,
        },
        "completeness": _evaluation_completeness(guardrails),
        "directness": {
            "verbosity_rate": round(guardrails.verbosity_rate, 4),
            "paradigm_aligned": guardrails.paradigm_aligned,
        },
        "guardrails": guardrails.to_dict(),
        "dual_track": {
            "heuristic_passed": guardrails.passed,
            "heuristic_hard_fuse_tripped": track_a_tripped,
            "semantic_factual_consistency": None,
            "hallucination_fused": hallucination_rate == HALLUCINATION_RATE_TRIGGERED,
            "forbidden_tripped": guardrails.forbidden_tripped,
            "judge_hallucination_detected": None,
        },
    }
    if judge_error:
        payload["judge_error"] = judge_error
    return payload


async def invoke_qa_judge(
    client: LlmClient,
    *,
    question: str,
    paradigm: str | None,
    answer_text: str,
    citations: list[dict[str, Any]],
    gold: dict[str, Any],
    guardrails: HeuristicGuardrailResult | None = None,
) -> TrackBJudgeSchema:
    """Run bottom-up Judge: Step 1 micro labels → Step 2 deterministic aggregation."""
    user_content = format_judge_user_content(
        question=question,
        paradigm=paradigm,
        answer_text=answer_text,
        citations=citations,
        gold=gold,
        guardrails=guardrails,
    )
    messages = [
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    replay = try_replay_judge(messages)
    if replay is not None:
        return resolve_judge_output(replay)

    if client.is_mock:
        structured = client.chat.with_structured_output(JudgeMicroOutput)
        micro = cast(JudgeMicroOutput, await structured.ainvoke(messages))
    else:
        micro = await run_with_judge_retry(
            lambda: invoke_judge_structured_output(client, messages, schema=JudgeMicroOutput),
        )

    maybe_record_judge(messages, micro)

    return resolve_judge_output(micro)
