"""Boundary tests: no double-routing and legacy sync RAG path eradication."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

RAG_INDEX_SYMBOLS = frozenset(
    {
        "index_paper_for_rag",
        "_index_paper_for_rag",
        "_index_paper_for_rag_async",
        "index_paper_for_rag_async",
    },
)

ALLOWED_RAG_CALLER_PATHS = frozenset(
    {
        BACKEND_ROOT / "rag" / "handlers.py",
        BACKEND_ROOT / "services" / "rag_index_service.py",
        BACKEND_ROOT / "rag" / "__init__.py",
    },
)

FORBIDDEN_RAG_SCAN_ROOTS = (
    BACKEND_ROOT / "graph",
    BACKEND_ROOT / "services" / "pipeline_completion_service.py",
)


def _relative_backend_path(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


def _collect_rag_symbol_references(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    hits: list[str] = []
    for symbol in RAG_INDEX_SYMBOLS:
        if symbol in source:
            hits.append(symbol)
    return hits


def test_nodes_py_has_no_rag_indexing_symbols() -> None:
    nodes_path = BACKEND_ROOT / "graph" / "nodes.py"
    hits = _collect_rag_symbol_references(nodes_path)
    assert hits == [], f"nodes.py must not reference RAG indexing symbols, found: {hits}"


def test_legacy_sync_rag_helper_removed_from_nodes_source() -> None:
    nodes_source = (BACKEND_ROOT / "graph" / "nodes.py").read_text(encoding="utf-8")
    assert "_index_paper_for_rag_async" not in nodes_source
    assert "index_paper_for_rag" not in nodes_source
    assert "rag_index_service" not in nodes_source
    assert "RagIndexService" not in nodes_source


@pytest.mark.parametrize(
    "scan_root",
    [
        BACKEND_ROOT / "graph",
    ],
)
def test_graph_package_has_no_direct_rag_index_calls(scan_root: Path) -> None:
    violations: list[str] = []
    for path in sorted(scan_root.rglob("*.py")):
        if path.name == "__pycache__":
            continue
        hits = _collect_rag_symbol_references(path)
        if hits:
            violations.append(f"{_relative_backend_path(path)}: {', '.join(hits)}")
    assert violations == [], "graph package must not call RAG indexing directly:\n" + "\n".join(violations)


def test_pipeline_completion_service_has_no_direct_rag_index_calls() -> None:
    path = BACKEND_ROOT / "services" / "pipeline_completion_service.py"
    hits = _collect_rag_symbol_references(path)
    assert hits == [], f"pipeline_completion_service must publish events only, found: {hits}"


def test_rag_indexing_callers_are_allowlisted_only() -> None:
    violations: list[str] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if "test" in path.parts:
            continue
        hits = _collect_rag_symbol_references(path)
        if not hits:
            continue
        if path not in ALLOWED_RAG_CALLER_PATHS:
            violations.append(f"{_relative_backend_path(path)}: {', '.join(hits)}")
    assert violations == [], "unexpected RAG indexing callers outside allowlist:\n" + "\n".join(violations)


def test_store_node_ast_does_not_import_rag_modules() -> None:
    nodes_path = BACKEND_ROOT / "graph" / "nodes.py"
    tree = ast.parse(nodes_path.read_text(encoding="utf-8"), filename=str(nodes_path))
    rag_imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "rag" in alias.name:
                    rag_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and "rag" in node.module:
            rag_imports.append(node.module)

    assert rag_imports == [], f"nodes.py must not import rag modules, found: {rag_imports}"
