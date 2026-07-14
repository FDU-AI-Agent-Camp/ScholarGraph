#!/usr/bin/env python3
"""P13 static concurrency audit: RAG/LLM I/O must declare explicit timeouts.

Exit non-zero when critical call sites lose ``asyncio.wait_for`` / HTTP timeouts,
so CI catches regressions that re-introduce unbounded hangs.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

# Packages where outbound I/O must not use bare httpx clients.
_IO_SCAN_ROOTS = (
    BACKEND / "rag",
    BACKEND / "llm",
    BACKEND / "patrol",
)

_HANDLERS = BACKEND / "rag" / "handlers.py"
_WATCHDOG = BACKEND / "rag" / "indexing_watchdog.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_rag_handler_wait_for() -> list[str]:
    """Layer-1 index path must wrap the core async indexer with configurable wait_for."""
    errors: list[str] = []
    source = _read(_HANDLERS)
    if "asyncio.wait_for" not in source and "wait_for(" not in source:
        errors.append(f"{_HANDLERS.relative_to(REPO_ROOT)}: missing asyncio.wait_for around index path")
    if "rag_single_index_timeout_seconds" not in source:
        errors.append(
            f"{_HANDLERS.relative_to(REPO_ROOT)}: must read settings.rag_single_index_timeout_seconds",
        )
    if "RAG_INDEX_TIMEOUT_WARNING" not in source:
        errors.append(f"{_HANDLERS.relative_to(REPO_ROOT)}: missing RAG_INDEX_TIMEOUT_WARNING path")
    if "_revoke_and_schedule_orphan_cleanup" not in source:
        errors.append(
            f"{_HANDLERS.relative_to(REPO_ROOT)}: missing orphan-run revoke/cleanup on timeout",
        )
    registry = BACKEND / "rag" / "indexing_run_registry.py"
    if not registry.is_file():
        errors.append(f"{registry.relative_to(REPO_ROOT)}: missing IndexingRunRegistry module")
    else:
        reg_src = _read(registry)
        if "may_activate" not in reg_src or "revoke" not in reg_src:
            errors.append(f"{registry.relative_to(REPO_ROOT)}: registry must expose revoke/may_activate")
    return errors


def check_watchdog_heal_log_tag() -> list[str]:
    """Macro heal/cold-boot must emit the ops-alert marker ``[P13_WATCHDOG_HEAL]``."""
    errors: list[str] = []
    source = _read(_WATCHDOG)
    if 'P13_WATCHDOG_HEAL_TAG = "[P13_WATCHDOG_HEAL]"' not in source:
        errors.append(f"{_WATCHDOG.relative_to(REPO_ROOT)}: missing P13_WATCHDOG_HEAL_TAG constant")
    if "P13_WATCHDOG_HEAL_TAG" not in source or "indexing_watchdog_promoted" not in source:
        errors.append(f"{_WATCHDOG.relative_to(REPO_ROOT)}: promote log must include P13_WATCHDOG_HEAL_TAG")
    if "indexing_watchdog_cold_boot_reconcile" not in source or "P13_WATCHDOG_HEAL_TAG" not in source:
        errors.append(f"{_WATCHDOG.relative_to(REPO_ROOT)}: cold-boot reconcile must tag P13_WATCHDOG_HEAL")
    if "threading.Thread" not in source or "dedicated_thread" not in source:
        errors.append(
            f"{_WATCHDOG.relative_to(REPO_ROOT)}: macro watchdog must run on a dedicated OS thread",
        )
    if "scan_and_promote_stuck_indexing_sync()" not in source:
        errors.append(
            f"{_WATCHDOG.relative_to(REPO_ROOT)}: thread body must use sync scan (not run_async onto the FastAPI loop)",
        )
    if "run_async(scan_and_promote_stuck_indexing())" in source:
        errors.append(
            f"{_WATCHDOG.relative_to(REPO_ROOT)}: thread body must not run_async(scan…) "
            "(main-loop starvation would stall the watchdog)",
        )
    return errors


class _HttpxTimeoutVisitor(ast.NodeVisitor):
    """Flag ``httpx.AsyncClient(...)`` / ``httpx.Client(...)`` constructed without timeout=."""

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.errors: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        # Require the httpx. qualifier to avoid OpenAI/chromadb Client false positives.
        if name in {"httpx.AsyncClient", "httpx.Client"} and not _has_keyword(node, "timeout"):
            lineno = getattr(node, "lineno", "?")
            self.errors.append(
                f"{self.rel_path}:{lineno}: {name}() missing explicit timeout= (unbounded I/O hang risk)",
            )
        self.generic_visit(node)


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _has_keyword(node: ast.Call, key: str) -> bool:
    return any(isinstance(kw, ast.keyword) and kw.arg == key for kw in node.keywords)


def check_httpx_clients_have_timeout() -> list[str]:
    errors: list[str] = []
    for root in _IO_SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.name.startswith("_") and path.name != "__init__.py":
                # still scan
                pass
            source = _read(path)
            if "httpx" not in source and "AsyncClient" not in source:
                continue
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError as exc:
                errors.append(f"{path.relative_to(REPO_ROOT)}: syntax error during audit: {exc}")
                continue
            visitor = _HttpxTimeoutVisitor(str(path.relative_to(REPO_ROOT)))
            visitor.visit(tree)
            errors.extend(visitor.errors)
    return errors


def check_settings_expose_timeouts() -> list[str]:
    """Settings must keep the P13 knobs importable / configurable."""
    from backend.config import get_settings

    settings = get_settings()
    errors: list[str] = []
    for attr in (
        "rag_single_index_timeout_seconds",
        "rag_indexing_watchdog_seconds",
        "rag_indexing_heartbeat_stale_seconds",
    ):
        if not hasattr(settings, attr):
            errors.append(f"Settings missing timeout knob: {attr}")
        else:
            value = getattr(settings, attr)
            if not isinstance(value, (int, float)) or float(value) <= 0:
                errors.append(f"Settings.{attr} must be a positive number, got {value!r}")
    return errors


def run_all_checks() -> list[str]:
    errors: list[str] = []
    errors.extend(check_rag_handler_wait_for())
    errors.extend(check_watchdog_heal_log_tag())
    errors.extend(check_httpx_clients_have_timeout())
    errors.extend(check_settings_expose_timeouts())
    return errors


def main() -> int:
    errors = run_all_checks()
    if errors:
        print("P13 RAG I/O timeout audit FAILED:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("P13 RAG I/O timeout audit OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
