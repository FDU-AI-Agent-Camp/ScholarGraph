#!/usr/bin/env python
"""QA 金标回归脚本 (V2 Phase 4).

读取 ``data/qa_golden_set.json`` 中的金标问题，逐题调用 ``qa_stream``，
收集回答后调用 Judge 模型进行结构化评估，输出 JSON report 到
``data/benchmark_reports/qa-{timestamp}.json``。

Usage (from repo root)::

    uv run python scripts/benchmark_qa.py
    uv run python scripts/benchmark_qa.py --dry-run
    uv run python scripts/benchmark_qa.py --output report.json

``--dry-run`` skips Judge evaluation and only validates question → answer
completeness (no LLM cost).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import get_settings  # noqa: E402
from backend.graph.qa import qa_stream  # noqa: E402
from backend.graph.qa_samples import M2_DEMO_PAPER_ID, seed_m2_qa_graph  # noqa: E402
from backend.llm.client import (  # noqa: E402
    LlmClient,
    get_judge_llm_client,
    get_qa_llm_client,
    reset_llm_client_cache,
)
from backend.llm.roles import clients_are_isolated  # noqa: E402
from backend.rag.qa_heuristics import run_heuristic_guardrails
from backend.rag.qa_judge import (
    build_dual_track_evaluation,
    build_evaluation_fallback,
    invoke_qa_judge,
)  # noqa: E402

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_USAGE_ERROR = 2
EXIT_RED_LINE = 3  # Hallucination detected — CI must fail

_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "qa_golden_set.json"
_REPORT_DIR = _REPO_ROOT / "data" / "benchmark_reports"
_EVAL_LOG_PATH = _REPO_ROOT / "data" / "logs" / "evaluation.log"
_DEFAULT_JUDGE_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class QaResult:
    """Collected QA turn output."""

    question: str
    paper_id: str
    answer_text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    elapsed_ms: int = 0


@dataclass
class EvaluationReport:
    """Aggregated benchmark report."""

    generated_at: str
    version: str
    total_questions: int
    success_count: int
    failed_count: int
    results: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph QA 金标回归 (V2 Phase 4)")
    parser.add_argument(
        "--golden-file",
        type=Path,
        default=_GOLDEN_SET_PATH,
        help="金标问题集路径 (default: data/qa_golden_set.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 report 路径（默认自动生成时间戳路径）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="跳过 Judge 评估，仅验证 QA 调用完整性",
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=None,
        help="图谱目录（默认 GRAPH_DATA_DIR env）",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_DEFAULT_JUDGE_CONCURRENCY,
        help=f"并行评估并发数 (default: {_DEFAULT_JUDGE_CONCURRENCY})",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def load_golden_set(path: Path) -> dict[str, Any]:
    """Load and validate the golden QA set."""
    if not path.is_file():
        print(f"[ERROR] 金标文件不存在: {path}", file=sys.stderr)
        sys.exit(EXIT_USAGE_ERROR)
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not isinstance(items, list) or len(items) == 0:
        print("[ERROR] 金标文件中 items 为空", file=sys.stderr)
        sys.exit(EXIT_USAGE_ERROR)
    print(f"[INFO] 加载 {len(items)} 个金标问题 (version={data.get('version', '?')})")
    return data


async def run_single_qa(
    paper_id: str,
    question: str,
    *,
    qa_client: LlmClient | None = None,
) -> QaResult:
    """Execute one QA turn via the Generator client and collect SSE output."""
    result = QaResult(question=question, paper_id=paper_id)
    start = time.monotonic()

    try:
        async for evt in qa_stream(paper_id, question, llm=qa_client):
            if evt.event == "message":
                result = QaResult(
                    question=question,
                    paper_id=paper_id,
                    answer_text=result.answer_text + evt.data.get("delta", ""),
                    citations=result.citations,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                )
            elif evt.event == "citation":
                result.citations.append(evt.data)
            elif evt.event == "error":
                result = QaResult(
                    question=question,
                    paper_id=paper_id,
                    answer_text=result.answer_text,
                    citations=result.citations,
                    error_code=evt.data.get("code"),
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                )
    except Exception as exc:
        result = QaResult(
            question=question,
            paper_id=paper_id,
            answer_text=result.answer_text,
            citations=result.citations,
            error_code=f"EXCEPTION: {exc}",
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

    return result


async def run_dry_eval(
    item: dict[str, Any],
    *,
    paper_id: str,
    qa_client: LlmClient | None = None,
) -> dict[str, Any]:
    """Minimal check: can we get a non-empty answer with at least one citation?"""
    question = item["question"]
    result = await run_single_qa(paper_id, question, qa_client=qa_client)
    return {
        "question": question,
        "paper_id": paper_id,
        "paradigm": item.get("paradigm"),
        "answer_length": len(result.answer_text),
        "citation_count": len(result.citations),
        "error_code": result.error_code,
        "elapsed_ms": result.elapsed_ms,
        "passed": (result.error_code is None and len(result.answer_text) > 0),
    }


async def run_full_eval(
    item: dict[str, Any],
    *,
    paper_id: str,
    qa_client: LlmClient,
    judge_client: LlmClient,
) -> dict[str, Any]:
    """Run QA (Generator) then dual-track heuristic + Judge evaluation."""
    question = item["question"]
    gold = item.get("gold", {})

    result = await run_single_qa(paper_id, question, qa_client=qa_client)
    guardrails = run_heuristic_guardrails(result.answer_text, result.citations, gold)

    judge_elapsed_ms = 0
    judge_error: str | None = None
    evaluation: dict[str, Any] = {}

    if result.error_code is None and result.answer_text.strip():
        judge_start = time.monotonic()
        try:
            judge_result = await invoke_qa_judge(
                judge_client,
                question=question,
                paradigm=item.get("paradigm"),
                answer_text=result.answer_text,
                citations=result.citations,
                gold=gold,
                guardrails=guardrails,
            )
            evaluation = build_dual_track_evaluation(guardrails, judge_result)
        except Exception as exc:
            judge_error = str(exc)
            logger.exception("judge_eval_failed question=%s", question[:80])
            evaluation = build_evaluation_fallback(guardrails, judge_error=judge_error)
        judge_elapsed_ms = int((time.monotonic() - judge_start) * 1000)
    else:
        evaluation = build_evaluation_fallback(guardrails)
        evaluation["skipped_judge"] = True

    return {
        "question": question,
        "paper_id": paper_id,
        "paradigm": item.get("paradigm"),
        "answer_text": result.answer_text,
        "answer_length": len(result.answer_text),
        "citation_count": len(result.citations),
        "citations": result.citations,
        "error_code": result.error_code,
        "elapsed_ms": result.elapsed_ms,
        "judge_elapsed_ms": judge_elapsed_ms,
        "judge_error": judge_error,
        "evaluation": evaluation,
        "passed_required_patterns": guardrails.passed_required_patterns,
        "has_forbidden_patterns": guardrails.has_forbidden_patterns,
        "guardrails_passed": guardrails.passed,
    }


async def _eval_item_with_semaphore(
    semaphore: asyncio.Semaphore,
    item: dict[str, Any],
    *,
    paper_id: str,
    qa_client: LlmClient | None,
    judge_client: LlmClient | None,
    dry_run: bool,
) -> dict[str, Any]:
    async with semaphore:
        if dry_run:
            return await run_dry_eval(item, paper_id=paper_id, qa_client=qa_client)
        assert qa_client is not None and judge_client is not None
        return await run_full_eval(
            item,
            paper_id=paper_id,
            qa_client=qa_client,
            judge_client=judge_client,
        )


def _log_dual_model_bindings(qa_client: LlmClient, judge_client: LlmClient) -> bool:
    """Print Generator/Judge bindings and return whether they are isolated."""
    settings = get_settings()
    isolated = clients_are_isolated(qa_client, judge_client)
    print(
        f"[INFO] Generator (QA): model={settings.qa_model_effective}, "
        f"endpoint={qa_client.api_base_url or '(default)'}, role={qa_client.role}",
    )
    print(
        f"[INFO] Judge: model={settings.judge_model_effective}, "
        f"endpoint={judge_client.api_base_url or '(default)'}, role={judge_client.role}",
    )
    if settings.is_llm_live and not isolated:
        print(
            "[WARN] QA 与 Judge 共享相同 model/endpoint/key — "
            "建议配置 LLM_MODEL_QA / LLM_MODEL_JUDGE 及独立 QA_API_KEY / JUDGE_API_KEY。",
        )
    else:
        print(f"[INFO] Generator/Judge isolated={isolated}")
    return isolated


async def run_benchmark(args: argparse.Namespace) -> int:
    """Main benchmark entry point."""
    golden = load_golden_set(args.golden_file)
    items = golden["items"]
    graph_dir = (args.graph_dir or Path(get_settings().graph_data_dir)).resolve()
    graph_dir.mkdir(parents=True, exist_ok=True)
    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)
    get_settings.cache_clear()
    reset_llm_client_cache()

    seed_m2_qa_graph(graph_dir)
    print(f"[INFO] graph_dir={graph_dir}")

    qa_client = get_qa_llm_client()
    judge_client: LlmClient | None = None
    clients_isolated = True
    if not args.dry_run:
        judge_client = get_judge_llm_client()
        clients_isolated = _log_dual_model_bindings(qa_client, judge_client)
        settings = get_settings()
        print(
            f"[INFO] Judge timeout={settings.judge_timeout_seconds}s, "
            f"concurrency={args.concurrency}",
        )
    else:
        settings = get_settings()
        print(
            f"[INFO] Generator (QA): model={settings.qa_model_effective} "
            f"(dry-run — Judge skipped)",
        )

    semaphore = asyncio.Semaphore(max(args.concurrency, 1))
    tasks = [
        _eval_item_with_semaphore(
            semaphore,
            item,
            paper_id=item.get("paper_id", M2_DEMO_PAPER_ID),
            qa_client=qa_client,
            judge_client=judge_client,
            dry_run=args.dry_run,
        )
        for item in items
    ]
    results = await asyncio.gather(*tasks)

    success_count = 0
    failed_count = 0
    for idx, (item, r) in enumerate(zip(items, results, strict=True), start=1):
        question = item["question"]
        print(f"\n[{idx}/{len(items)}] {question[:60]}...")

        eval_data = r.get("evaluation", {})
        faithfulness = eval_data.get("faithfulness", {})
        hallucination_rate = faithfulness.get("hallucination_rate", 0.0)
        semantic_alignment = faithfulness.get("semantic_alignment", faithfulness.get("entailment_rate", 0.0))

        if hallucination_rate > 0:
            print(f"  [RED] hallucination_rate={hallucination_rate}")
            failed_count += 1
        elif r.get("error_code"):
            print(f"  [SKIP] error_code={r['error_code']}")
            failed_count += 1
        elif r.get("judge_error"):
            print(f"  [FAIL] judge_error={r['judge_error']}")
            failed_count += 1
        elif r.get("guardrails_passed", r.get("evaluation", {}).get("guardrails", {}).get("passed", True)) is False:
            print("  [WARN] heuristic guardrails not passed")
            failed_count += 1
        else:
            alignment_suffix = ""
            if eval_data:
                alignment_suffix = f", semantic_alignment={semantic_alignment}"
            print(
                f"  [OK] answer_length={r['answer_length']}, citations={r['citation_count']}{alignment_suffix}",
            )
            success_count += 1

    floor = golden.get("allowed_recall_floor", 0.80)
    mean_recall = _compute_mean_recall(results)
    mean_semantic_alignment = _compute_mean_semantic_alignment(results)

    report = EvaluationReport(
        generated_at=datetime.now(UTC).isoformat(),
        version=golden["version"],
        total_questions=len(items),
        success_count=success_count,
        failed_count=failed_count,
        results=list(results),
        summary={
            "success_rate": success_count / max(len(items), 1),
            "mean_graph_element_recall": round(mean_recall, 2),
            "mean_semantic_alignment": round(mean_semantic_alignment, 2),
            "recall_floor": floor,
            "recall_pass": mean_recall >= floor,
            "qa_model": get_settings().qa_model_effective,
            "judge_model": get_settings().judge_model_effective if not args.dry_run else None,
            "clients_isolated": clients_isolated if not args.dry_run else None,
        },
    )

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or (_REPORT_DIR / f"qa-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json")
    output_path.write_text(
        json.dumps(report.__dict__, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n[INFO] Report written to {output_path}")

    _log_evaluation(report)

    if any(r.get("evaluation", {}).get("faithfulness", {}).get("hallucination_rate", 0) > 0 for r in results):
        print("\n[FAIL] RED LINE: Hallucination detected — CI must block merge.")
        return EXIT_RED_LINE

    print(f"\n[OK] Success: {success_count}/{len(items)}")
    return EXIT_SUCCESS


def _compute_mean_recall(results: list[dict[str, Any]]) -> float:
    recals = [r.get("evaluation", {}).get("completeness", {}).get("graph_element_recall", 0.0) for r in results]
    if not recals:
        return 0.0
    return sum(recals) / len(recals)


def _compute_mean_semantic_alignment(results: list[dict[str, Any]]) -> float:
    alignments = [
        r.get("evaluation", {})
        .get("faithfulness", {})
        .get("semantic_alignment", r.get("evaluation", {}).get("faithfulness", {}).get("entailment_rate", 0.0))
        for r in results
    ]
    if not alignments:
        return 0.0
    return sum(alignments) / len(alignments)


def _log_evaluation(report: EvaluationReport) -> None:
    """Append a summary line to the evaluation log."""
    _EVAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": report.generated_at,
        "version": report.version,
        "total": report.total_questions,
        "success": report.success_count,
        "failed": report.failed_count,
        "summary": report.summary,
    }
    with open(_EVAL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    raise SystemExit(main())
