#!/usr/bin/env python
"""QA 金标回归脚本 (V2 Phase 4).

读取 ``data/qa_golden_set.json`` 中的金标问题，逐题调用 ``qa_stream``，
收集回答后调用 Judge 模型进行结构化评估，输出 JSON report 到
``data/benchmark_reports/qa-{timestamp}.json``。

并发控制：默认 ``asyncio.Semaphore(3)`` 限制金标评估并发；Judge live 调用
对限流/超时类 transient 错误自动 tenacity 指数退避重试（3 次，2~30s）。

Usage (from repo root)::

    uv run python scripts/benchmark_qa.py
    uv run python scripts/benchmark_qa.py --dry-run
    uv run python scripts/benchmark_qa.py --output report.json

``--dry-run`` skips Judge evaluation and only validates question → answer
completeness (no LLM cost).

Chunk recall gate tiers (``detail_recall_gate.chunk_recall_min``):

- **mock_dry_run** (``LLM_MODE=mock`` or ``--dry-run``): floor **0.5**, enforced.
- **release_strict** (``EVAL_GATE_STRICT_CHUNK=1``): floor **0.7**, enforced.
- **informational** (live full eval without strict env): reported, not CI-blocking.

Judge snapshot replay (optional live Judge CI without token cost):

- ``JUDGE_SNAPSHOT_REPLAY=1`` — replay ``tests/fixtures/qa_judge_snapshot_replay.json`` by prompt SHA-256.
- ``JUDGE_SNAPSHOT_RECORD=1`` — on live Judge calls, persist micro-output into the replay file.
- ``JUDGE_SNAPSHOT_PATH`` — override replay JSON path (default: tests/fixtures/qa_judge_snapshot_replay.json).
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
from backend.graph.qa_samples import M2_DEMO_PAPER_ID, seed_m2_qa_graph, seed_stem_qa_graph  # noqa: E402
from backend.graph.store import GraphStore  # noqa: E402
from backend.llm.client import (  # noqa: E402
    LlmClient,
    get_judge_llm_client,
    get_qa_llm_client,
    reset_llm_client_cache,
)
from backend.llm.roles import clients_are_isolated  # noqa: E402
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever  # noqa: E402
from backend.rag.models import QuestionScale  # noqa: E402
from backend.rag.qa_heuristics import (  # noqa: E402
    chunk_recall_meets_floor,
    resolve_gold_chunk_ids,
    run_heuristic_guardrails,
)
from backend.rag.qa_judge import (  # noqa: E402
    build_dual_track_evaluation,
    build_evaluation_fallback,
    compute_mean_hallucination_rate,
    hallucination_ci_pass,
    invoke_qa_judge,
)
from backend.rag.qa_router import detect_question_scale  # noqa: E402
from backend.schemas.paradigm import Paradigm  # noqa: E402
from backend.services.paper_service import PaperService  # noqa: E402
from backend.services.qa_service import QaService  # noqa: E402

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_USAGE_ERROR = 2
EXIT_RED_LINE = 3  # Hallucination detected — CI must fail

_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "qa_golden_set.json"
_REPORT_DIR = _REPO_ROOT / "data" / "benchmark_reports"
_EVAL_LOG_PATH = _REPO_ROOT / "data" / "logs" / "evaluation.log"
_DEFAULT_BENCHMARK_CONCURRENCY = 3
# Align with docs/v2/rag-requirements.md QA_VERBOSITY_CEILING — yellow warning only, not P0 CI block.
_DEFAULT_QA_VERBOSITY_CEILING = 0.15
_REDUNDANT_SUSPECT_TAG = "REDUNDANT_SUSPECT"
_CHUNK_RECALL_FLOOR_MOCK = 0.5
_CHUNK_RECALL_FLOOR_STRICT = 0.7
_EVAL_GATE_STRICT_CHUNK_ENV = "EVAL_GATE_STRICT_CHUNK"
_RECALL_GATE_DETAIL_SCALES = frozenset({QuestionScale.DETAIL.value, "detail"})
_VECTOR_BRANCH_SCALES = frozenset(
    {QuestionScale.DETAIL.value, QuestionScale.VERIFICATION.value, "detail", "verification"},
)


@dataclass(frozen=True, slots=True)
class ChunkRecallGatePolicy:
    """Multi-tier chunk recall floor — mock/dry-run vs release strict."""

    floor: float
    tier: str
    enforced: bool


@dataclass(frozen=True, slots=True)
class QaResult:
    """Collected QA turn output."""

    question: str
    paper_id: str
    answer_text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    elapsed_ms: int = 0
    ttft_ms: int | None = None
    detected_scale: str | None = None
    gold_scale: str | None = None
    scale_routing_match: bool | None = None
    vector_branch_invoked: bool | None = None


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
    breakdown: list[dict[str, Any]] = field(default_factory=list)


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
        default=_DEFAULT_BENCHMARK_CONCURRENCY,
        help=f"金标评估最大并发数 (Semaphore, default: {_DEFAULT_BENCHMARK_CONCURRENCY})",
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


def _build_benchmark_paper_service() -> PaperService:
    """DB-backed papers aligned with OpenAPI fixtures (includes stem-001 / hss-001)."""
    from backend.repositories.async_bridge import run_async
    from backend.services.paper_fixture_seed import seed_from_fixtures
    from backend.services.paper_service import PaperService

    service = PaperService()
    run_async(seed_from_fixtures(service._paper_repo, service._pipeline_repo))
    return service


def _build_benchmark_qa_service(graph_dir: Path) -> QaService:
    """Wire graph store + optional static mock vectors for reproducible benchmark runs."""
    seed_m2_qa_graph(graph_dir)
    seed_stem_qa_graph(graph_dir)
    store = GraphStore(base_dir=graph_dir)

    settings = get_settings()
    vector_store = None
    if settings.is_llm_mock:
        from backend.rag.static_mock_vector_store import StaticMockVectorStore

        vector_store = StaticMockVectorStore.load_default()
        print(
            f"[INFO] mock vector store: {vector_store.chunk_count()} static chunks "
            "(data/mock_vector_store.json — no Chroma)",
        )

    retriever = HybridRetriever(vector_store=vector_store)
    bind_hybrid_retriever(retriever)
    return QaService(
        store=store,
        hybrid_retriever=retriever,
        paper_service=_build_benchmark_paper_service(),
    )


def _resolve_detected_scale(
    question: str,
    paper_id: str,
    *,
    paradigm: str | None,
) -> QuestionScale:
    parsed_paradigm = Paradigm(paradigm) if paradigm in {p.value for p in Paradigm} else None
    return detect_question_scale(
        question,
        paradigm=parsed_paradigm,
        current_paper_context={"paper_id": paper_id},
    )


def _vector_branch_invoked(scale: QuestionScale) -> bool:
    return scale.value in _VECTOR_BRANCH_SCALES


def _routing_fields(
    item: dict[str, Any],
    paper_id: str,
) -> dict[str, Any]:
    detected = _resolve_detected_scale(
        item["question"],
        paper_id,
        paradigm=item.get("paradigm"),
    )
    gold_scale = str(item.get("scale", ""))
    return {
        "detected_scale": detected.value,
        "gold_scale": gold_scale,
        "scale_routing_match": detected.value == gold_scale,
        "vector_branch_invoked": _vector_branch_invoked(detected),
    }


async def run_single_qa(
    paper_id: str,
    question: str,
    *,
    qa_client: LlmClient | None = None,
    qa_service: QaService | None = None,
    routing_meta: dict[str, Any] | None = None,
) -> QaResult:
    """Execute one QA turn via QaService (hybrid routing) and collect SSE output."""
    meta = routing_meta or {}
    result = QaResult(
        question=question,
        paper_id=paper_id,
        detected_scale=meta.get("detected_scale"),
        gold_scale=meta.get("gold_scale"),
        scale_routing_match=meta.get("scale_routing_match"),
        vector_branch_invoked=meta.get("vector_branch_invoked"),
    )
    start = time.monotonic()
    ttft_ms: int | None = None

    stream = (
        qa_service.stream(paper_id, question, llm=qa_client)
        if qa_service is not None
        else qa_stream(paper_id, question, llm=qa_client)
    )

    try:
        async for evt in stream:
            if evt.event == "message":
                if ttft_ms is None:
                    ttft_ms = int((time.monotonic() - start) * 1000)
                result = QaResult(
                    question=question,
                    paper_id=paper_id,
                    answer_text=result.answer_text + evt.data.get("delta", ""),
                    citations=result.citations,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                    ttft_ms=ttft_ms,
                    detected_scale=result.detected_scale,
                    gold_scale=result.gold_scale,
                    scale_routing_match=result.scale_routing_match,
                    vector_branch_invoked=result.vector_branch_invoked,
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
                    ttft_ms=ttft_ms,
                    detected_scale=result.detected_scale,
                    gold_scale=result.gold_scale,
                    scale_routing_match=result.scale_routing_match,
                    vector_branch_invoked=result.vector_branch_invoked,
                )
    except Exception as exc:
        result = QaResult(
            question=question,
            paper_id=paper_id,
            answer_text=result.answer_text,
            citations=result.citations,
            error_code=f"EXCEPTION: {exc}",
            elapsed_ms=int((time.monotonic() - start) * 1000),
            ttft_ms=ttft_ms,
            detected_scale=result.detected_scale,
            gold_scale=result.gold_scale,
            scale_routing_match=result.scale_routing_match,
            vector_branch_invoked=result.vector_branch_invoked,
        )

    return result


async def run_dry_eval(
    item: dict[str, Any],
    *,
    paper_id: str,
    qa_client: LlmClient | None = None,
    qa_service: QaService | None = None,
) -> dict[str, Any]:
    """Minimal check: can we get a non-empty answer with at least one citation?"""
    question = item["question"]
    routing = _routing_fields(item, paper_id)
    result = await run_single_qa(
        paper_id,
        question,
        qa_client=qa_client,
        qa_service=qa_service,
        routing_meta=routing,
    )
    guardrails = run_heuristic_guardrails(
        result.answer_text,
        result.citations,
        item.get("gold", {}),
        paradigm=item.get("paradigm"),
    )
    return {
        "question": question,
        "paper_id": paper_id,
        "paradigm": item.get("paradigm"),
        "answer_length": len(result.answer_text),
        "citation_count": len(result.citations),
        "error_code": result.error_code,
        "elapsed_ms": result.elapsed_ms,
        "ttft_ms": result.ttft_ms,
        **routing,
        "graph_element_recall": guardrails.graph_element_recall,
        "chunk_recall": guardrails.chunk_recall,
        "numeric_match": guardrails.numeric_match,
        "passed": (result.error_code is None and len(result.answer_text) > 0),
    }


async def run_full_eval(
    item: dict[str, Any],
    *,
    paper_id: str,
    qa_client: LlmClient,
    judge_client: LlmClient,
    qa_service: QaService | None = None,
) -> dict[str, Any]:
    """Run QA (Generator) then dual-track heuristic + Judge evaluation."""
    question = item["question"]
    gold = item.get("gold", {})
    routing = _routing_fields(item, paper_id)

    result = await run_single_qa(
        paper_id,
        question,
        qa_client=qa_client,
        qa_service=qa_service,
        routing_meta=routing,
    )
    guardrails = run_heuristic_guardrails(
        result.answer_text,
        result.citations,
        gold,
        paradigm=item.get("paradigm"),
    )

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
        "ttft_ms": result.ttft_ms,
        **routing,
        "graph_element_recall": guardrails.graph_element_recall,
        "chunk_recall": guardrails.chunk_recall,
        "numeric_match": guardrails.numeric_match,
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
    qa_service: QaService | None,
    dry_run: bool,
) -> dict[str, Any]:
    async with semaphore:
        if dry_run:
            return await run_dry_eval(
                item,
                paper_id=paper_id,
                qa_client=qa_client,
                qa_service=qa_service,
            )
        assert qa_client is not None and judge_client is not None
        return await run_full_eval(
            item,
            paper_id=paper_id,
            qa_client=qa_client,
            judge_client=judge_client,
            qa_service=qa_service,
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

    qa_service = _build_benchmark_qa_service(graph_dir)
    print(f"[INFO] graph_dir={graph_dir}")
    if get_settings().is_llm_mock:
        wiring = "QaService + HybridRetriever(static mock vectors)"
    else:
        wiring = "QaService + HybridRetriever"
    print(f"[INFO] qa_router wired via {wiring}")

    qa_client = get_qa_llm_client()
    judge_client: LlmClient | None = None
    clients_isolated = True
    if not args.dry_run:
        judge_client = get_judge_llm_client()
        clients_isolated = _log_dual_model_bindings(qa_client, judge_client)
        settings = get_settings()
        print(
            f"[INFO] Judge timeout={settings.judge_timeout_seconds}s, concurrency={args.concurrency}",
        )
    else:
        settings = get_settings()
        print(
            f"[INFO] Generator (QA): model={settings.qa_model_effective} (dry-run — Judge skipped)",
        )

    semaphore = asyncio.Semaphore(max(1, min(args.concurrency, 10)))
    tasks = [
        _eval_item_with_semaphore(
            semaphore,
            item,
            paper_id=item.get("paper_id", M2_DEMO_PAPER_ID),
            qa_client=qa_client,
            judge_client=judge_client,
            qa_service=qa_service,
            dry_run=args.dry_run,
        )
        for item in items
    ]
    try:
        results = await asyncio.gather(*tasks)
    finally:
        reset_hybrid_retriever()

    success_count = 0
    failed_count = 0
    for idx, (item, r) in enumerate(zip(items, results, strict=True), start=1):
        question = item["question"]
        print(f"\n[{idx}/{len(items)}] {question[:60]}...")

        eval_data = r.get("evaluation", {})
        faithfulness = eval_data.get("faithfulness", {})
        hallucination_rate = faithfulness.get("hallucination_rate", 0.0)
        semantic_alignment = faithfulness.get("semantic_alignment", faithfulness.get("entailment_rate", 0.0))
        verbosity_rate = _extract_verbosity_rate(r)

        if not args.dry_run:
            _maybe_flag_redundant_suspect(r, verbosity_rate=verbosity_rate, question=question)

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
    chunk_gate_policy = _resolve_chunk_recall_gate_policy(dry_run=args.dry_run)
    mean_recall = _compute_mean_recall(results)
    mean_semantic_alignment = _compute_mean_semantic_alignment(results)
    per_question_hallucination = _collect_per_question_hallucination_rates(results)
    mean_hallucination_rate = compute_mean_hallucination_rate(per_question_hallucination)
    verbosity_ceiling = _resolve_verbosity_ceiling()
    redundant_suspects = _collect_redundant_suspects(results)
    routing_summary = _compute_routing_summary(
        results,
        items,
        chunk_recall_floor=chunk_gate_policy.floor,
        chunk_gate_policy=chunk_gate_policy,
    )
    paradigm_summary = _compute_paradigm_report_summary(results, items)
    breakdown = _build_report_breakdown(results, items)

    report = EvaluationReport(
        generated_at=datetime.now(UTC).isoformat(),
        version=golden["version"],
        total_questions=len(items),
        success_count=success_count,
        failed_count=failed_count,
        results=list(results),
        breakdown=breakdown,
        summary={
            "success_rate": success_count / max(len(items), 1),
            "mean_graph_element_recall": round(mean_recall, 2),
            "mean_semantic_alignment": round(mean_semantic_alignment, 2),
            "recall_floor": floor,
            "recall_pass": mean_recall >= floor,
            "chunk_recall_gate_policy": {
                "tier": chunk_gate_policy.tier,
                "floor": chunk_gate_policy.floor,
                "enforced": chunk_gate_policy.enforced,
            },
            "mean_hallucination_rate": round(mean_hallucination_rate, 4),
            "hallucination_pass": hallucination_ci_pass(mean_hallucination_rate) if not args.dry_run else None,
            "verbosity_ceiling": verbosity_ceiling if not args.dry_run else None,
            "redundant_suspect_count": len(redundant_suspects) if not args.dry_run else None,
            "redundant_suspect_questions": redundant_suspects if not args.dry_run else None,
            "qa_model": get_settings().qa_model_effective,
            "judge_model": get_settings().judge_model_effective if not args.dry_run else None,
            "clients_isolated": clients_isolated if not args.dry_run else None,
            "routing": routing_summary,
            **paradigm_summary,
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
    _print_routing_summary(routing_summary)

    if not args.dry_run and redundant_suspects:
        print(
            f"\n[WARN] 🟡 {len(redundant_suspects)} question(s) exceed verbosity ceiling "
            f"{verbosity_ceiling:.0%} — tagged [{_REDUNDANT_SUSPECT_TAG}] for manual review.",
        )

    if not args.dry_run and not hallucination_ci_pass(mean_hallucination_rate):
        print(
            f"\n[FAIL] RED LINE: mean hallucination_rate={mean_hallucination_rate:.0%} "
            f"({sum(per_question_hallucination)}/{len(per_question_hallucination)} questions) — "
            "CI requires strictly 0%.",
        )
        return EXIT_RED_LINE

    chunk_gate = routing_summary.get("detail_recall_gate", {})
    if _should_fail_chunk_recall_gate(chunk_gate_policy, chunk_gate):
        print(
            f"\n[FAIL] chunk_recall gate ({chunk_gate_policy.tier}): "
            f"min_chunk_recall={chunk_gate.get('chunk_recall_min')} "
            f"< floor={chunk_gate_policy.floor}",
        )
        return EXIT_FAILED

    print(f"\n[OK] Success: {success_count}/{len(items)}")
    return EXIT_SUCCESS


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_chunk_recall_gate_policy(*, dry_run: bool) -> ChunkRecallGatePolicy:
    """Resolve chunk recall floor tier for mock/dry-run vs release strict gates."""
    if _env_truthy(_EVAL_GATE_STRICT_CHUNK_ENV):
        return ChunkRecallGatePolicy(
            floor=_CHUNK_RECALL_FLOOR_STRICT,
            tier="release_strict",
            enforced=True,
        )
    if dry_run or get_settings().is_llm_mock:
        return ChunkRecallGatePolicy(
            floor=_CHUNK_RECALL_FLOOR_MOCK,
            tier="mock_dry_run",
            enforced=True,
        )
    return ChunkRecallGatePolicy(
        floor=_CHUNK_RECALL_FLOOR_STRICT,
        tier="informational",
        enforced=False,
    )


def _should_fail_chunk_recall_gate(
    policy: ChunkRecallGatePolicy,
    detail_recall_gate: dict[str, Any],
) -> bool:
    if not policy.enforced:
        return False
    if detail_recall_gate.get("chunk_recall_cohort_count", 0) == 0:
        return False
    return detail_recall_gate.get("chunk_recall_gate_pass", True) is False


def _resolve_verbosity_ceiling() -> float:
    """Resolve QA verbosity yellow-line threshold (env override, default 0.15)."""
    raw = os.environ.get("QA_VERBOSITY_CEILING", str(_DEFAULT_QA_VERBOSITY_CEILING))
    try:
        return float(raw)
    except ValueError:
        logger.warning("invalid QA_VERBOSITY_CEILING=%r — fallback to %.2f", raw, _DEFAULT_QA_VERBOSITY_CEILING)
        return _DEFAULT_QA_VERBOSITY_CEILING


def _extract_verbosity_rate(result: dict[str, Any]) -> float | None:
    directness = result.get("evaluation", {}).get("directness", {})
    rate = directness.get("verbosity_rate")
    if rate is None:
        return None
    return float(rate)


def _maybe_flag_redundant_suspect(
    result: dict[str, Any],
    *,
    verbosity_rate: float | None,
    question: str,
) -> bool:
    """Mark high-verbosity answers for manual review — never fails CI."""
    if verbosity_rate is None:
        return False

    ceiling = _resolve_verbosity_ceiling()
    if verbosity_rate <= ceiling:
        return False

    result["redundant_suspect"] = True
    result["verbosity_warning"] = _REDUNDANT_SUSPECT_TAG
    logger.warning(
        "🟡 verbosity_rate=%.4f > ceiling %.4f — [%s] question=%s",
        verbosity_rate,
        ceiling,
        _REDUNDANT_SUSPECT_TAG,
        question[:120],
    )
    print(
        f"  [🟡 {_REDUNDANT_SUSPECT_TAG}] verbosity_rate={verbosity_rate:.2%} > ceiling {ceiling:.0%}",
    )
    return True


def _collect_redundant_suspects(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize questions flagged as verbosity suspects for the report summary."""
    suspects: list[dict[str, Any]] = []
    for result in results:
        if not result.get("redundant_suspect"):
            continue
        suspects.append(
            {
                "question": result.get("question", ""),
                "verbosity_rate": _extract_verbosity_rate(result),
                "tag": _REDUNDANT_SUSPECT_TAG,
            },
        )
    return suspects


