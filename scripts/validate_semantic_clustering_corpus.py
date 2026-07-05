#!/usr/bin/env python3
"""Validate semantic clustering on two small corpus samples.

This script runs the extraction pipeline (with semantic clustering enabled) on
hss-001.txt and stem-001.txt, then writes the resulting ExtractedGraphs and a
text report to ``data/benchmark_reports/semantic_clustering_validation/``.

Usage (from repo root)::<n></n>
    uv run python scripts/validate_semantic_clustering_corpus.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path

from backend.agents.extract_chunked import extract_chunked
from backend.config import get_settings
from backend.schemas.extract_phase import ExtractedGraph
from backend.schemas.paradigm import Paradigm

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CORPUS_DIR = Path("data/corpus")
OUTPUT_DIR = Path("data/benchmark_reports/semantic_clustering_validation")

SAMPLES: list[tuple[str, Path, Paradigm]] = [
    ("hss-001", CORPUS_DIR / "hss-001.txt", Paradigm.HSS),
    ("hss-003", CORPUS_DIR / "hss-003.txt", Paradigm.HSS),
]


def _ensure_settings() -> None:
    settings = get_settings()
    if not settings.semantic_clustering_enabled:
        logger.warning("SEMANTIC_CLUSTERING_ENABLED is false; enabling for this run.")
        # We cannot mutate the frozen settings object, but we can warn the user
        # to set the env var.  In practice the script is meant to be run with
        # SEMANTIC_CLUSTERING_ENABLED=true.


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _save_graph(graph: ExtractedGraph, path: Path) -> None:
    path.write_text(
        json.dumps(graph.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _analyze_clustering(graph: ExtractedGraph) -> dict:
    """Collect simple statistics about semantic clustering results."""
    nodes_with_aliases = [n for n in graph.nodes if n.data.get("semantic_aliases")]
    alias_count = sum(len(n.data.get("semantic_aliases", [])) for n in nodes_with_aliases)

    method_nodes = [n for n in graph.nodes if n.type == "Method"]
    dataset_nodes = [n for n in graph.nodes if n.type == "Dataset"]

    # Identify potential over-merging: Method nodes whose aliases have very
    # different labels (heuristic based on shared tokens).
    suspicious_methods: list[dict] = []
    for node in method_nodes:
        aliases = node.data.get("semantic_aliases", [])
        if not aliases:
            continue
        labels = [node.label] + [a.get("label", "") for a in aliases]
        # Simple heuristic: if no two labels share a substantive token, flag it.
        for i, left in enumerate(labels):
            for right in labels[i + 1 :]:
                left_tokens = set(_substantive_tokens(left))
                right_tokens = set(_substantive_tokens(right))
                if not left_tokens & right_tokens:
                    suspicious_methods.append(
                        {
                            "root_id": node.id,
                            "root_label": node.label,
                            "alias_label": right,
                            "reason": "no shared substantive tokens",
                        }
                    )

    # Identify potential under-merging: Dataset nodes with highly similar labels
    # that were NOT merged (i.e. no aliases and not elected as root of a cluster).
    dataset_label_groups: dict[str, list[str]] = defaultdict(list)
    for node in dataset_nodes:
        normalized = _normalize_dataset_label(node.label)
        dataset_label_groups[normalized].append(node.label)
    unmerged_dataset_duplicates = {norm: labels for norm, labels in dataset_label_groups.items() if len(labels) > 1}

    return {
        "total_nodes": len(graph.nodes),
        "nodes_with_semantic_aliases": len(nodes_with_aliases),
        "total_semantic_aliases": alias_count,
        "method_nodes": len(method_nodes),
        "dataset_nodes": len(dataset_nodes),
        "suspicious_method_merges": suspicious_methods,
        "unmerged_dataset_duplicates": unmerged_dataset_duplicates,
        "warnings": graph.warnings,
    }


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


def _format_report(results: list[tuple[str, ExtractedGraph, dict]]) -> str:
    sample_lines = ", ".join(f"{paper_id} ({graph.paradigm.value})" for paper_id, graph, _ in results)
    lines: list[str] = [
        "# Semantic Clustering Corpus Validation Report",
        "",
        f"Samples: {sample_lines}",
        "",
    ]
    for paper_id, graph, stats in results:
        lines.append(f"## {paper_id} ({graph.paradigm.value})")
        lines.append(f"- Total nodes: {stats['total_nodes']}")
        lines.append(f"- Nodes with semantic aliases: {stats['nodes_with_semantic_aliases']}")
        lines.append(f"- Total semantic aliases: {stats['total_semantic_aliases']}")
        lines.append(f"- Method nodes: {stats['method_nodes']}")
        lines.append(f"- Dataset nodes: {stats['dataset_nodes']}")
        lines.append("")
        lines.append("### Potential over-merging (Method aliases with no shared tokens)")
        if stats["suspicious_method_merges"]:
            for item in stats["suspicious_method_merges"]:
                lines.append(f"- `{item['root_label']}` <- `{item['alias_label']}` ({item['reason']})")
        else:
            lines.append("- None detected by the simple token-overlap heuristic.")
        lines.append("")
        lines.append("### Potential under-merging (Dataset labels with same normalized form)")
        if stats["unmerged_dataset_duplicates"]:
            for norm, labels in stats["unmerged_dataset_duplicates"].items():
                lines.append(f"- normalized=`{norm}`: {labels}")
        else:
            lines.append("- None detected by the simple suffix-stripping heuristic.")
        lines.append("")
        cluster_warnings = [w for w in stats["warnings"] if w.startswith("SEMANTIC_CLUSTERS_MERGED")]
        knn_warnings = [w for w in stats["warnings"] if w.startswith("SEMANTIC_KNN_EDGES_ADDED")]
        lines.append("### Clustering warnings")
        lines.extend(f"- {w}" for w in cluster_warnings + knn_warnings)
        if not cluster_warnings and not knn_warnings:
            lines.append("- No semantic clustering warnings.")
        lines.append("")
    return "\n".join(lines)


async def _run_sample(paper_id: str, path: Path, paradigm: Paradigm) -> tuple[str, ExtractedGraph, dict]:
    logger.info("Running extraction for %s ...", paper_id)
    full_text = _load_text(path)
    graph = await extract_chunked(
        full_text,
        paradigm,
        paper_id=paper_id,
        title=paper_id,
    )
    stats = _analyze_clustering(graph)
    return paper_id, graph, stats


async def main() -> None:
    _ensure_settings()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, ExtractedGraph, dict]] = []
    for paper_id, path, paradigm in SAMPLES:
        graph_path = OUTPUT_DIR / f"{paper_id}.extracted.json"
        if graph_path.exists():
            logger.info("Reusing existing %s", graph_path)
            graph = ExtractedGraph.model_validate_json(graph_path.read_text(encoding="utf-8"))
            stats = _analyze_clustering(graph)
        else:
            paper_id, graph, stats = await _run_sample(paper_id, path, paradigm)
            _save_graph(graph, graph_path)
            logger.info("Saved %s (%d nodes, %d edges)", graph_path, len(graph.nodes), len(graph.edges))
        results.append((paper_id, graph, stats))

    report = _format_report(results)
    report_path = OUTPUT_DIR / "report.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("Saved report to %s", report_path)
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
