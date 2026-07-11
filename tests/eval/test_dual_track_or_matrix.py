"""Dual-track OR matrix boundary tests (Track A hard fuse ∨ Track B Judge).

Four boundary states verify the strictest fuse always wins:
  ① A safe  + B clear  → 0%
  ② A tripped + B clear → 100% (rules override LLM miss)
  ③ A safe  + B trip   → 100% (LLM catches semantic hallucination)
  ④ A tripped + B trip → 100%
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest

from backend.llm.client import get_judge_llm_client, get_qa_llm_client, reset_llm_client_cache
from backend.rag.models import QAJudgeResult, SentenceJudgment, SentenceLabel
from backend.rag.qa_heuristics import is_heuristic_hard_fuse_tripped, run_heuristic_guardrails
from backend.rag.qa_judge import build_dual_track_evaluation, compute_question_hallucination_rate
from tests.conftest import REPO_ROOT

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"

_GOLD_STEM = {
    "nodes": ["n1"],
    "edges": [],
    "required_patterns": ["0.89", "ImageNet"],
    "forbidden_patterns": ["PCR"],
}

_GOLD_HSS = {
    "nodes": ["n1"],
    "edges": [],
    "required_patterns": ["核心论点"],
    "forbidden_patterns": ["PCR"],
}


def _judge(*, hallucination_detected: bool, sentence: str = "测试句。") -> QAJudgeResult:
    label = SentenceLabel.HALLUCINATED if hallucination_detected else SentenceLabel.SUPPORTED
    supported = 0.0 if hallucination_detected else 1.0
    return QAJudgeResult(
        sentence_judgments=[SentenceJudgment(sentence=sentence, label=label)],
        factual_consistency=supported,
        hallucination_detected=hallucination_detected,
        reasoning=f"Mock judge: hallucination_detected={hallucination_detected}.",
    )


def _assert_or_matrix_state(
    *,
    state_id: str,
    guardrails: Any,
    judge: QAJudgeResult,
    expected_rate: float,
    track_a_safe: bool,
    track_b_safe: bool,
) -> None:
    """Shared engineering assertions for one OR-matrix boundary state."""
    track_a_tripped = is_heuristic_hard_fuse_tripped(guardrails)
    assert track_a_tripped is (not track_a_safe), f"{state_id}: Track A fuse mismatch"
    assert judge.hallucination_detected is (not track_b_safe), f"{state_id}: Track B fuse mismatch"

    fused_rate = compute_question_hallucination_rate(
        heuristic_hard_fuse_hit=track_a_tripped,
        llm_judge_detected=judge.hallucination_detected,
    )
    assert fused_rate == expected_rate, f"{state_id}: raw OR matrix"

    evaluation = build_dual_track_evaluation(guardrails, judge)
    assert evaluation["faithfulness"]["hallucination_rate"] == expected_rate, f"{state_id}: report rate"
    assert evaluation["dual_track"]["hallucination_fused"] is (expected_rate == 1.0), f"{state_id}: fused flag"
    assert evaluation["dual_track"]["heuristic_hard_fuse_tripped"] is track_a_tripped
    assert evaluation["dual_track"]["judge_hallucination_detected"] == judge.hallucination_detected


@pytest.mark.parametrize(
    ("state_id", "answer_text", "gold", "paradigm", "judge_detected", "expected_rate", "track_a_safe", "track_b_safe"),
    [
        pytest.param(
            "①",
            "实验 F1 达到 0.89，在 ImageNet 上验证。",
            _GOLD_STEM,
            "STEM",
            False,
            0.0,
            True,
            True,
            id="state-1-both-safe",
        ),
        pytest.param(
            "②-forbidden",
            "回答包含 PCR 但未给出数值。",
            _GOLD_HSS,
            "HSS",
            False,
            1.0,
            False,
            True,
            id="state-2a-forbidden-llm-miss",
        ),
        pytest.param(
            "②-numeric",
            "方法描述充分，但未报告 F1 数值。",
            _GOLD_STEM,
            "STEM",
            False,
            1.0,
            False,
            True,
            id="state-2b-numeric-llm-miss",
        ),
        pytest.param(
            "③",
            "论文提出了一种全新的跨模态架构并取得提升。",
            _GOLD_HSS,
            "HSS",
            True,
            1.0,
            True,
            False,
            id="state-3-llm-catch",
        ),
        pytest.param(
            "④",
            "回答包含 PCR 且编造了额外实验结论。",
            _GOLD_HSS,
            "HSS",
            True,
            1.0,
            False,
            False,
            id="state-4-double-fuse",
        ),
    ],
)
def test_dual_track_or_matrix_boundary_states(
    state_id: str,
    answer_text: str,
    gold: dict[str, Any],
    paradigm: str,
    judge_detected: bool,
    expected_rate: float,
    track_a_safe: bool,
    track_b_safe: bool,
) -> None:
    guardrails = run_heuristic_guardrails(
        answer_text,
        [{"type": "node", "node_id": "n1"}],
        gold,
        paradigm=paradigm,
    )
    judge = _judge(hallucination_detected=judge_detected, sentence=answer_text)
    _assert_or_matrix_state(
        state_id=state_id,
        guardrails=guardrails,
        judge=judge,
        expected_rate=expected_rate,
        track_a_safe=track_a_safe,
        track_b_safe=track_b_safe,
    )


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa_or", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa_or"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _mock_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.config import get_settings

    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()
    yield
    get_settings.cache_clear()
    reset_llm_client_cache()


@dataclass
class _FakeQaResult:
    answer_text: str
    citations: list[dict[str, Any]]
    question: str = "boundary test"
    paper_id: str = "hss-001"
    error_code: None = None
    elapsed_ms: int = 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state_id", "answer_text", "gold", "paradigm", "judge_detected", "expected_rate"),
    [
        ("①", "实验 F1 达到 0.89，在 ImageNet 上验证。", _GOLD_STEM, "STEM", False, 0.0),
        ("②", "回答包含 PCR 但未给出数值。", _GOLD_HSS, "HSS", False, 1.0),
        ("③", "论文提出了一种全新的跨模态架构。", _GOLD_HSS, "HSS", True, 1.0),
        ("④", "回答包含 PCR 且编造了额外结论。", _GOLD_HSS, "HSS", True, 1.0),
    ],
)
async def test_run_full_eval_or_matrix_with_forced_qa_and_judge(
    benchmark_qa_module: Any,
    state_id: str,
    answer_text: str,
    gold: dict[str, Any],
    paradigm: str,
    judge_detected: bool,
    expected_rate: float,
) -> None:
    """Integration: forge QA engine answer + Judge verdict, assert fused hallucination_rate."""
    mod = benchmark_qa_module
    os.environ.setdefault("GRAPH_DATA_DIR", str(REPO_ROOT / "data" / "graphs"))

    item = {"question": "boundary", "paradigm": paradigm, "gold": gold}
    fake = _FakeQaResult(answer_text=answer_text, citations=[{"type": "node", "node_id": "n1"}])

    async def _fake_run_single_qa(_paper_id: str, _question: str, **_kwargs: object) -> _FakeQaResult:
        return fake

    async def _fake_invoke_qa_judge(*_args: object, **_kwargs: object) -> QAJudgeResult:
        return _judge(hallucination_detected=judge_detected, sentence=answer_text)

    mod.run_single_qa = _fake_run_single_qa  # type: ignore[method-assign]
    mod.invoke_qa_judge = _fake_invoke_qa_judge  # type: ignore[method-assign]

    result = await mod.run_full_eval(
        item,
        paper_id="hss-001",
        qa_client=get_qa_llm_client(),
        judge_client=get_judge_llm_client(),
    )

    evaluation = result["evaluation"]
    assert evaluation["faithfulness"]["hallucination_rate"] == expected_rate, state_id
    assert evaluation["dual_track"]["hallucination_fused"] is (expected_rate == 1.0), state_id
    assert evaluation["dual_track"]["judge_hallucination_detected"] is judge_detected, state_id

    track_a_tripped = is_heuristic_hard_fuse_tripped(
        run_heuristic_guardrails(fake.answer_text, fake.citations, gold, paradigm=paradigm),
    )
    assert evaluation["dual_track"]["heuristic_hard_fuse_tripped"] is track_a_tripped, state_id