def _collect_per_question_hallucination_rates(results: list[dict[str, Any]]) -> list[float]:
    """Collect per-question hallucination_rate values for golden-set averaging."""
    rates: list[float] = []
    for result in results:
        rate = result.get("evaluation", {}).get("faithfulness", {}).get("hallucination_rate")
        if rate is not None:
            rates.append(float(rate))
    return rates


def _collect_matched_required_patterns(answer_text: str, gold: dict[str, Any]) -> list[str]:
    """Return required_patterns whose substring appears in the model answer."""
    answer_lower = answer_text.lower()
    matched: list[str] = []
    for pattern in gold.get("required_patterns", []):
        token = str(pattern).strip()
        if token and token.lower() in answer_lower:
            matched.append(token)
    return matched


def _compute_paradigm_report_summary(
    results: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Paradigm-split headline metrics for mixed HSS/STEM benchmark reports."""
    hss_cases = sum(1 for item in items if str(item.get("paradigm", "")).upper() == "HSS")
    stem_cases = sum(1 for item in items if str(item.get("paradigm", "")).upper() == "STEM")
    per_question_hallucination = _collect_per_question_hallucination_rates(results)
    global_hallucination_rate = compute_mean_hallucination_rate(per_question_hallucination)

    chunk_recalls: list[float] = []
    for result in results:
        chunk_value = _extract_chunk_recall(result)
        if chunk_value is not None:
            chunk_recalls.append(chunk_value)

    global_chunk_recall: float | None = None
    if chunk_recalls:
        global_chunk_recall = round(sum(chunk_recalls) / len(chunk_recalls), 4)

    return {
        "total_cases": len(items),
        "hss_cases": hss_cases,
        "stem_cases": stem_cases,
        "global_hallucination_rate": round(global_hallucination_rate, 4),
        "global_chunk_recall": global_chunk_recall,
    }


def _build_report_breakdown(
    results: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-case paradigm/scale/chunk recall slice for report consumers."""
    breakdown: list[dict[str, Any]] = []
    for item, result in zip(items, results, strict=True):
        gold = item.get("gold", {})
        case_id = str(item.get("id") or item.get("question", ""))[:80]
        entry: dict[str, Any] = {
            "case_id": case_id,
            "paradigm": item.get("paradigm"),
            "scale": str(item.get("scale", "")).upper(),
            "required_patterns_matched": _collect_matched_required_patterns(
                result.get("answer_text", ""),
                gold,
            ),
        }
        chunk_recall = _extract_chunk_recall(result)
        if chunk_recall is not None:
            entry["chunk_recall"] = round(chunk_recall, 4)
        breakdown.append(entry)
    return breakdown


def _mean_ttft_for_scale(results: list[dict[str, Any]], scale: str) -> float | None:
    ttfts = [float(r["ttft_ms"]) for r in results if r.get("detected_scale") == scale and r.get("ttft_ms") is not None]
    if not ttfts:
        return None
    return sum(ttfts) / len(ttfts)


def _compute_routing_summary(
    results: list[dict[str, Any]],
    items: list[dict[str, Any]],
    *,
    chunk_recall_floor: float = _CHUNK_RECALL_FLOOR_STRICT,
    chunk_gate_policy: ChunkRecallGatePolicy | None = None,
) -> dict[str, Any]:
    """Aggregate scale routing accuracy, TTFT by scale, and detail recall gate."""
    scale_matches = [bool(r.get("scale_routing_match")) for r in results if r.get("scale_routing_match") is not None]
    summary_ttft = _mean_ttft_for_scale(results, QuestionScale.SUMMARY.value)
    detail_ttft = _mean_ttft_for_scale(results, QuestionScale.DETAIL.value)
    verification_ttft = _mean_ttft_for_scale(results, QuestionScale.VERIFICATION.value)

    ttft_improvement_ratio: float | None = None
    if summary_ttft is not None and detail_ttft is not None and summary_ttft > 0 and detail_ttft > 0:
        ttft_improvement_ratio = round(detail_ttft / summary_ttft, 2)

    recall_gate = _compute_detail_recall_gate(results, items, chunk_recall_floor=chunk_recall_floor)
    if chunk_gate_policy is not None:
        recall_gate = {
            **recall_gate,
            "chunk_gate_tier": chunk_gate_policy.tier,
            "chunk_gate_enforced": chunk_gate_policy.enforced,
        }
    vector_wiring = _compute_vector_branch_wiring(results)

    return {
        "scale_detection_accuracy": round(sum(scale_matches) / max(len(scale_matches), 1), 2),
        "mean_ttft_ms_summary": round(summary_ttft, 1) if summary_ttft is not None else None,
        "mean_ttft_ms_detail": round(detail_ttft, 1) if detail_ttft is not None else None,
        "mean_ttft_ms_verification": round(verification_ttft, 1) if verification_ttft is not None else None,
        "summary_ttft_ratio_vs_detail": ttft_improvement_ratio,
        "vector_branch_wiring": vector_wiring,
        "detail_recall_gate": recall_gate,
    }


def _compute_vector_branch_wiring(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Shadow check: SUMMARY must skip vectors; DETAIL/VERIFICATION must invoke branch."""
    summary_items = [r for r in results if r.get("detected_scale") == QuestionScale.SUMMARY.value]
    detail_items = [r for r in results if r.get("detected_scale") == QuestionScale.DETAIL.value]
    verification_items = [r for r in results if r.get("detected_scale") == QuestionScale.VERIFICATION.value]
    return {
        "summary_skip_vector_count": sum(1 for r in summary_items if r.get("vector_branch_invoked") is False),
        "summary_total": len(summary_items),
        "detail_invoke_vector_count": sum(1 for r in detail_items if r.get("vector_branch_invoked") is True),
        "detail_total": len(detail_items),
        "verification_invoke_vector_count": sum(
            1 for r in verification_items if r.get("vector_branch_invoked") is True
        ),
        "verification_total": len(verification_items),
        "wiring_pass": (
            all(r.get("vector_branch_invoked") is False for r in summary_items)
            and all(r.get("vector_branch_invoked") is True for r in detail_items)
            and all(r.get("vector_branch_invoked") is True for r in verification_items)
        ),
    }


def _extract_graph_element_recall(result: dict[str, Any]) -> float:
    eval_recall = result.get("evaluation", {}).get("completeness", {}).get("graph_element_recall")
    if eval_recall is not None:
        return float(eval_recall)
    if result.get("graph_element_recall") is not None:
        return float(result["graph_element_recall"])
    return 0.0


def _extract_numeric_match(result: dict[str, Any]) -> bool:
    guardrails = result.get("evaluation", {}).get("guardrails", {})
    if "numeric_match" in guardrails:
        return bool(guardrails["numeric_match"])
    if result.get("numeric_match") is not None:
        return bool(result["numeric_match"])
    return True


def _extract_chunk_recall(result: dict[str, Any]) -> float | None:
    eval_recall = result.get("evaluation", {}).get("completeness", {}).get("chunk_recall")
    if eval_recall is not None:
        return float(eval_recall)
    guardrails_recall = result.get("evaluation", {}).get("guardrails", {}).get("chunk_recall")
    if guardrails_recall is not None:
        return float(guardrails_recall)
    if result.get("chunk_recall") is not None:
        return float(result["chunk_recall"])
    return None


def _item_has_chunk_gold(item: dict[str, Any]) -> bool:
    return bool(resolve_gold_chunk_ids(item.get("gold", {})))


def _compute_detail_recall_gate(
    results: list[dict[str, Any]],
    items: list[dict[str, Any]],
    *,
    chunk_recall_floor: float = _CHUNK_RECALL_FLOOR_STRICT,
) -> dict[str, Any]:
    """Recall gate for detail cohort — prefer STEM detail items when present."""
    cohort: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (item, result)
        for item, result in zip(items, results, strict=True)
        if item.get("scale") in _RECALL_GATE_DETAIL_SCALES
    ]
    stem_detail = [(item, result) for item, result in cohort if item.get("paradigm") == Paradigm.STEM.value]
    if stem_detail:
        cohort = stem_detail

    if not cohort:
        return {
            "count": 0,
            "graph_element_recall_min": None,
            "chunk_recall_min": None,
            "recall_gate_pass": True,
            "numeric_gate_pass": True,
            "chunk_recall_gate_pass": True,
        }

    recalls = [_extract_graph_element_recall(result) for _, result in cohort]
    numeric_flags = [_extract_numeric_match(result) for _, result in cohort]
    recall_min = min(recalls)

    chunk_cohort = [(item, result) for item, result in cohort if _item_has_chunk_gold(item)]
    chunk_recalls: list[float] = []
    for _item, result in chunk_cohort:
        chunk_value = _extract_chunk_recall(result)
        chunk_recalls.append(0.0 if chunk_value is None else chunk_value)
    chunk_recall_min = min(chunk_recalls) if chunk_recalls else None
    chunk_gate_pass = chunk_recall_min is None or chunk_recall_meets_floor(chunk_recall_min, chunk_recall_floor)

    return {
        "count": len(cohort),
        "cohort": "stem_detail" if stem_detail else "detail",
        "graph_element_recall_min": round(recall_min, 4),
        "graph_element_recall_values": [round(v, 4) for v in recalls],
        "chunk_recall_min": round(chunk_recall_min, 4) if chunk_recall_min is not None else None,
        "chunk_recall_values": [round(v, 4) for v in chunk_recalls] if chunk_recalls else [],
        "chunk_recall_cohort_count": len(chunk_cohort),
        "recall_gate_pass": recall_min >= 1.0 and chunk_gate_pass,
        "numeric_gate_pass": all(numeric_flags),
        "chunk_recall_gate_pass": chunk_gate_pass,
        "chunk_recall_floor": chunk_recall_floor,
    }


def _print_routing_summary(routing: dict[str, Any]) -> None:
    print("\n[INFO] --- QA Router Benchmark Metrics ---")
    print(f"  scale_detection_accuracy={routing.get('scale_detection_accuracy')}")
    print(f"  mean_ttft_ms_summary={routing.get('mean_ttft_ms_summary')}")
    print(f"  mean_ttft_ms_detail={routing.get('mean_ttft_ms_detail')}")
    print(f"  mean_ttft_ms_verification={routing.get('mean_ttft_ms_verification')}")
    ratio = routing.get("summary_ttft_ratio_vs_detail")
    if ratio is not None:
        print(f"  summary_ttft_ratio_vs_detail={ratio}x (detail/summary — higher means summary is faster)")
    wiring = routing.get("vector_branch_wiring", {})
    print(
        f"  vector_branch_wiring: summary_skip={wiring.get('summary_skip_vector_count')}/"
        f"{wiring.get('summary_total')}, detail_invoke={wiring.get('detail_invoke_vector_count')}/"
        f"{wiring.get('detail_total')}, pass={wiring.get('wiring_pass')}",
    )
    gate = routing.get("detail_recall_gate", {})
    print(
        f"  detail_recall_gate: count={gate.get('count')}, "
        f"min_graph_recall={gate.get('graph_element_recall_min')}, "
        f"min_chunk_recall={gate.get('chunk_recall_min')}, "
        f"chunk_floor={gate.get('chunk_recall_floor')}, "
        f"chunk_tier={gate.get('chunk_gate_tier')}, "
        f"chunk_enforced={gate.get('chunk_gate_enforced')}, "
        f"pass={gate.get('recall_gate_pass')}",
    )


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
