"""Tests for LLM-as-a-Judge QA evaluation (B1 fix)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from backend.llm.client import get_judge_llm_client, get_qa_llm_client, reset_llm_client_cache
from backend.rag.models import QAJudgeResult
from backend.rag.qa_heuristics import run_heuristic_guardrails
from backend.rag.qa_judge import (
    build_dual_track_evaluation,
    compute_mean_hallucination_rate,
    compute_question_hallucination_rate,
    format_judge_user_content,
    hallucination_ci_pass,
    invoke_qa_judge,
)
from tests.conftest import REPO_ROOT

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa"] = module
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


def test_qa_judge_result_schema_validation() -> None:
    result = QAJudgeResult(
        factual_consistency=0.9,
        hallucination_detected=False,
        reasoning="Facts align with gold patterns.",
    )
    assert result.factual_consistency == 0.9
    assert result.hallucination_detected is False


def test_hallucination_matrix_or_logic() -> None:
    assert compute_question_hallucination_rate(heuristic_forbidden_hit=False, llm_judge_detected=False) == 0.0
    assert compute_question_hallucination_rate(heuristic_forbidden_hit=True, llm_judge_detected=False) == 1.0
    assert compute_question_hallucination_rate(heuristic_forbidden_hit=False, llm_judge_detected=True) == 1.0
    assert compute_question_hallucination_rate(heuristic_forbidden_hit=True, llm_judge_detected=True) == 1.0


def test_mean_hallucination_rate_ci_gate_requires_strict_zero() -> None:
    assert compute_mean_hallucination_rate([0.0, 0.0, 0.0]) == 0.0
    assert hallucination_ci_pass(0.0) is True
    assert compute_mean_hallucination_rate([0.0, 1.0, 0.0]) == pytest.approx(1 / 3)
    assert hallucination_ci_pass(1 / 3) is False


def test_format_judge_user_content_includes_gold_payload() -> None:
    content = format_judge_user_content(
        question="论文做了什么？",
        paradigm="HSS",
        answer_text="核心论点[CITE:n1]",
        citations=[{"type": "node", "node_id": "n1"}],
        gold={
            "nodes": ["n1"],
            "edges": [],
            "required_patterns": ["核心论点"],
            "forbidden_patterns": ["PCR"],
        },
    )
    assert "论文做了什么？" in content
    assert "required_patterns" in content
    assert "PCR" in content


@pytest.mark.asyncio
async def test_invoke_qa_judge_mock_returns_structured_result() -> None:
    judge_client = get_judge_llm_client()
    result = await invoke_qa_judge(
        judge_client,
        question="这篇论文做了什么？",
        paradigm="HSS",
        answer_text="关于制度路径依赖的核心论点[CITE:n1]",
        citations=[{"type": "node", "node_id": "n1"}],
        gold={
            "nodes": ["n1"],
            "edges": [],
            "required_patterns": ["核心论点", "制度"],
            "forbidden_patterns": ["PCR"],
        },
    )
    assert isinstance(result, QAJudgeResult)
    assert result.factual_consistency >= 0.5
    assert result.hallucination_detected is False
    assert result.reasoning


def test_build_dual_track_fuses_forbidden_and_judge_hallucination() -> None:
    guardrails = run_heuristic_guardrails(
        "包含 PCR",
        [],
        {"required_patterns": [], "forbidden_patterns": ["PCR"], "nodes": [], "edges": []},
    )
    judge = QAJudgeResult(
        factual_consistency=0.2,
        hallucination_detected=True,
        reasoning="Forbidden pattern detected.",
    )
    evaluation = build_dual_track_evaluation(guardrails, judge)
    assert evaluation["faithfulness"]["hallucination_rate"] == 1.0
    assert evaluation["faithfulness"]["semantic_alignment"] == 0.2
    assert evaluation["dual_track"]["heuristic_passed"] is False
    assert evaluation["guardrails"]["forbidden_tripped"] is True


@pytest.mark.asyncio
async def test_run_full_eval_uses_judge_client(benchmark_qa_module, tmp_path: Path) -> None:
    mod = benchmark_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    mod.seed_m2_qa_graph(graph_dir)
    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)

    from backend.config import get_settings

    get_settings.cache_clear()
    reset_llm_client_cache()

    item = {
        "question": "这篇论文做了什么？请给出核心论点总览。",
        "paradigm": "HSS",
        "paper_id": "hss-001",
        "gold": {
            "nodes": ["n1"],
            "edges": [],
            "required_patterns": ["核心论点"],
            "forbidden_patterns": ["PCR"],
        },
    }
    judge_client = get_judge_llm_client()
    result = await mod.run_full_eval(
        item,
        paper_id="hss-001",
        qa_client=get_qa_llm_client(),
        judge_client=judge_client,
    )

    assert result["error_code"] is None
    assert result["answer_length"] > 0
    assert "evaluation" in result
    assert "judge" in result["evaluation"]
    assert "guardrails" in result["evaluation"]
    assert "dual_track" in result["evaluation"]
    assert result["evaluation"]["faithfulness"]["semantic_alignment"] >= 0.0
    assert result["judge_error"] is None


@pytest.mark.asyncio
async def test_run_full_eval_detects_forbidden_via_dual_track(benchmark_qa_module) -> None:
    mod = benchmark_qa_module
    judge_client = get_judge_llm_client()

    item = {
        "question": "test",
        "paradigm": "HSS",
        "gold": {
            "nodes": [],
            "edges": [],
            "required_patterns": [],
            "forbidden_patterns": ["PCR"],
        },
    }

    class _FakeQaResult:
        question = "test"
        paper_id = "hss-001"
        answer_text = "回答包含 PCR 编造内容"
        citations: list[dict] = []
        error_code = None
        elapsed_ms = 1

    async def _fake_run_single_qa(_paper_id: str, _question: str, **_kwargs: object) -> object:
        return _FakeQaResult()

    mod.run_single_qa = _fake_run_single_qa  # type: ignore[method-assign]
    result = await mod.run_full_eval(
        item,
        paper_id="hss-001",
        qa_client=get_qa_llm_client(),
        judge_client=judge_client,
    )

    assert result["evaluation"]["faithfulness"]["hallucination_rate"] == 1.0
    assert result["evaluation"]["dual_track"]["forbidden_tripped"] is True


@pytest.mark.asyncio
async def test_benchmark_full_eval_mock_repeatable(benchmark_qa_module, tmp_path: Path) -> None:
    mod = benchmark_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    mod.seed_m2_qa_graph(graph_dir)

    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "test",
                "allowed_recall_floor": 0.5,
                "items": [
                    {
                        "question": "这篇论文做了什么？请给出核心论点总览。",
                        "paradigm": "HSS",
                        "paper_id": "hss-001",
                        "scale": "summary",
                        "gold": {
                            "nodes": ["n1"],
                            "edges": [],
                            "paragraphs": [],
                            "required_patterns": ["核心论点"],
                            "forbidden_patterns": ["PCR"],
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = mod.parse_args(
        [
            "--golden-file",
            str(golden_path),
            "--graph-dir",
            str(graph_dir),
            "--concurrency",
            "1",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )
    exit_code = await mod.run_benchmark(args)
    assert exit_code == mod.EXIT_SUCCESS

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["total_questions"] == 1
    assert report["results"][0]["evaluation"]["judge"]["reasoning"]
    assert report["summary"]["mean_hallucination_rate"] == 0.0
    assert report["summary"]["hallucination_pass"] is True
    assert "mean_semantic_alignment" in report["summary"]
