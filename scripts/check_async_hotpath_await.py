# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""AST gate: Phase-2 async hot paths must not call ``run_async``.

Scans production modules that sit on the FastAPI / EventBus / RAG / Patrol
hot path and must ``await`` PaperService / PipelineStatusService APIs directly.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Modules named in Phase-2 acceptance: RAG, Patrol, pipeline status, extract, workflow.
HOTPATH_REL_PATHS: tuple[str, ...] = (
    "backend/rag/vector_store_replace.py",
    "backend/rag/vector_store.py",
    "backend/rag/vector_store_chunk_text.py",
    "backend/rag/handlers.py",
    "backend/rag/wipe_vector_sweep.py",
    "backend/patrol/result_cache.py",
    "backend/services/patrol_service.py",
    "backend/services/pipeline_status_service.py",
    "backend/services/extract_worker.py",
    "backend/graph/workflow.py",
    "backend/graph/nodes.py",
)

# Public APIs that Phase-2 requires callers to await (not wrap via run_async).
REQUIRED_AWAIT_APIS: frozenset[str] = frozenset(
    {
        "get_active_run_id",
        "set_active_run_id",
        "fail_pipeline",
        "get_pipeline_snapshot",
        "set_status_snapshot",
    }
)


class HotpathAwaitViolationError(Exception):
    """Raised when a hot-path module embeds async_bridge / run_async or naked API calls."""

    def __init__(self, *, rel_path: str, lineno: int, detail: str) -> None:
        self.rel_path = rel_path
        self.lineno = lineno
        self.detail = detail
        super().__init__(f"{rel_path}:{lineno}: {detail}")


def _is_async_bridge_module(name: str) -> bool:
    return name == "async_bridge" or name.endswith(".async_bridge") or "async_bridge" in name.split(".")


def _check_imports(tree: ast.AST, *, rel_path: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_async_bridge_module(alias.name) or alias.asname == "run_async":
                    raise HotpathAwaitViolationError(
                        rel_path=rel_path,
                        lineno=node.lineno,
                        detail="forbidden import of async_bridge / run_async",
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_async_bridge_module(module):
                raise HotpathAwaitViolationError(
                    rel_path=rel_path,
                    lineno=node.lineno,
                    detail=f"forbidden import from async_bridge ({module!r})",
                )
            for alias in node.names:
                if alias.name == "run_async" or alias.asname == "run_async":
                    raise HotpathAwaitViolationError(
                        rel_path=rel_path,
                        lineno=node.lineno,
                        detail="forbidden import of run_async",
                    )


def _check_no_run_async_calls(tree: ast.AST, *, rel_path: str) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "run_async":
            raise HotpathAwaitViolationError(
                rel_path=rel_path,
                lineno=node.lineno,
                detail="forbidden call to run_async(...)",
            )
        if isinstance(func, ast.Attribute) and func.attr == "run_async":
            raise HotpathAwaitViolationError(
                rel_path=rel_path,
                lineno=node.lineno,
                detail="forbidden call to *.run_async(...)",
            )


def _call_api_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in REQUIRED_AWAIT_APIS:
        return func.attr
    return None


def _check_api_calls_are_awaited(tree: ast.AST, *, rel_path: str) -> None:
    """Every Call to REQUIRED_AWAIT_APIS must be the value of an Await node."""
    awaited_calls: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            awaited_calls.add(id(node.value))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        api_name = _call_api_name(node)
        if api_name is None:
            continue
        if id(node) not in awaited_calls:
            raise HotpathAwaitViolationError(
                rel_path=rel_path,
                lineno=node.lineno,
                detail=f"call to {api_name}(...) must be awaited on the hot path",
            )


def check_hotpath_source(source: str, *, rel_path: str) -> None:
    """Parse *source* and enforce Phase-2 hot-path rules (for unit tests)."""
    tree = ast.parse(source, filename=rel_path)
    _check_imports(tree, rel_path=rel_path)
    _check_no_run_async_calls(tree, rel_path=rel_path)
    _check_api_calls_are_awaited(tree, rel_path=rel_path)


def check_async_hotpath_await(*, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    for rel in HOTPATH_REL_PATHS:
        path = repo_root / rel
        if not path.is_file():
            errors.append(f"{rel}: missing file")
            continue
        source = path.read_text(encoding="utf-8")
        try:
            check_hotpath_source(source, rel_path=rel)
        except SyntaxError as exc:
            errors.append(f"{rel}:{exc.lineno or 0}: <syntax>")
        except HotpathAwaitViolationError as exc:
            errors.append(str(exc))
    return errors


def main() -> int:
    errors = check_async_hotpath_await()
    if errors:
        print(f"{len(errors)} violation(s) found in Phase-2 async hot paths:")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"0 violations found across {len(HOTPATH_REL_PATHS)} Phase-2 hot-path modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
