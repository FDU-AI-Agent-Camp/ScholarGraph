# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Benchmark JSON regression helpers for dual(rules) quality baseline (Phase D / T6).

Committed baseline: ``tests/fixtures/benchmark/dual_rules_baseline.json``.
Full machine reports: ``data/benchmark_reports/corpus-batch-*.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "benchmark" / "dual_rules_baseline.json"

BASELINE_SCHEMA_VERSION = 1
QUALITY_PATH_KEYS = ("pymupdf_sync", "path_b", "dual_route_rules", "dual_route_llm")
REPORT_PATH_KEYS = ("pymupdf_sync", "grobid_crf", "mineru_pipeline", "dual_route_rules", "dual_route_llm")


@dataclass(frozen=True)
class QualityTotals:
    pymupdf_sync: int
    path_b: int
    dual_route_rules: int
    dual_route_llm: int | None
    paper_count: int
    max_total: int

    @property
    def dual_route_rules_ratio(self) -> str:
        return f"{self.dual_route_rules}/{self.max_total}"


@dataclass
class RegressionDiff:
    paper_id: str
    field: str
    expected: int
    actual: int

    def __str__(self) -> str:
        return f"{self.paper_id}.{self.field}: expected {self.expected}, got {self.actual}"


@dataclass
class CompareResult:
    ok: bool
    diffs: list[RegressionDiff] = field(default_factory=list)
    totals: QualityTotals | None = None
    baseline_totals: QualityTotals | None = None
    constraint_violations: list[str] = field(default_factory=list)

    def format_message(self) -> str:
        lines: list[str] = []
        if self.baseline_totals and self.totals:
            lines.append(
                f"dual(rules) totals: baseline {self.baseline_totals.dual_route_rules_ratio} "
                f"vs actual {self.totals.dual_route_rules_ratio}"
            )
        for violation in self.constraint_violations:
            lines.append(f"constraint: {violation}")
        for diff in self.diffs:
            lines.append(str(diff))
        return "\n".join(lines) if lines else "ok"


def load_baseline(path: Path | None = None) -> dict[str, Any]:
    """Load committed regression baseline JSON."""
    baseline_path = path or DEFAULT_BASELINE_PATH
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    validate_baseline(payload)
    return payload


def validate_baseline(payload: dict[str, Any]) -> None:
    """Raise ``ValueError`` when baseline schema or invariants are invalid."""
    if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {payload.get('schema_version')}")

    required_top = ("baseline_id", "paper_ids", "totals", "papers")
    for key in required_top:
        if key not in payload:
            raise ValueError(f"baseline missing key: {key}")

    totals = payload["totals"]
    for key in ("dual_route_rules", "pymupdf_sync", "path_b", "max"):
        if key not in totals:
            raise ValueError(f"baseline.totals missing key: {key}")

    paper_ids = payload["paper_ids"]
    papers = payload["papers"]
    if set(paper_ids) != set(papers.keys()):
        raise ValueError("paper_ids mismatch vs papers keys")

    for paper_id in paper_ids:
        if paper_id not in papers:
            raise ValueError(f"papers missing entry for {paper_id}")
        entry = papers[paper_id]
        quality = entry.get("quality")
        if not isinstance(quality, dict):
            raise ValueError(f"{paper_id}.quality must be an object")
        for field_name in ("pymupdf_sync", "path_b", "dual_route_rules"):
            if field_name not in quality:
                raise ValueError(f"{paper_id}.quality missing {field_name}")
            score = quality[field_name]
            if not isinstance(score, int) or not 0 <= score <= 4:
                raise ValueError(f"{paper_id}.quality.{field_name} must be int 0–4")

    constraints = payload.get("constraints", {})
    if constraints.get("dual_gte_pymupdf") or constraints.get("dual_gte_path_b"):
        _assert_monotonicity(papers, paper_ids)


def _path_b_key_for_pages(pages: int | None, *, short_page_limit: int = 25) -> str:
    if pages is None:
        return "path_b"
    return "mineru_pipeline" if pages <= short_page_limit else "grobid_crf"


def _quality_total(entry: dict[str, Any] | None) -> int | None:
    if entry is None:
        return None
    quality = entry.get("quality")
    if not isinstance(quality, dict):
        return None
    total = quality.get("total")
    return int(total) if isinstance(total, int) else None


def summarize_report(
    payload: dict[str, Any],
    *,
    short_page_limit: int = 25,
) -> QualityTotals:
    """Aggregate quality totals from a full ``corpus-batch-*.json`` report."""
    paper_ids = payload.get("paper_ids") or []
    results = payload.get("results") or {}
    n = len(paper_ids)
    max_total = n * 4

    pym_total = path_b_total = dual_rules_total = dual_llm_total = 0
    dual_llm_seen = False

    for paper_id in paper_ids:
        row = results.get(paper_id)
        if not isinstance(row, dict):
            continue
        pages = row.get("pages")
        path_b_key = _path_b_key_for_pages(pages if isinstance(pages, int) else None, short_page_limit=short_page_limit)
        pym = _quality_total(row.get("pymupdf_sync"))
        path_b = _quality_total(row.get(path_b_key))
        dual_r = _quality_total(row.get("dual_route_rules"))
        dual_l = _quality_total(row.get("dual_route_llm"))
        if pym is not None:
            pym_total += pym
        if path_b is not None:
            path_b_total += path_b
        if dual_r is not None:
            dual_rules_total += dual_r
        if dual_l is not None:
            dual_llm_total += dual_l
            dual_llm_seen = True

    return QualityTotals(
        pymupdf_sync=pym_total,
        path_b=path_b_total,
        dual_route_rules=dual_rules_total,
        dual_route_llm=dual_llm_total if dual_llm_seen else None,
        paper_count=n,
        max_total=max_total,
    )


