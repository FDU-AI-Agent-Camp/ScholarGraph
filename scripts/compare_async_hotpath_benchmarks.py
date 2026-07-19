# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Aggregate raw async hot-path benchmark JSON files into a comparison report.

Reads every ``*.json`` written by ``scripts/benchmark_async_hotpath.py`` from
``--input-dir``, groups by (layer, concurrency, label), computes pooled
percentiles with hierarchical-bootstrap 95% confidence intervals, and writes a
merged JSON document plus a Markdown report.

Bootstrap notes (kept out of the resample hot path for speed):
- All draws use ``random.Random.choices`` (C-backed batch sampling).
- Latency CIs use a hierarchical bootstrap: resample repetitions first, then
  operation samples within each selected repetition.
- QPS CIs resample the per-repetition QPS summaries.
- Candidate/baseline ratio CIs use paired draws over matched repetition
  indices, because repetitions are executed in alternating matched pairs.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_RESAMPLES = 10_000
DEFAULT_SEED = 20260719
CI_LOW_Q = 2.5
CI_HIGH_Q = 97.5
PROGRESS_EVERY = 1_000

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.benchmark_async_hotpath import percentile  # noqa: E402

# ---------------------------------------------------------------------------
# Bootstrap primitives (unit-tested)
# ---------------------------------------------------------------------------


def _latency_stats(sorted_values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": percentile(sorted_values, 50),
        "p95_ms": percentile(sorted_values, 95),
        "p99_ms": percentile(sorted_values, 99),
    }


def hierarchical_latency_bootstrap(
    rep_samples: list[list[float]],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    progress_label: str | None = None,
) -> dict[str, tuple[float, float]]:
    """95% CI for pooled P50/P95/P99 via hierarchical bootstrap.

    Resamples repetitions with replacement, then operation samples within each
    chosen repetition, sorting once per resample and reading all three
    percentiles from the same sorted array.
    """
    if not rep_samples or any(not rep for rep in rep_samples):
        raise ValueError("hierarchical bootstrap requires non-empty repetition samples")
    rng = random.Random(seed)
    rep_count = len(rep_samples)
    draws: dict[str, list[float]] = {"p50_ms": [], "p95_ms": [], "p99_ms": []}
    started = time.perf_counter()
    for iteration in range(n_resamples):
        chosen_reps = rng.choices(range(rep_count), k=rep_count)
        pooled: list[float] = []
        for rep_index in chosen_reps:
            samples = rep_samples[rep_index]
            pooled.extend(rng.choices(samples, k=len(samples)))
        pooled.sort()
        stats = _latency_stats(pooled)
        for key, value in stats.items():
            draws[key].append(value)
        if progress_label and (iteration + 1) % PROGRESS_EVERY == 0:
            elapsed = time.perf_counter() - started
            print(f"  [{progress_label}] resample {iteration + 1}/{n_resamples} ({elapsed:.1f}s)")
    intervals: dict[str, tuple[float, float]] = {}
    for key, values in draws.items():
        values.sort()
        intervals[key] = (percentile(values, CI_LOW_Q), percentile(values, CI_HIGH_Q))
    return intervals


