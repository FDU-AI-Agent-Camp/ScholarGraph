#!/usr/bin/env python3
"""Run the full upload pipeline on short + long corpus samples and evaluate semantic clustering.

Reuses the production path: ``PaperService.create_from_upload`` → LangGraph pipeline
(including async head refine, paradigm classification, two-phase extraction, and semantic
clustering for long papers) → poll status until ready/failed → load graph from GraphStore.

Outputs:
- Persisted graphs under ``data/graphs/`` (normal pipeline artifact).
- Evaluation JSON + Markdown report under
  ``data/benchmark_reports/pipeline_semantic_clustering/``.

Usage (from repo root)::<n></n>
    uv run python scripts/eval_pipeline_semantic_clustering.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.services.extract_worker import get_full_extraction_task
from backend.services.paper_service import PaperService, get_paper_service

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
OUTPUT_DIR = REPO_ROOT / "data" / "benchmark_reports" / "pipeline_semantic_clustering"

SAMPLES: list[tuple[str, Path]] = [
    ("hss-001", CORPUS_DIR / "hss-001.pdf"),
    ("hss-003", CORPUS_DIR / "hss-003.pdf"),
    ("hss-002", CORPUS_DIR / "hss-002.pdf"),
]

POLL_INTERVAL_SECONDS = 2.0
MAX_POLL_SECONDS = 14400  # 4 hours; long-paper chunked extraction may take a while.


def _substantive_tokens(text: str) -> list[str]:
    """Return lowercase alphanumeric tokens, dropping short/common words."""
    stop = {"的", "与", "和", "在", "了", "是", "方法", "框架", "构建", "技术", "基于"}
    tokens = []
    for token in text.lower().replace("+", " ").split():
        token = "".join(c for c in token if c.isalnum() or "\u4e00" <= c <= "\u9fff")
        if len(token) > 1 and token not in stop:
            tokens.append(token)
    return tokens


def _normalize_dataset_label(label: str) -> str:
    """Strip common suffixes/noise from dataset labels for grouping."""
    label = label.strip()
    for suffix in ("数据", "数据集", "语料", "语料库", "样本"):
        if label.endswith(suffix):
            label = label[: -len(suffix)].strip()
    return label


def _analyze_clustering(graph: UnifiedPaperGraph) -> dict:
    """Collect statistics about semantic clustering results."""
    nodes_with_aliases = [n for n in graph.nodes if n.data.get("semantic_aliases")]
    alias_count = sum(len(n.data.get("semantic_aliases", [])) for n in nodes_with_aliases)

    method_nodes = [n for n in graph.nodes if n.type == "Method"]
    dataset_nodes = [n for n in graph.nodes if n.type == "Dataset"]
    concept_nodes = [n for n in graph.nodes if n.type == "Concept"]
    thesis_nodes = [n for n in graph.nodes if n.type == "Thesis"]
    claim_nodes = [n for n in graph.nodes if n.type == "Claim"]

    suspicious_methods: list[dict] = []
    for node in method_nodes:
        aliases = node.data.get("semantic_aliases", [])
        if not aliases:
            continue
        labels = [node.label] + [a.get("label", "") for a in aliases]
        for i, left in enumerate(labels):
            for right in labels[i + 1 :]:
                if not set(_substantive_tokens(left)) & set(_substantive_tokens(right)):
                    suspicious_methods.append(
                        {
                            "root_id": node.id,
                            "root_label": node.label,
                            "alias_label": right,
                            "reason": "no shared substantive tokens",
                        }
                    )

    suspicious_theses: list[dict] = []
    for node in thesis_nodes:
        aliases = node.data.get("semantic_aliases", [])
        if not aliases:
            continue
        labels = [node.label] + [a.get("label", "") for a in aliases]
        for i, left in enumerate(labels):
            for right in labels[i + 1 :]:
                if not set(_substantive_tokens(left)) & set(_substantive_tokens(right)):
                    suspicious_theses.append(
                        {
                            "root_id": node.id,
                            "root_label": node.label,
                            "alias_label": right,
                            "reason": "no shared substantive tokens",
                        }
                    )

    dataset_label_groups: dict[str, list[str]] = defaultdict(list)
    for node in dataset_nodes:
        normalized = _normalize_dataset_label(node.label)
        dataset_label_groups[normalized].append(node.label)
    unmerged_dataset_duplicates = {
        norm: labels for norm, labels in dataset_label_groups.items() if len(labels) > 1
    }

    return {
        "total_nodes": len(graph.nodes),
        "total_edges": len(graph.edges),
        "nodes_with_semantic_aliases": len(nodes_with_aliases),
        "total_semantic_aliases": alias_count,
        "method_nodes": len(method_nodes),
        "dataset_nodes": len(dataset_nodes),
        "concept_nodes": len(concept_nodes),
        "thesis_nodes": len(thesis_nodes),
        "claim_nodes": len(claim_nodes),
        "suspicious_method_merges": suspicious_methods,
        "suspicious_thesis_merges": suspicious_theses,
        "unmerged_dataset_duplicates": unmerged_dataset_duplicates,
        "thesis_clusters": [
            {
                "root_id": n.id,
                "root_label": n.label,
                "alias_count": len(n.data.get("semantic_aliases", [])),
                "aliases": [a.get("label", "") for a in n.data.get("semantic_aliases", [])],
            }
            for n in thesis_nodes
            if n.data.get("semantic_aliases")
        ],
    }


async def _wait_for_ready(service: PaperService, paper_id: str) -> PaperStatus:
    """Poll paper status until terminal or timeout."""
    deadline = time.monotonic() + MAX_POLL_SECONDS
    while time.monotonic() < deadline:
        status_data = await service.get_status(paper_id)
        if status_data.status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS, PaperStatus.FAILED):
            return status_data.status
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return PaperStatus.FAILED


async def _run_sample(paper_id: str, pdf_path: Path, service: PaperService) -> dict:
    """Upload a PDF through the production service and wait for the pipeline."""
    logger.info("[%s] Uploading %s ...", paper_id, pdf_path.name)
    content = pdf_path.read_bytes()
    result = await service.create_from_upload(filename=pdf_path.name, content=content)
    assigned_id = result.paper_id

    logger.info("[%s] Pipeline started, polling status ...", paper_id)
    started = time.perf_counter()
    final_status = await _wait_for_ready(service, assigned_id)
    elapsed = time.perf_counter() - started

    status_data = await service.get_status(assigned_id)
    detail = await service.get_paper(assigned_id)

    record = {
        "paper_id": assigned_id,
        "sample_id": paper_id,
        "status": final_status.value,
        "percent": status_data.percent,
        "stage": status_data.stage.value if status_data.stage else None,
        "message": status_data.message,
        "error_code": status_data.error_code,
        "failed_during": status_data.failed_during.value if status_data.failed_during else None,
        "elapsed_seconds": round(elapsed, 2),
        "paradigm": detail.paradigm.value if detail.paradigm else None,
        "extract_warnings": detail.extract_warnings,
        "classify_warnings": detail.classify_warnings,
        "ingest_head": (
            {
                "title": detail.ingest_head.title,
                "abstract": (
                    detail.ingest_head.abstract[:200] + "..."
                    if len(detail.ingest_head.abstract) > 200
                    else detail.ingest_head.abstract
                ),
                "keywords": detail.ingest_head.keywords,
                "intro": (
                    detail.ingest_head.intro[:200] + "..."
                    if len(detail.ingest_head.intro) > 200
                    else detail.ingest_head.intro
                ),
            }
            if detail.ingest_head else None
        ),
        "graph": None,
        "clustering": None,
    }

    if final_status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS):
        graph = service.get_preview_graph(assigned_id) or GraphStore().load(assigned_id)
        if graph is not None:
            record["graph"] = {
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "nodes": [
                    {"id": n.id, "label": n.label, "type": n.type, "data": n.data}
                    for n in graph.nodes
                ],
                "edges": [
                    {"id": e.id, "source": e.source, "target": e.target, "type": e.type}
                    for e in graph.edges
                ],
            }
            record["clustering"] = _analyze_clustering(graph)

    return record


def _format_report(records: list[dict]) -> str:
    """Build a Markdown report from evaluation records."""
    lines: list[str] = [
        "# Pipeline Semantic Clustering Evaluation Report",
        "",
        f"Samples: {', '.join(r['sample_id'] for r in records)}",
        "",
    ]
    for r in records:
        lines.append(f"## {r['sample_id']} ({r['paradigm']})")
        lines.append(f"- Assigned paper_id: `{r['paper_id']}`")
        lines.append(f"- Final status: `{r['status']}`")
        lines.append(f"- Elapsed: {r['elapsed_seconds']:.2f}s")
        lines.append(f"- Stage: {r['stage']}")
        lines.append(f"- Message: {r['message']}")
        if r["error_code"]:
            lines.append(f"- Error code: `{r['error_code']}`")
        if r["failed_during"]:
            lines.append(f"- Failed during: `{r['failed_during']}`")
        lines.append("")

        graph = r.get("graph")
        if graph:
            lines.append(f"- Nodes: {graph['node_count']}")
            lines.append(f"- Edges: {graph['edge_count']}")
        clustering = r.get("clustering")
        if clustering:
            lines.append(f"- Nodes with semantic aliases: {clustering['nodes_with_semantic_aliases']}")
            lines.append(f"- Total semantic aliases: {clustering['total_semantic_aliases']}")
            lines.append(f"- Method nodes: {clustering['method_nodes']}")
            lines.append(f"- Dataset nodes: {clustering['dataset_nodes']}")
            lines.append(f"- Concept nodes: {clustering['concept_nodes']}")
            lines.append(f"- Thesis nodes: {clustering['thesis_nodes']}")
            lines.append(f"- Claim nodes: {clustering['claim_nodes']}")
        lines.append("")

        if r["extract_warnings"]:
            lines.append("### Extract warnings")
            for w in r["extract_warnings"]:
                lines.append(f"- `{w}`")
            lines.append("")
        if r["classify_warnings"]:
            lines.append("### Classify warnings")
            for w in r["classify_warnings"]:
                lines.append(f"- `{w}`")
            lines.append("")
        if r["ingest_head"]:
            lines.append("### Refined ingest head")
            head = r["ingest_head"]
            lines.append(f"- Title: `{head['title']}`")
            lines.append(f"- Keywords: `{head['keywords']}`")
            lines.append("")

        if clustering:
            lines.append("### Thesis clusters")
            for item in clustering["thesis_clusters"]:
                lines.append(
                    f"- `{item['root_label']}` ({item['alias_count']} aliases): {item['aliases']}"
                )
            if not clustering["thesis_clusters"]:
                lines.append("- None")
            lines.append("")

            lines.append("### Potential over-merging (Method aliases with no shared tokens)")
            if clustering["suspicious_method_merges"]:
                for item in clustering["suspicious_method_merges"]:
                    lines.append(f"- `{item['root_label']}` <- `{item['alias_label']}` ({item['reason']})")
            else:
                lines.append("- None detected by the simple token-overlap heuristic.")
            lines.append("")

            lines.append("### Potential over-merging (Thesis aliases with no shared tokens)")
            if clustering["suspicious_thesis_merges"]:
                for item in clustering["suspicious_thesis_merges"]:
                    lines.append(f"- `{item['root_label']}` <- `{item['alias_label']}` ({item['reason']})")
            else:
                lines.append("- None detected by the simple token-overlap heuristic.")
            lines.append("")

            lines.append("### Potential under-merging (Dataset labels with same normalized form)")
            if clustering["unmerged_dataset_duplicates"]:
                for norm, labels in clustering["unmerged_dataset_duplicates"].items():
                    lines.append(f"- normalized=`{norm}`: {labels}")
            else:
                lines.append("- None detected by the simple suffix-stripping heuristic.")
            lines.append("")

    return "\n".join(lines)


async def main() -> int:
    settings = get_settings()
    if not settings.semantic_clustering_enabled:
        logger.warning("SEMANTIC_CLUSTERING_ENABLED is false; this script expects it to be true.")
    if settings.is_llm_mock:
        logger.warning("LLM_MODE is mock; results will be fixture-based and not meaningful for clustering eval.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clear any stale full-extraction task references so each run is independent.
    from backend.services.extract_worker import reset_extract_worker

    reset_extract_worker()

    service = get_paper_service()
    records: list[dict] = []

    for sample_id, pdf_path in SAMPLES:
        if not pdf_path.is_file():
            logger.error("[%s] PDF not found: %s", sample_id, pdf_path)
            records.append(
                {
                    "sample_id": sample_id,
                    "status": "missing_pdf",
                    "error": f"PDF not found: {pdf_path}",
                }
            )
            continue

        record = await _run_sample(sample_id, pdf_path, service)
        records.append(record)

        # Wait for any background extraction task to fully finish before moving on,
        # so the next upload starts from a clean scheduling state.
        task = get_full_extraction_task(record["paper_id"])
        if task is not None and not task.done():
            logger.info("[%s] Waiting for background extraction task ...", sample_id)
            try:
                await asyncio.wait_for(task, timeout=MAX_POLL_SECONDS)
            except TimeoutError:
                logger.warning("[%s] Background extraction still running after timeout", sample_id)

    json_path = OUTPUT_DIR / "records.json"
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved records to %s", json_path)

    report = _format_report(records)
    report_path = OUTPUT_DIR / "report.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("Saved report to %s", report_path)
    print("\n" + report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