def extract_paper_quality_from_report(
    row: dict[str, Any],
    *,
    pages: int | None,
    short_page_limit: int = 25,
) -> dict[str, int | None]:
    path_b_key = _path_b_key_for_pages(pages, short_page_limit=short_page_limit)
    return {
        "pymupdf_sync": _quality_total(row.get("pymupdf_sync")),
        "path_b": _quality_total(row.get(path_b_key)),
        "dual_route_rules": _quality_total(row.get("dual_route_rules")),
        "dual_route_llm": _quality_total(row.get("dual_route_llm")),
    }


def _assert_monotonicity(papers: dict[str, Any], paper_ids: list[str]) -> None:
    for paper_id in paper_ids:
        quality = papers[paper_id]["quality"]
        dual = quality["dual_route_rules"]
        pym = quality["pymupdf_sync"]
        path_b = quality["path_b"]
        if dual < pym:
            raise ValueError(f"{paper_id}: dual_route_rules {dual} < pymupdf_sync {pym}")
        if dual < path_b:
            raise ValueError(f"{paper_id}: dual_route_rules {dual} < path_b {path_b}")


def compare_report_to_baseline(
    report: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    short_page_limit: int = 25,
) -> CompareResult:
    """Compare a full batch report against the committed baseline."""
    baseline = baseline or load_baseline()
    paper_ids = baseline["paper_ids"]
    results = report.get("results") or {}

    diffs: list[RegressionDiff] = []
    constraint_violations: list[str] = []

    for paper_id in paper_ids:
        expected_entry = baseline["papers"][paper_id]
        expected_quality = expected_entry["quality"]
        row = results.get(paper_id)
        if not isinstance(row, dict):
            diffs.append(RegressionDiff(paper_id, "missing_row", 1, 0))
            continue

        pages = row.get("pages")
        if isinstance(pages, int):
            pass
        elif isinstance(expected_entry.get("pages"), int):
            pages = expected_entry["pages"]

        actual_quality = extract_paper_quality_from_report(
            row,
            pages=pages if isinstance(pages, int) else None,
            short_page_limit=short_page_limit,
        )

        for field_name in ("pymupdf_sync", "path_b", "dual_route_rules"):
            expected = expected_quality[field_name]
            actual = actual_quality.get(field_name)
            if actual is None:
                diffs.append(RegressionDiff(paper_id, field_name, expected, -1))
            elif actual != expected:
                diffs.append(RegressionDiff(paper_id, field_name, expected, actual))

        dual = actual_quality.get("dual_route_rules")
        pym = actual_quality.get("pymupdf_sync")
        path_b = actual_quality.get("path_b")
        if dual is not None and pym is not None and dual < pym:
            constraint_violations.append(f"{paper_id}: dual {dual} < pymupdf {pym}")
        if dual is not None and path_b is not None and dual < path_b:
            constraint_violations.append(f"{paper_id}: dual {dual} < path_b {path_b}")

    baseline_totals = QualityTotals(
        pymupdf_sync=int(baseline["totals"]["pymupdf_sync"]),
        path_b=int(baseline["totals"]["path_b"]),
        dual_route_rules=int(baseline["totals"]["dual_route_rules"]),
        dual_route_llm=baseline["totals"].get("dual_route_llm"),
        paper_count=len(paper_ids),
        max_total=int(baseline["totals"]["max"]),
    )
    actual_totals = summarize_report(report, short_page_limit=short_page_limit)

    if actual_totals.dual_route_rules != baseline_totals.dual_route_rules:
        diffs.append(
            RegressionDiff(
                "__totals__",
                "dual_route_rules",
                baseline_totals.dual_route_rules,
                actual_totals.dual_route_rules,
            )
        )

    ok = not diffs and not constraint_violations
    return CompareResult(
        ok=ok,
        diffs=diffs,
        totals=actual_totals,
        baseline_totals=baseline_totals,
        constraint_violations=constraint_violations,
    )


def build_baseline_from_report(
    report: dict[str, Any],
    *,
    baseline_id: str,
    source_report: str,
    short_page_limit: int = 25,
) -> dict[str, Any]:
    """Build a committed baseline payload from a full batch report."""
    import time

    paper_ids = list(report.get("paper_ids") or [])
    results = report.get("results") or {}
    totals = summarize_report(report, short_page_limit=short_page_limit)

    papers: dict[str, Any] = {}
    for paper_id in paper_ids:
        row = results.get(paper_id)
        if not isinstance(row, dict):
            continue
        pages = row.get("pages")
        pages_int = pages if isinstance(pages, int) else None
        quality = extract_paper_quality_from_report(
            row,
            pages=pages_int,
            short_page_limit=short_page_limit,
        )
        papers[paper_id] = {
            "pages": pages_int,
            "route": "short" if pages_int is not None and pages_int <= short_page_limit else "long",
            "quality": {
                "pymupdf_sync": quality["pymupdf_sync"],
                "path_b": quality["path_b"],
                "dual_route_rules": quality["dual_route_rules"],
            },
        }

    payload: dict[str, Any] = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "baseline_id": baseline_id,
        "source_report": source_report,
        "recorded_at": report.get("generated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "paper_ids": paper_ids,
        "totals": {
            "pymupdf_sync": totals.pymupdf_sync,
            "path_b": totals.path_b,
            "dual_route_rules": totals.dual_route_rules,
            "max": totals.max_total,
        },
        "constraints": {
            "dual_gte_pymupdf": True,
            "dual_gte_path_b": True,
        },
        "papers": papers,
    }
    validate_baseline(payload)
    return payload


def write_baseline(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or DEFAULT_BASELINE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
