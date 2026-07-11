"""LLM-as-a-Judge evaluation helpers for QA benchmark (Phase 4, Track B)."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm.client import LlmClient
from backend.llm.structured_output import ainvoke_structured
from backend.rag.models import QAJudgeResult
from backend.rag.qa_heuristics import HeuristicGuardrailResult

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """\
你是学术 QA 质量评估专家（LLM-as-a-Judge）。请根据金标上下文、模型回答与引用，进行语义裁判。

## 评估维度
1. **factual_consistency** (0.0-1.0): 回答中的事实、数值与逻辑断言与金标 required_patterns / 图谱期望的语义一致程度。
2. **hallucination_detected** (boolean): 回答是否包含与金标矛盾、或完全无依据的编造事实/逻辑断言。
   - 若回答命中 forbidden_patterns，通常应判为 true。
3. **reasoning**: 对上述两项的详细理由。

## 输出格式
只输出 JSON，字段名必须与 schema 完全一致：factual_consistency, hallucination_detected, reasoning。
不要输出 markdown 代码块。"""


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
    return (
        "请评估以下 QA 回答。\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )


def build_dual_track_evaluation(
    guardrails: HeuristicGuardrailResult,
    judge: QAJudgeResult,
) -> dict[str, Any]:
    """Merge Track A (heuristics) and Track B (LLM Judge) into one report block."""
    hallucination_fused = guardrails.forbidden_tripped or judge.hallucination_detected
    hallucination_rate = 1.0 if hallucination_fused else 0.0
    return {
        "faithfulness": {
            "hallucination_rate": hallucination_rate,
            "entailment_rate": round(judge.factual_consistency, 4),
            "semantic_alignment": round(judge.factual_consistency, 4),
        },
        "completeness": {
            "graph_element_recall": round(guardrails.graph_element_recall, 4),
        },
        "directness": {
            "verbosity_rate": 0.0,
            "paradigm_aligned": not guardrails.has_forbidden_patterns,
        },
        "guardrails": guardrails.to_dict(),
        "judge": judge.model_dump(),
        "dual_track": {
            "heuristic_passed": guardrails.passed,
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
    hallucination_rate = 1.0 if guardrails.forbidden_tripped else 0.0
    payload: dict[str, Any] = {
        "faithfulness": {
            "hallucination_rate": hallucination_rate,
            "entailment_rate": 0.0,
            "semantic_alignment": 0.0,
        },
        "completeness": {
            "graph_element_recall": round(guardrails.graph_element_recall, 4),
        },
        "directness": {
            "verbosity_rate": 0.0,
            "paradigm_aligned": not guardrails.has_forbidden_patterns,
        },
        "guardrails": guardrails.to_dict(),
        "dual_track": {
            "heuristic_passed": guardrails.passed,
            "semantic_factual_consistency": None,
            "hallucination_fused": guardrails.forbidden_tripped,
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
) -> QAJudgeResult:
    """Call the Judge model and parse a structured ``QAJudgeResult``."""
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

    if client.is_mock:
        structured = client.chat.with_structured_output(QAJudgeResult)
        return cast(QAJudgeResult, await structured.ainvoke(messages))

    return await ainvoke_structured(client, QAJudgeResult, messages)
