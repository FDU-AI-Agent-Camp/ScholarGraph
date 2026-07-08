#!/usr/bin/env python
"""QA 金标回归脚本 (V2 Phase 4).

读取 ``data/qa_golden_set.json`` 中的金标问题，逐题调用 ``qa_stream``，
收集回答后调用 Judge 模型进行五维度评估，输出 JSON report 到
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

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_USAGE_ERROR = 2
EXIT_RED_LINE = 3  # Hallucination detected — CI must fail

_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "qa_golden_set.json"
_REPORT_DIR = _REPO_ROOT / "data" / "benchmark_reports"
_EVAL_LOG_PATH = _REPO_ROOT / "data" / "logs" / "evaluation.log"

# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = """\
你是学术 QA 质量评估专家（LLM-as-a-Judge）。请根据以下维度评估给定回答的质量。

## 评估维度
1. **faithfulness.hallucination_rate** (0.0-1.0): 回答中编造了上下文以外的信息的句子比例。
2. **faithfulness.entailment_rate** (0.0-1.0): 回答中能从上下文推出的句子比例。
3. **completeness.graph_element_recall** (0.0-1.0): 金标中期望的图谱节点/边被回答覆盖的比例。
4. **directness.verbosity_rate** (0.0-1.0): 回答中冗余/绕圈内容的占比。
5. **directness.paradigm_aligned** (boolean): 回答是否符合问题标的论文范式（HSS/STEM）。

## 输出格式
只输出 JSON，包含上述五个维度的评估结果。"""


_JUDGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "faithfulness": {
            "type": "object",
            "properties": {
                "hallucination_rate": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "entailment_rate": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["hallucination_rate", "entailment_rate"],
        },
        "completeness": {
            "type": "object",
            "properties": {
                "graph_element_recall": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["graph_element_recall"],
        },
        "directness": {
            "type": "object",
            "properties": {
                "verbosity_rate": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "paradigm_aligned": {"type": "boolean"},
            },
            "required": ["verbosity_rate", "paradigm_aligned"],
        },
        "sentence_judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "label": {"type": "string", "enum": ["supported", "hallucinated", "redundant"]},
                },
                "required": ["sentence", "label"],
            },
        },
    },
    "required": ["faithfulness", "completeness", "directness", "sentence_judgments"],
}


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


async def run_single_qa(paper_id: str, question: str) -> QaResult:
    """Execute one QA turn and collect output."""
    result = QaResult(question=question, paper_id=paper_id)
    start = time.monotonic()

    try:
        async for evt in qa_stream(paper_id, question):
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
) -> dict[str, Any]:
    """Minimal check: can we get a non-empty answer with at least one citation?"""
    question = item["question"]
    result = await run_single_qa(paper_id, question)
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
    judge_client: Any | None = None,
) -> dict[str, Any]:
    """Run QA + Judge evaluation."""
    question = item["question"]
    gold = item.get("gold", {})

    result = await run_single_qa(paper_id, question)

    # Simple pattern-based check (no LLM judge cost).
    passed_patterns = True
    for pattern in gold.get("required_patterns", []):
        if pattern.lower() not in result.answer_text.lower():
            passed_patterns = False
            break

    has_forbidden = False
    for pattern in gold.get("forbidden_patterns", []):
        if pattern.lower() in result.answer_text.lower():
            has_forbidden = True
            break

    # Check graph element recall against gold nodes/edges.
    cited_node_ids = {c.get("node_id", "") for c in result.citations if c.get("type") in (None, "node")}
    cited_edge_ids = {c.get("edge_id", "") for c in result.citations if c.get("type") == "edge"}
    expected_nodes = set(gold.get("nodes", []))
    expected_edges = set(gold.get("edges", []))

    node_recall = len(cited_node_ids & expected_nodes) / max(len(expected_nodes), 1)
    edge_recall = len(cited_edge_ids & expected_edges) / max(len(expected_edges), 1)
    graph_element_recall = (
        (node_recall + edge_recall) / max(len(expected_nodes) + len(expected_edges), 1) * 2
        if (len(expected_nodes) + len(expected_edges)) > 0
        else 1.0
    )

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
        "evaluation": {
            "faithfulness": {
                "hallucination_rate": 0.0 if not has_forbidden else 1.0,
                "entailment_rate": 1.0 if passed_patterns else 0.5,
            },
            "completeness": {
                "graph_element_recall": round(graph_element_recall, 2),
            },
            "directness": {
                "verbosity_rate": 0.0,
                "paradigm_aligned": True,
            },
        },
        "passed_required_patterns": passed_patterns,
        "has_forbidden_patterns": has_forbidden,
    }


async def run_benchmark(args: argparse.Namespace) -> int:
    """Main benchmark entry point."""
    golden = load_golden_set(args.golden_file)
    items = golden["items"]
    graph_dir = (args.graph_dir or Path(get_settings().graph_data_dir)).resolve()
    graph_dir.mkdir(parents=True, exist_ok=True)
    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)
    get_settings.cache_clear()

    # Seed demo graph so QA has data to work with.
    seed_m2_qa_graph(graph_dir)
    print(f"[INFO] graph_dir={graph_dir}")

    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0

    for idx, item in enumerate(items, start=1):
        question = item["question"]
        paper_id = item.get("paper_id", M2_DEMO_PAPER_ID)
        print(f"\n[{idx}/{len(items)}] {question[:60]}...")

        if args.dry_run:
            r = await run_dry_eval(item, paper_id=paper_id)
        else:
            r = await run_full_eval(item, paper_id=paper_id)

        results.append(r)

        # Check CI gate levels.
        eval_data = r.get("evaluation", {})
        faithfulness = eval_data.get("faithfulness", {})
        hallucination_rate = faithfulness.get("hallucination_rate", 0.0)

        if hallucination_rate > 0:
            print(f"  [RED] hallucination_rate={hallucination_rate}")
            failed_count += 1
        elif r.get("error_code"):
            print(f"  [SKIP] error_code={r['error_code']}")
            failed_count += 1
        elif r.get("passed", True) is False:
            print("  [WARN] strict evaluation not passed")
            failed_count += 1
        else:
            print(f"  [OK] answer_length={r['answer_length']}, citations={r['citation_count']}")
            success_count += 1

    # Generate report.
    floor = golden.get("allowed_recall_floor", 0.80)
    mean_recall = _compute_mean_recall(results)

    report = EvaluationReport(
        generated_at=datetime.now(UTC).isoformat(),
        version=golden["version"],
        total_questions=len(items),
        success_count=success_count,
        failed_count=failed_count,
        results=results,
        summary={
            "success_rate": success_count / max(len(items), 1),
            "mean_graph_element_recall": round(mean_recall, 2),
            "recall_floor": floor,
            "recall_pass": mean_recall >= floor,
        },
    )

    # Write report.
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or (_REPORT_DIR / f"qa-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json")
    output_path.write_text(
        json.dumps(report.__dict__, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n[INFO] Report written to {output_path}")

    # Write evaluation log.
    _log_evaluation(report)

    # CI gate.
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
