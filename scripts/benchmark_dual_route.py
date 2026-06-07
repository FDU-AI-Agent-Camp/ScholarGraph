#!/usr/bin/env python3
"""Compare dual-route ingest (§2.1) vs single-parser baselines on golden corpus.

Quality: classifier 四段 0–4 分（与 progress.md §2.2 同一套启发式规则）。
Speed: wall-clock per path.

Usage (repo root):
    uv run python scripts/benchmark_dual_route.py
    uv run python scripts/benchmark_dual_route.py --with-llm
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import Settings, get_settings
from backend.ingest.grobid_client import fetch_grobid_tei
from backend.ingest.head_candidates import HeadCandidate, build_pymupdf_head_candidate
from backend.ingest.head_merge import merge_with_llm, merge_with_rules
from backend.ingest.mineru_backend import is_mineru_available, run_mineru_pipeline
from backend.ingest.pdf import ingest_pdf
from backend.ingest.router import get_pdf_page_count, is_short_pdf, resolve_ingest_route
from backend.ingest.snippets import ClassifierSections, parse_classifier_sections
from backend.ingest.tei_parser import parse_tei_to_head_candidate
from backend.schemas.ingest_head import IngestHead
from scripts.benchmark_regression import (  # noqa: E402
    build_baseline_from_report,
    compare_report_to_baseline,
)
from scripts.benchmark_regression import (
    write_baseline as persist_baseline,
)

CORPUS_DIR = REPO_ROOT / "data" / "corpus"
CORPUS_IDS = ("stem-001", "hss-001", "hss-002")
REPORT_DIR = REPO_ROOT / "data" / "benchmark_reports"


def list_corpus_paper_ids(*, all_corpus: bool = False) -> tuple[str, ...]:
    """Return golden trio or all local PDF stems (excluding ``_probe*``)."""
    if not all_corpus:
        return CORPUS_IDS
    ids = sorted(
        path.stem for path in CORPUS_DIR.glob("*.pdf") if path.is_file() and not path.stem.startswith("_probe")
    )
    return tuple(ids)


TITLE_POLLUTION = re.compile(
    r"(学号|密级|doi:|https?://|university of|received:|accepted:)",
    re.IGNORECASE,
)


@dataclass
class QualityScore:
    total: int
    title: bool
    abstract: bool
    keywords: bool
    intro: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class PathResult:
    label: str
    elapsed_seconds: float
    sections: ClassifierSections
    quality: QualityScore
    sources: dict[str, str] = field(default_factory=dict)


def score_sections(sections: ClassifierSections, *, paper_id: str) -> QualityScore:
    """Heuristic 0–4 scoring aligned with historical golden benchmark."""
    notes: list[str] = []
    title_ok = bool(sections.title.strip()) and len(sections.title.strip()) >= 8
    if title_ok and TITLE_POLLUTION.search(sections.title):
        title_ok = False
        notes.append("title_polluted")

    abstract = sections.abstract.strip()
    abstract_ok = len(abstract) >= 80
    if paper_id == "hss-001" and abstract.startswith("前就"):
        abstract_ok = False
        notes.append("abstract_wrong_cut")
    if paper_id == "stem-001" and abstract_ok:
        lower = abstract.lower()
        if "atomic embedding" not in lower and "crystal" not in lower and "materials project" not in lower:
            abstract_ok = len(abstract) >= 200
            if not abstract_ok:
                notes.append("abstract_not_canonical")
    if paper_id == "hss-002" and abstract_ok and len(abstract) < 120:
        notes.append("abstract_short")

    keywords_ok = len(sections.keywords.strip()) >= 2
    intro_ok = len(sections.intro.strip()) >= 40

    parts = [title_ok, abstract_ok, keywords_ok, intro_ok]
    return QualityScore(
        total=sum(parts),
        title=title_ok,
        abstract=abstract_ok,
        keywords=keywords_ok,
        intro=intro_ok,
        notes=notes,
    )


def sections_from_head(head: IngestHead | HeadCandidate) -> ClassifierSections:
    return ClassifierSections(
        title=head.title,
        abstract=head.abstract,
        keywords=head.keywords,
        intro=head.intro,
    )


def sections_from_classifier_input(text: str) -> ClassifierSections:
    return parse_classifier_sections(text)


async def run_pymupdf_sync(pdf_path: Path) -> PathResult:
    started = time.perf_counter()
    result = await ingest_pdf(pdf_path, paper_id=pdf_path.stem)
    elapsed = time.perf_counter() - started
    sections = sections_from_classifier_input(result["classifier_input"])
    return PathResult(
        label="pymupdf_sync",
        elapsed_seconds=elapsed,
        sections=sections,
        quality=score_sections(sections, paper_id=pdf_path.stem),
    )


async def run_grobid_path(pdf_path: Path, settings: Settings) -> PathResult | None:
    started = time.perf_counter()
    tei = await fetch_grobid_tei(pdf_path, settings=settings)
    if not tei:
        return None
    candidate = parse_tei_to_head_candidate(tei)
    elapsed = time.perf_counter() - started
    sections = sections_from_head(candidate)
    return PathResult(
        label="grobid_crf",
        elapsed_seconds=elapsed,
        sections=sections,
        quality=score_sections(sections, paper_id=pdf_path.stem),
        sources={"route": "grobid"},
    )


def run_mineru_path(pdf_path: Path, settings: Settings) -> PathResult | None:
    if not is_mineru_available():
        return None
    started = time.perf_counter()
    candidate = run_mineru_pipeline(pdf_path, settings=settings)
    if candidate is None:
        return None
    elapsed = time.perf_counter() - started
    sections = sections_from_head(candidate)
    return PathResult(
        label="mineru_pipeline",
        elapsed_seconds=elapsed,
        sections=sections,
        quality=score_sections(sections, paper_id=pdf_path.stem),
        sources={"route": "mineru"},
    )


async def run_dual_route_rules(
    pdf_path: Path,
    settings: Settings,
    *,
    grobid: PathResult | None,
    mineru: PathResult | None,
) -> PathResult:
    started = time.perf_counter()
    snippets = build_pymupdf_head_candidate(pdf_path)
    page_count = get_pdf_page_count(pdf_path)
    short = is_short_pdf(page_count, settings=settings)
    path_b: HeadCandidate | None = None
    if short and mineru is not None:
        path_b = HeadCandidate(
            title=mineru.sections.title,
            abstract=mineru.sections.abstract,
            keywords=mineru.sections.keywords,
            intro=mineru.sections.intro,
            source="mineru",
        )
    elif not short and grobid is not None:
        path_b = HeadCandidate(
            title=grobid.sections.title,
            abstract=grobid.sections.abstract,
            keywords=grobid.sections.keywords,
            intro=grobid.sections.intro,
            source="grobid",
        )
    merged = merge_with_rules(snippets, path_b, is_short=short)
    elapsed = time.perf_counter() - started
    sections = sections_from_head(merged)
    return PathResult(
        label="dual_route_rules",
        elapsed_seconds=elapsed,
        sections=sections,
        quality=score_sections(sections, paper_id=pdf_path.stem),
        sources=merged.sources,
    )


async def run_dual_route_llm(
    pdf_path: Path,
    settings: Settings,
    *,
    grobid: PathResult | None,
    mineru: PathResult | None,
) -> PathResult | None:
    if settings.is_llm_mock or not settings.ingest_head_llm_enabled:
        return None
    if not settings.scholargraph_api_key.strip():
        return None
    started = time.perf_counter()
    snippets = build_pymupdf_head_candidate(pdf_path)
    page_count = get_pdf_page_count(pdf_path)
    short = is_short_pdf(page_count, settings=settings)
    path_b: HeadCandidate | None = None
    if short and mineru is not None:
        path_b = HeadCandidate(
            title=mineru.sections.title,
            abstract=mineru.sections.abstract,
            keywords=mineru.sections.keywords,
            intro=mineru.sections.intro,
            source="mineru",
        )
    elif not short and grobid is not None:
        path_b = HeadCandidate(
            title=grobid.sections.title,
            abstract=grobid.sections.abstract,
            keywords=grobid.sections.keywords,
            intro=grobid.sections.intro,
            source="grobid",
        )
    merged = await merge_with_llm(snippets, path_b, is_short=short, settings=settings)
    elapsed = time.perf_counter() - started
    sections = sections_from_head(merged)
    return PathResult(
        label="dual_route_llm",
        elapsed_seconds=elapsed,
        sections=sections,
        quality=score_sections(sections, paper_id=pdf_path.stem),
        sources=merged.sources,
    )


def fmt_score(result: PathResult | None) -> str:
    if result is None:
        return "—"
    return f"{result.quality.total}/4"


def print_report(all_results: dict[str, dict[str, PathResult | None]]) -> None:
    historical = {
        "stem-001": {"pymupdf": "2/4", "mineru": "3/4", "grobid": "3/4"},
        "hss-001": {"pymupdf": "3/4", "mineru": "4/4", "grobid": "0/4"},
        "hss-002": {"pymupdf": "2/4", "mineru": "2/4", "grobid": "4/4"},
    }
    print("\n## Golden corpus — quality (classifier 四段 0–4)\n")
    print(
        "| 语料 | 页数 | 路由 | 历史 PyMuPDF | 现 PyMuPDF | 历史 path-B | 现 path-B | 现 dual(rules) | 现 dual(LLM) |"
    )
    print("|------|------|------|-------------|-----------|------------|----------|----------------|-------------|")
    totals: dict[str, int] = {
        "pymupdf_now": 0,
        "path_b_now": 0,
        "dual_rules": 0,
        "dual_llm": 0,
    }
    for paper_id in CORPUS_IDS:
        pdf = CORPUS_DIR / f"{paper_id}.pdf"
        pages = get_pdf_page_count(pdf)
        route = resolve_ingest_route(pages)
        route_label = "短" if route and route.value == "short" else "长"
        row = all_results[paper_id]
        pym = row.get("pymupdf_sync")
        path_b_key = "mineru_pipeline" if pages <= 25 else "grobid_crf"
        path_b = row.get(path_b_key)
        dual_r = row.get("dual_route_rules")
        dual_l = row.get("dual_route_llm")
        hist_b = historical[paper_id]["mineru" if pages <= 25 else "grobid"]
        if pym:
            totals["pymupdf_now"] += pym.quality.total
        if path_b:
            totals["path_b_now"] += path_b.quality.total
        if dual_r:
            totals["dual_rules"] += dual_r.quality.total
        if dual_l:
            totals["dual_llm"] += dual_l.quality.total
        print(
            f"| {paper_id} | {pages} | {route_label} | {historical[paper_id]['pymupdf']} | "
            f"{fmt_score(pym)} | {hist_b} | {fmt_score(path_b)} | {fmt_score(dual_r)} | {fmt_score(dual_l)} |"
        )
    print(
        f"\n**合计（现测）**：PyMuPDF {totals['pymupdf_now']}/12 · path-B {totals['path_b_now']}/12 · "
        f"dual rules {totals['dual_rules']}/12 · dual LLM {totals['dual_llm']}/12"
    )

    print("\n## Speed (seconds, this machine)\n")
    print("| 语料 | PyMuPDF 同步 | path-B | dual rules | dual LLM | 上传感知* |")
    print("|------|-------------|--------|------------|----------|----------|")
    for paper_id in CORPUS_IDS:
        row = all_results[paper_id]
        pdf = CORPUS_DIR / f"{paper_id}.pdf"
        pages = get_pdf_page_count(pdf)
        path_b_key = "mineru_pipeline" if pages <= 25 else "grobid_crf"
        sync = row.get("pymupdf_sync")
        path_b = row.get(path_b_key)
        dual_r = row.get("dual_route_rules")
        dual_l = row.get("dual_route_llm")
        upload = sync.elapsed_seconds if sync else 0.0
        print(
            f"| {paper_id} | {sync.elapsed_seconds if sync else '—':.2f} | "
            f"{path_b.elapsed_seconds if path_b else '—'} | "
            f"{dual_r.elapsed_seconds if dual_r else '—'} | "
            f"{dual_l.elapsed_seconds if dual_l else '—'} | **{upload:.2f}** |"
        )
    print("\n*上传感知 = 仅 PyMuPDF 同步 ingest；path-B 与 merge 为异步后台。")


def print_batch_report(all_results: dict[str, dict[str, PathResult | None]], paper_ids: tuple[str, ...]) -> None:
    """Full-corpus quality + speed summary (§2.1 batch benchmark)."""
    n = len(paper_ids)
    max_total = n * 4
    print(f"\n## Full corpus batch ({n} PDFs) — quality (classifier 四段 0–4)\n")
    print("| 语料 | 页数 | 路由 | PyMuPDF | path-B | dual(rules) | dual(LLM) |")
    print("|------|------|------|---------|--------|-------------|-----------|")

    totals: dict[str, int] = {
        "pymupdf_sync": 0,
        "path_b": 0,
        "dual_route_rules": 0,
        "dual_route_llm": 0,
    }
    path_b_ok = 0
    speed_totals: dict[str, float] = {
        "pymupdf_sync": 0.0,
        "path_b": 0.0,
        "dual_route_rules": 0.0,
        "dual_route_llm": 0.0,
    }
    speed_counts: dict[str, int] = {
        "pymupdf_sync": 0,
        "path_b": 0,
        "dual_route_rules": 0,
        "dual_route_llm": 0,
    }

    for paper_id in paper_ids:
        pdf = CORPUS_DIR / f"{paper_id}.pdf"
        if paper_id not in all_results:
            print(f"| {paper_id} | — | — | SKIP | SKIP | SKIP | SKIP |")
            continue
        pages = get_pdf_page_count(pdf)
        short = pages <= 25
        route_label = "短" if short else "长"
        row = all_results[paper_id]
        pym = row.get("pymupdf_sync")
        path_b_key = "mineru_pipeline" if short else "grobid_crf"
        path_b = row.get(path_b_key)
        dual_r = row.get("dual_route_rules")
        dual_l = row.get("dual_route_llm")
        if pym:
            totals["pymupdf_sync"] += pym.quality.total
            speed_totals["pymupdf_sync"] += pym.elapsed_seconds
            speed_counts["pymupdf_sync"] += 1
        if path_b:
            totals["path_b"] += path_b.quality.total
            speed_totals["path_b"] += path_b.elapsed_seconds
            speed_counts["path_b"] += 1
            path_b_ok += 1
        if dual_r:
            totals["dual_route_rules"] += dual_r.quality.total
            speed_totals["dual_route_rules"] += dual_r.elapsed_seconds
            speed_counts["dual_route_rules"] += 1
        if dual_l:
            totals["dual_route_llm"] += dual_l.quality.total
            speed_totals["dual_route_llm"] += dual_l.elapsed_seconds
            speed_counts["dual_route_llm"] += 1
        print(
            f"| {paper_id} | {pages} | {route_label} | {fmt_score(pym)} | "
            f"{fmt_score(path_b)} | {fmt_score(dual_r)} | {fmt_score(dual_l)} |"
        )

    print(
        f"\n**质量合计**：PyMuPDF {totals['pymupdf_sync']}/{max_total} · "
        f"path-B {totals['path_b']}/{max_total} ({path_b_ok}/{n} 成功) · "
        f"dual rules {totals['dual_route_rules']}/{max_total} · "
        f"dual LLM {totals['dual_route_llm']}/{max_total}"
    )

    def _avg(label: str) -> str:
        count = speed_counts[label]
        if count == 0:
            return "—"
        return f"{speed_totals[label] / count:.2f}s"

    print("\n## Speed summary (mean wall-clock per path)\n")
    print("| 路径 | 均值 | 合计 |")
    print("|------|------|------|")
    for label, title in (
        ("pymupdf_sync", "PyMuPDF 同步"),
        ("path_b", "path-B (MinerU/GROBID)"),
        ("dual_route_rules", "dual(rules)"),
        ("dual_route_llm", "dual(LLM)"),
    ):
        count = speed_counts[label]
        total = speed_totals[label]
        print(f"| {title} | {_avg(label)} | {total:.1f}s ({count} ok) |")

    # Head-to-head wins on quality total
    dual_wins = pym_wins = path_b_wins = 0
    ties = 0
    for paper_id in paper_ids:
        row = all_results.get(paper_id)
        if not row:
            continue
        pdf = CORPUS_DIR / f"{paper_id}.pdf"
        pages = get_pdf_page_count(pdf)
        path_b_key = "mineru_pipeline" if pages <= 25 else "grobid_crf"
        scores: dict[str, int] = {}
        if row.get("pymupdf_sync"):
            scores["pym"] = row["pymupdf_sync"].quality.total  # type: ignore[union-attr]
        if row.get(path_b_key):
            scores["path_b"] = row[path_b_key].quality.total  # type: ignore[union-attr]
        if row.get("dual_route_rules"):
            scores["dual"] = row["dual_route_rules"].quality.total  # type: ignore[union-attr]
        if len(scores) < 2:
            continue
        best = max(scores.values())
        winners = [k for k, v in scores.items() if v == best]
        if len(winners) > 1:
            ties += 1
        elif winners[0] == "dual":
            dual_wins += 1
        elif winners[0] == "pym":
            pym_wins += 1
        else:
            path_b_wins += 1

    print(
        f"\n**逐篇质量领先**（PyMuPDF vs path-B vs dual rules）："
        f"dual {dual_wins} · path-B {path_b_wins} · PyMuPDF {pym_wins} · 并列 {ties}"
    )
    print("\n*path-B = 短档 MinerU / 长档 GROBID；上传感知 = PyMuPDF 同步耗时。")


def save_batch_json(
    all_results: dict[str, dict[str, PathResult | None]],
    paper_ids: tuple[str, ...],
    *,
    output_path: Path,
) -> None:
    """Persist batch results for offline review."""
    import json
    from dataclasses import asdict

    payload: dict[str, object] = {
        "paper_ids": list(paper_ids),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": {},
    }
    results_payload: dict[str, object] = {}
    for paper_id in paper_ids:
        row = all_results.get(paper_id)
        if row is None:
            continue
        pdf = CORPUS_DIR / f"{paper_id}.pdf"
        pages = get_pdf_page_count(pdf) if pdf.is_file() else None
        entry: dict[str, object] = {"pages": pages}
        for key, result in row.items():
            if result is None:
                entry[key] = None
                continue
            entry[key] = {
                "elapsed_seconds": result.elapsed_seconds,
                "quality": asdict(result.quality),
                "sources": result.sources,
                "title_len": len(result.sections.title.strip()),
                "abstract_len": len(result.sections.abstract.strip()),
                "keywords_len": len(result.sections.keywords.strip()),
                "intro_len": len(result.sections.intro.strip()),
            }
        results_payload[paper_id] = entry
    payload["results"] = results_payload
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON report: {output_path}")


async def run_paper_comparison(
    pdf_path: Path,
    settings: Settings,
    *,
    with_llm: bool = False,
    skip_mineru_on_long: bool = False,
) -> dict[str, PathResult | None]:
    """
    Run one PDF through all benchmark paths (§2.1 dual-route comparison set).

    Keys: ``pymupdf_sync``, ``grobid_crf``, ``mineru_pipeline``,
    ``dual_route_rules``, ``dual_route_llm`` (None when LLM disabled or unavailable).
    """
    page_count = get_pdf_page_count(pdf_path)
    short = is_short_pdf(page_count, settings=settings)
    row: dict[str, PathResult | None] = {}
    row["pymupdf_sync"] = await run_pymupdf_sync(pdf_path)
    row["grobid_crf"] = await run_grobid_path(pdf_path, settings)
    if short or not skip_mineru_on_long:
        row["mineru_pipeline"] = run_mineru_path(pdf_path, settings)
    else:
        row["mineru_pipeline"] = None
    row["dual_route_rules"] = await run_dual_route_rules(
        pdf_path,
        settings,
        grobid=row["grobid_crf"],
        mineru=row["mineru_pipeline"],
    )
    if with_llm:
        row["dual_route_llm"] = await run_dual_route_llm(
            pdf_path,
            settings,
            grobid=row["grobid_crf"],
            mineru=row["mineru_pipeline"],
        )
    else:
        row["dual_route_llm"] = None
    return row


def build_benchmark_settings(*, with_llm: bool) -> Settings:
    """Settings for benchmark runs (mock LLM by default; live when ``with_llm``)."""
    settings = get_settings()
    if not with_llm:
        return Settings(
            _env_file=None,
            llm_mode="mock",
            ingest_head_llm_enabled=False,
            ingest_mineru_enabled=True,
            ingest_mineru_model_source=settings.ingest_mineru_model_source or "modelscope",
            ingest_mineru_timeout_seconds=settings.ingest_mineru_timeout_seconds,
            ingest_short_page_limit=settings.ingest_short_page_limit,
            ingest_route=settings.ingest_route,
            grobid_url=settings.grobid_url,
        )
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()
    return Settings(
        _env_file=None,
        llm_mode="live",
        scholargraph_api_key=settings.scholargraph_api_key or get_settings().scholargraph_api_key,
        llm_api_base_url=settings.llm_api_base_url,
        ingest_head_llm_enabled=True,
        ingest_mineru_enabled=True,
        ingest_mineru_model_source=settings.ingest_mineru_model_source or "modelscope",
        ingest_mineru_timeout_seconds=settings.ingest_mineru_timeout_seconds,
        ingest_short_page_limit=settings.ingest_short_page_limit,
        ingest_route=settings.ingest_route,
        grobid_url=settings.grobid_url,
    )


async def main(
    *,
    with_llm: bool,
    all_corpus: bool,
    compare_baseline: bool = False,
    write_baseline: bool = False,
) -> int:
    settings = build_benchmark_settings(with_llm=with_llm)
    paper_ids = list_corpus_paper_ids(all_corpus=all_corpus)
    if all_corpus and not paper_ids:
        print("No PDFs in data/corpus (excluding _probe*).")
        return 1

    all_results: dict[str, dict[str, PathResult | None]] = {}
    for index, paper_id in enumerate(paper_ids, start=1):
        pdf_path = CORPUS_DIR / f"{paper_id}.pdf"
        if not pdf_path.is_file():
            print(f"SKIP {paper_id}: missing PDF")
            continue
        print(f"[{index}/{len(paper_ids)}] Running {paper_id} ({get_pdf_page_count(pdf_path)} pages)...", flush=True)
        all_results[paper_id] = await run_paper_comparison(
            pdf_path,
            settings,
            with_llm=with_llm,
            skip_mineru_on_long=all_corpus,
        )

    if all_corpus:
        print_batch_report(all_results, paper_ids)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        report_path = REPORT_DIR / f"corpus-batch-{stamp}.json"
        save_batch_json(
            all_results,
            paper_ids,
            output_path=report_path,
        )
        import json

        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        if write_baseline:
            baseline_payload = build_baseline_from_report(
                report_payload,
                baseline_id="phase-d-dual-rules",
                source_report=report_path.name,
            )
            baseline_path = persist_baseline(baseline_payload)
            print(f"Baseline written: {baseline_path}")
        if compare_baseline:
            result = compare_report_to_baseline(report_payload)
            print("\n## Baseline regression\n")
            print(result.format_message())
            if not result.ok:
                return 1
    else:
        print_report(all_results)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-llm", action="store_true", help="Include live LLM merge (needs API key)")
    parser.add_argument(
        "--all-corpus",
        action="store_true",
        help="Run all data/corpus/*.pdf except _probe* (default: golden 3)",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="After --all-corpus, compare report to tests/fixtures/benchmark/dual_rules_baseline.json",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="After --all-corpus, refresh committed baseline JSON from this run",
    )
    args = parser.parse_args()
    if args.compare_baseline and not args.all_corpus:
        parser.error("--compare-baseline requires --all-corpus")
    if args.write_baseline and not args.all_corpus:
        parser.error("--write-baseline requires --all-corpus")
    raise SystemExit(
        asyncio.run(
            main(
                with_llm=args.with_llm,
                all_corpus=args.all_corpus,
                compare_baseline=args.compare_baseline,
                write_baseline=args.write_baseline,
            )
        )
    )
