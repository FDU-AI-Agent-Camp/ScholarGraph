#!/usr/bin/env python3
"""Benchmark two-phase vs single-phase graph extraction on local corpus papers.

Usage (repo root):

    uv run python scripts/benchmark_extract_two_phase.py \
        --papers hss-001 hss-002 hss-003 stem-001 stem-002 stem-003

The script will:
1. Load full text from ``data/corpus/{id}.txt`` if present, otherwise parse ``{id}.pdf``.
2. Classify the paradigm (or infer from the paper id prefix).
3. Run extraction in both single-phase and two-phase modes.
4. Report node/edge counts, warnings, elapsed time, retries, and fallback status.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"

# Make repo root importable for backend.* modules
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class ExtractRun:
    """Metrics for one extraction run."""

    mode: str
    paper_id: str
    paradigm: str
    node_count: int = 0
    edge_count: int = 0
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    retries: int = 0
    fallback: bool = False
    error: str | None = None


def _infer_paradigm(paper_id: str) -> str:
    """Infer paradigm from paper id prefix (hss-* / stem-*)."""
    if paper_id.lower().startswith("hss-"):
        return "HSS"
    if paper_id.lower().startswith("stem-"):
        return "STEM"
    raise ValueError(f"Cannot infer paradigm from paper_id: {paper_id}")


async def _load_full_text(paper_id: str) -> str:
    """Load full text from .txt file or parse PDF."""
    txt_path = CORPUS_DIR / f"{paper_id}.txt"
    if txt_path.is_file():
        return txt_path.read_text(encoding="utf-8")

    pdf_path = CORPUS_DIR / f"{paper_id}.pdf"
    if not pdf_path.is_file():
        raise FileNotFoundError(f"No corpus file found for {paper_id}")

    from backend.ingest.pdf import ingest_pdf

    result = await ingest_pdf(pdf_path)
    return result["full_text"]


def _set_extract_mode(*, two_phase: bool) -> None:
    """Switch extraction mode by updating env and clearing settings cache."""
    os.environ["EXTRACT_TWO_PHASE_ENABLED"] = "true" if two_phase else "false"

    from backend.config import get_settings

    get_settings.cache_clear()

    # Also clear LLM client cache if it has model-dependent state.
    from backend.llm.client import reset_llm_client_cache

    reset_llm_client_cache()


async def _run_extraction(
    paper_id: str, full_text: str, *, two_phase: bool, max_chars: int, timeout_seconds: int = 180
) -> ExtractRun:
    """Run extraction once and collect metrics."""
    from backend.agents.extractor import extract
    from backend.config import get_settings
    from backend.schemas.paradigm import Paradigm

    _set_extract_mode(two_phase=two_phase)

    # Apply per-run input limit by temporarily overriding settings.
    settings = get_settings()
    settings.extract_max_input_chars = max_chars

    paradigm = Paradigm(_infer_paradigm(paper_id))
    run = ExtractRun(mode="two_phase" if two_phase else "single_phase", paper_id=paper_id, paradigm=paradigm.value)

    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(extract(full_text, paradigm, paper_id=paper_id), timeout=timeout_seconds)
    except TimeoutError:
        run.error = "Timeout"
        run.elapsed_seconds = time.perf_counter() - started
        return run
    except Exception as exc:
        run.error = f"{type(exc).__name__}: {exc}"
        run.elapsed_seconds = time.perf_counter() - started
        return run

    run.elapsed_seconds = time.perf_counter() - started
    run.node_count = len(result.graph.nodes)
    run.edge_count = len(result.graph.edges)
    run.warnings = result.warnings
    run.fallback = any("extract_heuristic_fallback" in w for w in result.warnings)
    return run


async def _evaluate_paper(paper_id: str, *, max_chars: int, timeout_seconds: int) -> dict[str, ExtractRun]:
    """Evaluate both extraction modes for one paper."""
    full_text = await _load_full_text(paper_id)
    print(f"Evaluating {paper_id}: {len(full_text):,} chars (limit {max_chars:,})")

    single = await _run_extraction(
        paper_id, full_text, two_phase=False, max_chars=max_chars, timeout_seconds=timeout_seconds
    )
    two = await _run_extraction(
        paper_id, full_text, two_phase=True, max_chars=max_chars, timeout_seconds=timeout_seconds
    )

    return {"single_phase": single, "two_phase": two}


def _print_results(results: list[dict[str, ExtractRun]]) -> None:
    """Print markdown table of results."""
    rows: list[list[str]] = []
    for result in results:
        single = result["single_phase"]
        two = result["two_phase"]
        rows.append(
            [
                single.paper_id,
                single.paradigm,
                single.mode,
                str(single.node_count),
                str(single.edge_count),
                f"{single.elapsed_seconds:.2f}s",
                ",".join(single.warnings) or "-",
                single.error or "-",
            ]
        )
        rows.append(
            [
                two.paper_id,
                two.paradigm,
                two.mode,
                str(two.node_count),
                str(two.edge_count),
                f"{two.elapsed_seconds:.2f}s",
                ",".join(two.warnings) or "-",
                two.error or "-",
            ]
        )

    headers = ["paper_id", "paradigm", "mode", "nodes", "edges", "time", "warnings", "error"]
    widths = [max(len(headers[i]), max(len(row[i]) for row in rows)) for i in range(len(headers))]

    def _format_row(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    print("\n" + _format_row(headers))
    print(" | ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print(_format_row(row))

    print("\n### Summary")
    single_times = [r["single_phase"].elapsed_seconds for r in results if r["single_phase"].error is None]
    two_times = [r["two_phase"].elapsed_seconds for r in results if r["two_phase"].error is None]
    single_nodes = [r["single_phase"].node_count for r in results if r["single_phase"].error is None]
    two_nodes = [r["two_phase"].node_count for r in results if r["two_phase"].error is None]
    single_edges = [r["single_phase"].edge_count for r in results if r["single_phase"].error is None]
    two_edges = [r["two_phase"].edge_count for r in results if r["two_phase"].error is None]
    single_fallbacks = sum(1 for r in results if r["single_phase"].fallback)
    two_fallbacks = sum(1 for r in results if r["two_phase"].fallback)

    if single_times and two_times:
        print(f"- Single-phase avg time: {statistics.mean(single_times):.2f}s")
        print(f"- Two-phase avg time:    {statistics.mean(two_times):.2f}s")
        print(
            f"- Single-phase avg nodes/edges: {statistics.mean(single_nodes):.1f} / {statistics.mean(single_edges):.1f}"
        )
        print(f"- Two-phase avg nodes/edges:    {statistics.mean(two_nodes):.1f} / {statistics.mean(two_edges):.1f}")
        print(f"- Single-phase fallbacks: {single_fallbacks}")
        print(f"- Two-phase fallbacks:    {two_fallbacks}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark extraction modes on corpus papers.")
    parser.add_argument(
        "--papers",
        nargs="+",
        default=["hss-001", "hss-002", "hss-003", "stem-001", "stem-002", "stem-003"],
        help="Paper ids from data/corpus to evaluate (default: 3 HSS + 3 STEM).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=8000,
        help="Max chars passed to extraction per paper (default: 8000).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Per-extraction timeout in seconds (default: 180).",
    )
    args = parser.parse_args(argv)

    # Ensure live mode for real evaluation; user can override with env.
    os.environ.setdefault("LLM_MODE", "live")

    missing = [
        pid
        for pid in args.papers
        if not (CORPUS_DIR / f"{pid}.txt").is_file() and not (CORPUS_DIR / f"{pid}.pdf").is_file()
    ]
    if missing:
        print(f"Missing corpus files for: {missing}")
        return 1

    results: list[dict[str, ExtractRun]] = []
    for paper_id in args.papers:
        results.append(asyncio.run(_evaluate_paper(paper_id, max_chars=args.max_chars, timeout_seconds=args.timeout)))

    _print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
