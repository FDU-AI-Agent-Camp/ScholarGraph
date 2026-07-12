#!/usr/bin/env python
"""金标 QA ID 校验脚本 (V2 Phase 4).

遍历 ``data/qa_golden_set.json`` 中引用的 ``node_id``、``edge_id`` 与 chunk/paragraph ID，
校验是否仍存在于 ``data/graphs/`` 的图谱样本、``data/chunk_manifests/`` 与
``data/mock_vector_store.json`` 的 mock 向量索引中；并对 STEM detail 金标执行数值格式合规性检查。
发现过期引用或不符合分片命名规范的 ID 时以非零退出码退出。

Usage (from repo root)::

    uv run python scripts/validate_golden_qa.py
    uv run python scripts/validate_golden_qa.py --graph-dir ./data/graphs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import get_settings  # noqa: E402
from backend.graph.qa_samples import seed_m2_qa_graph, seed_stem_qa_graph  # noqa: E402
from backend.graph.store import GraphStore  # noqa: E402
from backend.rag.qa_heuristics import _PATTERN_NUMBER_RE, resolve_gold_chunk_ids  # noqa: E402

EXIT_SUCCESS = 0
EXIT_VALIDATION_FAILED = 1
EXIT_USAGE_ERROR = 2

_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "qa_golden_set.json"
_CHUNK_MANIFEST_DIR = _REPO_ROOT / "data" / "chunk_manifests"
_MOCK_VECTOR_STORE_PATH = _REPO_ROOT / "data" / "mock_vector_store.json"
_GOLDEN_CHUNK_ID_RE = re.compile(r"^(?P<paper_id>[a-z][\w-]*-\d{3,}):chunk:(?P<index>\d+)$")
_LEGACY_CHUNK_ID_RE = re.compile(r"^.+_chunk_\d+$")


class MockChunkIndex:
    """In-memory stand-in for VectorStore chunk lookup during golden-set validation."""

    def __init__(
        self,
        manifests: dict[str, set[str]],
        *,
        chunk_text_by_id: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._manifests = manifests
        self._chunk_text_by_id = chunk_text_by_id or {}

    def known_chunk_ids(self, paper_id: str) -> set[str] | None:
        return self._manifests.get(paper_id)

    def has_chunk(self, paper_id: str, chunk_id: str) -> bool:
        known = self._manifests.get(paper_id)
        if known is None:
            return False
        return chunk_id in known

    def chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        return self._chunk_text_by_id.get(paper_id, {}).get(chunk_id)

    def has_chunk_with_text(self, paper_id: str, chunk_id: str) -> bool:
        if not self.has_chunk(paper_id, chunk_id):
            return False
        text = self.chunk_text(paper_id, chunk_id)
        if text is None:
            return True
        return bool(text.strip())

    @classmethod
    def load_from_repo(
        cls,
        manifest_dir: Path = _CHUNK_MANIFEST_DIR,
        *,
        mock_vector_path: Path = _MOCK_VECTOR_STORE_PATH,
    ) -> MockChunkIndex:
        manifests: dict[str, set[str]] = {}
        chunk_text_by_id: dict[str, dict[str, str]] = {}

        if manifest_dir.is_dir():
            for path in sorted(manifest_dir.glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                paper_id = str(payload.get("paper_id", path.stem))
                chunk_ids = {
                    str(chunk_id).strip() for chunk_id in payload.get("chunk_ids", []) if str(chunk_id).strip()
                }
                manifests.setdefault(paper_id, set()).update(chunk_ids)

        if mock_vector_path.is_file():
            payload = json.loads(mock_vector_path.read_text(encoding="utf-8"))
            papers = payload.get("papers", {})
            if isinstance(papers, dict):
                for paper_id, paper_payload in papers.items():
                    if not isinstance(paper_payload, dict):
                        continue
                    pid = str(paper_id)
                    manifests.setdefault(pid, set())
                    chunk_text_by_id.setdefault(pid, {})
                    for raw in paper_payload.get("chunks", []):
                        if not isinstance(raw, dict):
                            continue
                        chunk_id = str(raw.get("chunk_id", "")).strip()
                        text = str(raw.get("text", "")).strip()
                        if not chunk_id:
                            continue
                        manifests[pid].add(chunk_id)
                        if text:
                            chunk_text_by_id[pid][chunk_id] = text

        return cls(manifests, chunk_text_by_id=chunk_text_by_id)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph 金标 QA ID 校验")
    parser.add_argument(
        "--golden-file",
        type=Path,
        default=_GOLDEN_SET_PATH,
        help="金标问题集路径 (default: data/qa_golden_set.json)",
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=None,
        help="图谱目录（默认 GRAPH_DATA_DIR env）",
    )
    parser.add_argument(
        "--chunk-manifest-dir",
        type=Path,
        default=_CHUNK_MANIFEST_DIR,
        help="Mock 向量库 chunk manifest 目录 (default: data/chunk_manifests)",
    )
    parser.add_argument(
        "--mock-vector-file",
        type=Path,
        default=_MOCK_VECTOR_STORE_PATH,
        help="CI mock 静态向量库 (default: data/mock_vector_store.json)",
    )
    parser.add_argument(
        "--no-auto-seed",
        action="store_true",
        help="禁用缺失 demo 图谱时自动 seed（默认与 benchmark 对齐自动 seed hss-001/stem-001）",
    )
    return parser.parse_args(argv)


def is_stem_detail_item(item: dict[str, Any]) -> bool:
    """True when item targets STEM detail-scale QA (case-insensitive)."""
    paradigm = str(item.get("paradigm", "")).strip().upper()
    scale = str(item.get("scale", "")).strip().lower()
    return paradigm == "STEM" and scale == "detail"


def validate_numeric_pattern_token(pattern: str) -> str | None:
    """Return error message when a numeric required_pattern token is not float()-parseable."""
    token = str(pattern).strip()
    if not _PATTERN_NUMBER_RE.match(token):
        return None

    numeric_body = token[:-1].strip() if token.endswith("%") else token
    try:
        float(numeric_body)
    except ValueError:
        suffix = "%" if token.endswith("%") else ""
        return f"numeric pattern {token!r} is not float()-parseable (body={numeric_body!r}{suffix})"
    return None


def validate_stem_detail_gold(case_id: str, gold: dict[str, Any]) -> list[str]:
    """Assertion 1: STEM detail gold must declare parseable numeric required_patterns."""
    errors: list[str] = []
    patterns = gold.get("required_patterns", [])
    if not isinstance(patterns, list) or not patterns:
        errors.append(f"{case_id}: STEM detail required_patterns must be a non-empty list")
        return errors

    numeric_pattern_count = 0
    for pattern in patterns:
        token = str(pattern).strip()
        if not token:
            errors.append(f"{case_id}: required_patterns contains an empty token")
            continue
        if not _PATTERN_NUMBER_RE.match(token):
            continue
        numeric_pattern_count += 1
        numeric_error = validate_numeric_pattern_token(token)
        if numeric_error is not None:
            errors.append(f"{case_id}: {numeric_error}")

    expected_numbers = gold.get("expected_numbers")
    has_explicit_numbers = isinstance(expected_numbers, list) and bool(expected_numbers)
    if numeric_pattern_count == 0 and not has_explicit_numbers:
        errors.append(
            f"{case_id}: STEM detail must include at least one numeric required_pattern "
            "(float-parseable or % suffix) or non-empty gold.expected_numbers",
        )
    return errors


def ensure_demo_graphs(graph_dir: Path, *, auto_seed: bool) -> None:
    """Seed canonical demo graphs when missing so validation does not silently skip."""
    if not auto_seed:
        return
    if not (graph_dir / "hss-001.json").is_file():
        seed_m2_qa_graph(graph_dir)
        print("[INFO] auto-seeded demo graph hss-001")
    if not (graph_dir / "stem-001.json").is_file():
        seed_stem_qa_graph(graph_dir)
        print("[INFO] auto-seeded demo graph stem-001")


def validate_chunk_id_format(chunk_id: str, *, expected_paper_id: str) -> str | None:
    """Return an error message when *chunk_id* violates the canonical naming scheme."""
    if _LEGACY_CHUNK_ID_RE.match(chunk_id):
        return (
            f"chunk_id={chunk_id!r} uses legacy '_chunk_' naming; "
            f"expected {{paper_id}}:chunk:{{index}} (e.g. {expected_paper_id}:chunk:42)"
        )

    match = _GOLDEN_CHUNK_ID_RE.match(chunk_id)
    if match is None:
        return (
            f"chunk_id={chunk_id!r} does not match canonical pattern "
            f"'{{paper_id}}:chunk:{{index}}' (e.g. {expected_paper_id}:chunk:42)"
        )

    if match.group("paper_id") != expected_paper_id:
        return (
            f"chunk_id={chunk_id!r} paper prefix {match.group('paper_id')!r} "
            f"does not match item paper_id={expected_paper_id!r}"
        )
    return None


def validate(args: argparse.Namespace) -> int:
    """Iterate golden QA items and verify referenced graph/chunk IDs."""
    if not args.golden_file.is_file():
        print(f"[ERROR] 金标文件不存在: {args.golden_file}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    golden = json.loads(args.golden_file.read_text(encoding="utf-8"))
    items = golden.get("items", [])
    if not items:
        print("[ERROR] 金标文件中 items 为空", file=sys.stderr)
        return EXIT_USAGE_ERROR

    graph_dir = (args.graph_dir or Path(get_settings().graph_data_dir)).resolve()
    graph_dir.mkdir(parents=True, exist_ok=True)
    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)
    get_settings.cache_clear()

    ensure_demo_graphs(graph_dir, auto_seed=not args.no_auto_seed)
    chunk_index = MockChunkIndex.load_from_repo(
        args.chunk_manifest_dir,
        mock_vector_path=args.mock_vector_file,
    )

    store = GraphStore(base_dir=graph_dir)
    all_valid = True

    paper_ids: set[str] = {str(item.get("paper_id", "")).strip() for item in items if item.get("paper_id")}
    graphs: dict[str, Any | None] = {}
    for pid in paper_ids:
        graph = store.load(pid)
        if graph is None:
            print(f"[ERROR] 图谱未就绪: {pid} — 请运行 ingest/seed 或移除 --no-auto-seed", file=sys.stderr)
            graphs[pid] = None
            all_valid = False
            continue

        graphs[pid] = graph
        node_ids = {n.id for n in graph.nodes}
        edge_ids = {e.id for e in graph.edges}
        print(f"[INFO] {pid}: {len(node_ids)} nodes, {len(edge_ids)} edges loaded")

    for paper_id, chunk_ids in ((pid, chunk_index.known_chunk_ids(pid)) for pid in paper_ids):
        if chunk_ids is not None:
            print(f"[INFO] mock vector index {paper_id}: {len(chunk_ids)} chunk_ids")

    for idx, item in enumerate(items, start=1):
        question = item.get("question", f"item-{idx}")[:60]
        paper_id = str(item.get("paper_id", ""))
        case_id = str(item.get("id", question))
        gold = item.get("gold", {})

        graph = graphs.get(paper_id)
        if graph is None:
            print(f"  [{idx}] ❌ FAIL: {case_id} — paper {paper_id!r} graph missing", file=sys.stderr)
            continue

        if is_stem_detail_item(item):
            for stem_error in validate_stem_detail_gold(case_id, gold):
                print(f"  [{idx}] ❌ FAIL: {stem_error}", file=sys.stderr)
                all_valid = False

        node_ids_in_graph = {n.id for n in graph.nodes}
        edge_ids_in_graph = {e.id for e in graph.edges}

        for node_id in gold.get("nodes", []):
            if node_id not in node_ids_in_graph:
                print(
                    f"  [{idx}] ❌ FAIL: node_id={node_id!r} not in {paper_id} graph ({case_id})",
                    file=sys.stderr,
                )
                all_valid = False

        for edge_id in gold.get("edges", []):
            if edge_id not in edge_ids_in_graph:
                print(
                    f"  [{idx}] ❌ FAIL: edge_id={edge_id!r} not in {paper_id} graph ({case_id})",
                    file=sys.stderr,
                )
                all_valid = False

        chunk_refs = sorted(resolve_gold_chunk_ids(gold))
        if not chunk_refs:
            continue

        if chunk_index.known_chunk_ids(paper_id) is None:
            print(
                f"  [{idx}] ❌ FAIL: {case_id} references chunks but no manifest/mock index for "
                f"{paper_id} (checked {args.chunk_manifest_dir} and {args.mock_vector_file})",
                file=sys.stderr,
            )
            all_valid = False
            continue

        for chunk_id in chunk_refs:
            format_error = validate_chunk_id_format(chunk_id, expected_paper_id=paper_id)
            if format_error is not None:
                print(f"  [{idx}] ❌ FAIL: {format_error} ({case_id})", file=sys.stderr)
                all_valid = False
                continue

            if not chunk_index.has_chunk_with_text(paper_id, chunk_id):
                print(
                    f"  [{idx}] ❌ FAIL: chunk_id={chunk_id!r} not found in mock vector index "
                    f"(manifest + {args.mock_vector_file.name}) for {paper_id} ({case_id})",
                    file=sys.stderr,
                )
                all_valid = False

    if all_valid:
        print(f"\n[OK] 所有 {len(items)} 个金标问题的 graph/chunk ID 引用均有效。")
        return EXIT_SUCCESS

    print(
        f"\n[FAIL] 发现过期或非法 ID 引用，请更新 {args.golden_file} 或相关 manifest/graph 后重新运行。",
        file=sys.stderr,
    )
    return EXIT_VALIDATION_FAILED


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return validate(args)


if __name__ == "__main__":
    raise SystemExit(main())