def scalar_bootstrap_ci(
    rep_values: list[float],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
    """95% CI for the mean of per-repetition scalar summaries (e.g. QPS)."""
    if not rep_values:
        raise ValueError("scalar bootstrap requires at least one repetition value")
    rng = random.Random(seed)
    count = len(rep_values)
    means = sorted(sum(rng.choices(rep_values, k=count)) / count for _ in range(n_resamples))
    return (percentile(means, CI_LOW_Q), percentile(means, CI_HIGH_Q))


def paired_ratio_ci(
    baseline_reps: list[float],
    candidate_reps: list[float],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
    """95% CI for mean(candidate)/mean(baseline) using paired repetition draws."""
    if len(baseline_reps) != len(candidate_reps) or not baseline_reps:
        raise ValueError("paired ratio requires equal, non-empty repetition lists")
    rng = random.Random(seed)
    count = len(baseline_reps)
    indices = range(count)
    ratios: list[float] = []
    for _ in range(n_resamples):
        chosen = rng.choices(indices, k=count)
        base_mean = sum(baseline_reps[i] for i in chosen) / count
        cand_mean = sum(candidate_reps[i] for i in chosen) / count
        if base_mean <= 0:
            continue
        ratios.append(cand_mean / base_mean)
    if not ratios:
        raise ValueError("paired ratio bootstrap produced no valid draws")
    ratios.sort()
    return (percentile(ratios, CI_LOW_Q), percentile(ratios, CI_HIGH_Q))


def paired_latency_ratio_ci(
    baseline_rep_samples: list[list[float]],
    candidate_rep_samples: list[list[float]],
    metric: str,
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
    """95% CI for candidate/baseline pooled-percentile ratio via paired hierarchical draws."""
    if len(baseline_rep_samples) != len(candidate_rep_samples) or not baseline_rep_samples:
        raise ValueError("paired latency ratio requires matched repetition lists")
    metric_q = {"p50_ms": 50, "p95_ms": 95, "p99_ms": 99}[metric]
    rng = random.Random(seed)
    count = len(baseline_rep_samples)
    ratios: list[float] = []
    for _ in range(n_resamples):
        chosen = rng.choices(range(count), k=count)
        base_pool: list[float] = []
        cand_pool: list[float] = []
        for rep_index in chosen:
            base = baseline_rep_samples[rep_index]
            cand = candidate_rep_samples[rep_index]
            base_pool.extend(rng.choices(base, k=len(base)))
            cand_pool.extend(rng.choices(cand, k=len(cand)))
        base_pool.sort()
        cand_pool.sort()
        base_value = percentile(base_pool, metric_q)
        if base_value <= 0:
            continue
        ratios.append(percentile(cand_pool, metric_q) / base_value)
    if not ratios:
        raise ValueError("paired latency ratio bootstrap produced no valid draws")
    ratios.sort()
    return (percentile(ratios, CI_LOW_Q), percentile(ratios, CI_HIGH_Q))


# ---------------------------------------------------------------------------
# Raw-document loading and fingerprint checks
# ---------------------------------------------------------------------------


def load_raw_documents(input_dir: Path) -> list[dict[str, Any]]:
    documents = []
    for path in sorted(input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_source"] = str(path)
        documents.append(payload)
    if not documents:
        raise SystemExit(f"no raw benchmark files found under {input_dir}")
    return documents


def assert_fingerprints_compatible(documents: list[dict[str, Any]], *, allow_mismatch: bool) -> list[str]:
    """Groups sharing (layer, concurrency) must share the workload fingerprint."""
    warnings: list[str] = []
    by_cell: dict[tuple[str, int], dict[str, Any]] = {}
    for doc in documents:
        cell = (doc["layer"], doc["concurrency"])
        fingerprint = dict(doc["workload_fingerprint"])
        existing = by_cell.get(cell)
        if existing is None:
            by_cell[cell] = fingerprint
        elif existing != fingerprint:
            message = f"workload fingerprint mismatch in cell layer={cell[0]} c={cell[1]}"
            if allow_mismatch:
                warnings.append(message)
            else:
                raise SystemExit(message + " (use --allow-mismatch to override)")
    env_keys = {json.dumps(doc["env_fingerprint"], sort_keys=True) for doc in documents}
    if len(env_keys) > 2:  # one per label is expected (candidate_async differs)
        warnings.append("more than two distinct env fingerprints; check host consistency")
    return warnings


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _group_documents(
    documents: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, list[dict[str, Any]]]]:
    grouped: dict[tuple[str, int], dict[str, list[dict[str, Any]]]] = {}
    for doc in documents:
        cell = grouped.setdefault((doc["layer"], doc["concurrency"]), {})
        cell.setdefault(doc["label"], []).append(doc)
    for cell in grouped.values():
        for docs in cell.values():
            docs.sort(key=lambda d: d["repetition"])
    return grouped


def _summarize_label(docs: list[dict[str, Any]], *, n_resamples: int, seed: int, progress_label: str) -> dict[str, Any]:
    rep_latencies = [doc["results"]["latencies_ms"] for doc in docs]
    pooled = sorted(value for rep in rep_latencies for value in rep)
    rep_qps = [doc["results"]["qps"] for doc in docs]
    lag_pooled = sorted(v for doc in docs for v in doc["results"]["loop_lag_ms"]["samples"])
    errors: dict[str, int] = {}
    for doc in docs:
        for error_type, count in doc["results"]["errors"].items():
            errors[error_type] = errors.get(error_type, 0) + count
    latency_ci = hierarchical_latency_bootstrap(
        rep_latencies,
        n_resamples=n_resamples,
        seed=seed,
        progress_label=progress_label,
    )
    summary = {
        "repetitions": len(docs),
        "success_count": sum(doc["results"]["success_count"] for doc in docs),
        "error_count": sum(doc["results"]["error_count"] for doc in docs),
        "errors": errors,
        "latency": {
            "p50_ms": percentile(pooled, 50),
            "p95_ms": percentile(pooled, 95),
            "p99_ms": percentile(pooled, 99),
            "mean_ms": sum(pooled) / len(pooled),
            "max_ms": pooled[-1],
            "ci95": {key: list(value) for key, value in latency_ci.items()},
        },
        "qps": {
            "mean": statistics.fmean(rep_qps),
            "stdev": statistics.stdev(rep_qps) if len(rep_qps) > 1 else 0.0,
            "per_repetition": rep_qps,
            "ci95": list(scalar_bootstrap_ci(rep_qps, n_resamples=n_resamples, seed=seed)),
        },
        "loop_lag_ms": {
            "p99": percentile(lag_pooled, 99) if lag_pooled else 0.0,
            "max": lag_pooled[-1] if lag_pooled else 0.0,
            "over_20ms": sum(1 for sample in lag_pooled if sample > 20.0),
            "over_100ms": sum(1 for sample in lag_pooled if sample > 100.0),
            "sample_count": len(lag_pooled),
        },
        "drain_s": {
            "mean": statistics.fmean(doc["results"]["drain_s"] for doc in docs),
            "max": max(doc["results"]["drain_s"] for doc in docs),
        },
    }
    lock_errors = sum(count for error_type, count in errors.items() if "database_is_locked" in error_type)
    summary["sqlite_write_bound"] = lock_errors > 0
    summary["database_locked_count"] = lock_errors
    return summary


def _compare_cell(
    baseline_docs: list[dict[str, Any]],
    candidate_docs: list[dict[str, Any]],
    *,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    baseline_reps = [doc["results"]["latencies_ms"] for doc in baseline_docs]
    candidate_reps = [doc["results"]["latencies_ms"] for doc in candidate_docs]
    ratios: dict[str, Any] = {}
    for metric in ("p50_ms", "p95_ms", "p99_ms"):
        low, high = paired_latency_ratio_ci(
            baseline_reps,
            candidate_reps,
            metric,
            n_resamples=n_resamples,
            seed=seed,
        )
        ratios[f"latency_{metric}_ratio_ci95"] = [low, high]
    qps_low, qps_high = paired_ratio_ci(
        [doc["results"]["qps"] for doc in baseline_docs],
        [doc["results"]["qps"] for doc in candidate_docs],
        n_resamples=n_resamples,
        seed=seed,
    )
    ratios["qps_ratio_ci95"] = [qps_low, qps_high]
    lag_low, lag_high = paired_ratio_ci(
        [doc["results"]["loop_lag_ms"]["max"] for doc in baseline_docs],
        [doc["results"]["loop_lag_ms"]["max"] for doc in candidate_docs],
        n_resamples=n_resamples,
        seed=seed,
    )
    ratios["loop_lag_max_ratio_ci95"] = [lag_low, lag_high]
    ratios["qps_improvement_supported"] = qps_low > 1.0
    ratios["p99_improvement_supported"] = ratios["latency_p99_ms_ratio_ci95"][1] < 1.0
    ratios["loop_lag_improvement_supported"] = lag_high < 1.0
    return ratios


def build_comparison(
    documents: list[dict[str, Any]],
    *,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    grouped = _group_documents(documents)
    cells = []
    for (layer, concurrency), by_label in sorted(grouped.items()):
        cell: dict[str, Any] = {"layer": layer, "concurrency": concurrency, "labels": {}}
        for label, docs in sorted(by_label.items()):
            progress = f"{layer}/c{concurrency}/{label}"
            cell["labels"][label] = _summarize_label(
                docs,
                n_resamples=n_resamples,
                seed=seed,
                progress_label=progress,
            )
        if "baseline" in by_label and "candidate" in by_label:
            base_docs, cand_docs = by_label["baseline"], by_label["candidate"]
            if len(base_docs) == len(cand_docs):
                cell["candidate_vs_baseline"] = _compare_cell(
                    base_docs,
                    cand_docs,
                    n_resamples=n_resamples,
                    seed=seed,
                )
        cells.append(cell)
    return {
        "schema_version": 1,
        "n_resamples": n_resamples,
        "seed": seed,
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _format_ci(interval: list[float], unit: str = "") -> str:
    return f"[{interval[0]:.2f}, {interval[1]:.2f}]{unit}"


def render_markdown(comparison: dict[str, Any], documents: list[dict[str, Any]], warnings: list[str]) -> str:
    commits = {doc["label"]: doc["commit"] for doc in documents}
    env = documents[0]["env_fingerprint"]
    lines = [
        "# Async Hot-Path Benchmark Report",
        "",
        f"- baseline: `{commits.get('baseline', 'n/a')}`",
        f"- candidate: `{commits.get('candidate', 'n/a')}`",
        f"- host: {env['platform']} / Python {env['python']} / {env['cpu_count']} CPUs / affinity={env['affinity']}",
        f"- bootstrap: {comparison['n_resamples']} resamples, seed {comparison['seed']}, 95% CI",
        "",
    ]
    if warnings:
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    for cell in comparison["cells"]:
        lines.append(f"## {cell['layer']} @ concurrency {cell['concurrency']}")
        lines.append("")
        lines.append(
            "| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | "
            "loop lag P99/max ms | lag>20ms | lag>100ms | errors | locked |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for label, summary in sorted(cell["labels"].items()):
            latency = summary["latency"]
            qps = summary["qps"]
            lag = summary["loop_lag_ms"]
            lines.append(
                f"| {label} | {qps['mean']:.1f} {_format_ci(qps['ci95'])} "
                f"| {latency['p50_ms']:.1f} | {latency['p95_ms']:.1f} "
                f"| {latency['p99_ms']:.1f} {_format_ci(latency['ci95']['p99_ms'])} "
                f"| {lag['p99']:.1f} / {lag['max']:.1f} "
                f"| {lag.get('over_20ms', 0)} | {lag.get('over_100ms', 0)} "
                f"| {summary['error_count']} | {summary['database_locked_count']} |",
            )
        lines.append("")
        ratios = cell.get("candidate_vs_baseline")
        if ratios:
            lines.append(
                f"- candidate/baseline QPS ratio CI95: {_format_ci(ratios['qps_ratio_ci95'])} "
                f"(supported improvement: {ratios['qps_improvement_supported']})",
            )
            lines.append(
                f"- candidate/baseline P99 ratio CI95: {_format_ci(ratios['latency_p99_ms_ratio_ci95'])} "
                f"(supported improvement: {ratios['p99_improvement_supported']})",
            )
            base_lag = cell["labels"].get("baseline", {}).get("loop_lag_ms", {})
            cand_lag = cell["labels"].get("candidate", {}).get("loop_lag_ms", {})
            if base_lag and cand_lag and base_lag.get("max", 0) > 0:
                lag_ratio = cand_lag["max"] / base_lag["max"]
                lines.append(
                    f"- loop-lag max ratio (candidate/baseline): {lag_ratio:.3f} "
                    f"(baseline_max={base_lag['max']:.1f}ms, candidate_max={cand_lag['max']:.1f}ms)",
                )
            saturation = any(cell["labels"][label]["sqlite_write_bound"] for label in cell["labels"])
            if saturation:
                lines.append(
                    "- caveat: `sqlite_write_bound` — write-lock saturation detected; "
                    "prefer loop-lag attribution over raw P99/QPS",
                )
            if base_lag.get("max", 0) >= 100 and cand_lag.get("max", 0) < 50:
                lines.append(
                    "- note: baseline ghost-sync keeps per-op P99 flat by freezing the loop; "
                    "loop-lag is the primary success metric for this cell",
                )
            if cell["layer"] == "diskio":
                base_over = base_lag.get("over_20ms", 0)
                cand_over = cand_lag.get("over_20ms", 0)
                lines.append(
                    f"- diskio lag>20ms counts: baseline={base_over}, candidate={cand_over} "
                    "(natural tiny-JSON I/O is often <20ms when OS-cached; use "
                    "`--amplify-sync-io-ms` for a controlled slow-disk console verdict)",
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--allow-mismatch", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    documents = load_raw_documents(Path(args.input_dir))
    warnings = assert_fingerprints_compatible(documents, allow_mismatch=args.allow_mismatch)
    started = time.perf_counter()
    comparison = build_comparison(documents, n_resamples=args.resamples, seed=args.seed)
    comparison["aggregation_seconds"] = time.perf_counter() - started

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(comparison, documents, warnings), encoding="utf-8")
    print(f"wrote {output_json} and {output_md} (aggregation {comparison['aggregation_seconds']:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
