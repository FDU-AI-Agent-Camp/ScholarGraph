# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""AST gate: forbid embedded ``run_async`` / ``async_bridge`` in ``backend/services/``.

Also enforces that Phase-1 SSOT public APIs on PaperService,
PipelineStatusService, status_snapshot_guard, and HeadRefineCoordinator are
declared as ``async def`` (pure-sync helpers remain on an explicit allowlist).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = REPO_ROOT / "backend" / "services"

# Pure CPU / disk helpers that are intentionally sync (no async_bridge).
_SYNC_PUBLIC_ALLOWLIST: dict[str, frozenset[str]] = {
    "paper_service.py::PaperService": frozenset(
        {
            "get_extract_quality_thresholds",
            "compute_extractor_config_hash",
        }
    ),
    "head_refine_coordinator.py::HeadRefineCoordinator": frozenset(
        {
            "load_head_sync",
            "load_record_sync",
            "get_classifier_input_sync",
        }
    ),
    "status_snapshot_guard.py": frozenset(
        {
            "audit_dual_table_invariant",
        }
    ),
    "pipeline_status_service.py": frozenset(
        {
            "validate_status_contract",
            "validate_failed_error_fields",
        }
    ),
}

# Classes / modules whose public callables must be async unless allowlisted.
_ASYNC_SSOT_TARGETS: frozenset[str] = frozenset(
    {
        "paper_service.py::PaperService",
        "pipeline_status_service.py::PipelineStatusService",
        "head_refine_coordinator.py::HeadRefineCoordinator",
        "status_snapshot_guard.py",
    }
)


class ServicesBridgeViolationError(Exception):
    """Raised when ``backend/services`` embeds async_bridge / run_async or sync SSOT APIs."""

    def __init__(self, *, rel_path: str, lineno: int, detail: str) -> None:
        self.rel_path = rel_path
        self.lineno = lineno
        self.detail = detail
        super().__init__(f"{rel_path}:{lineno}: {detail}")


def _iter_service_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _is_async_bridge_module(name: str) -> bool:
    return name == "async_bridge" or name.endswith(".async_bridge") or "async_bridge" in name.split(".")


def _check_import(node: ast.Import, *, rel_path: str) -> None:
    for alias in node.names:
        name = alias.name
        if _is_async_bridge_module(name):
            raise ServicesBridgeViolationError(
                rel_path=rel_path,
                lineno=node.lineno,
                detail=f"forbidden import of async_bridge ({name!r})",
            )
        if alias.asname == "run_async" or name.endswith(".run_async"):
            raise ServicesBridgeViolationError(
                rel_path=rel_path,
                lineno=node.lineno,
                detail="forbidden import of run_async",
            )


def _check_import_from(node: ast.ImportFrom, *, rel_path: str) -> None:
    module = node.module or ""
    if _is_async_bridge_module(module):
        raise ServicesBridgeViolationError(
            rel_path=rel_path,
            lineno=node.lineno,
            detail=f"forbidden import from async_bridge ({module!r})",
        )
    imported = {alias.name for alias in node.names}
    if "run_async" in imported:
        raise ServicesBridgeViolationError(
            rel_path=rel_path,
            lineno=node.lineno,
            detail="forbidden import of run_async",
        )
    if "async_bridge" in imported:
        raise ServicesBridgeViolationError(
            rel_path=rel_path,
            lineno=node.lineno,
            detail="forbidden import of async_bridge",
        )


def _check_call(node: ast.Call, *, rel_path: str) -> None:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "run_async":
        raise ServicesBridgeViolationError(
            rel_path=rel_path,
            lineno=node.lineno,
            detail="forbidden call to run_async(...)",
        )
    if isinstance(func, ast.Attribute) and func.attr == "run_async":
        raise ServicesBridgeViolationError(
            rel_path=rel_path,
            lineno=node.lineno,
            detail="forbidden call to *.run_async(...)",
        )


def _is_public_name(name: str) -> bool:
    return not name.startswith("_")


def _check_ssot_async_apis(tree: ast.AST, *, file_name: str, rel_path: str) -> None:
    """Require public SSOT APIs to be ``async def`` (allowlisted pure-sync exceptions)."""
    module_key = file_name
    if module_key in _ASYNC_SSOT_TARGETS:
        allow = _SYNC_PUBLIC_ALLOWLIST.get(module_key, frozenset())
        for node in tree.body if isinstance(tree, ast.Module) else []:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public_name(node.name):
                if node.name in allow:
                    continue
                if isinstance(node, ast.FunctionDef):
                    raise ServicesBridgeViolationError(
                        rel_path=rel_path,
                        lineno=node.lineno,
                        detail=f"public SSOT API {node.name!r} must be async def",
                    )

    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.ClassDef):
            continue
        class_key = f"{file_name}::{node.name}"
        if class_key not in _ASYNC_SSOT_TARGETS:
            continue
        allow = _SYNC_PUBLIC_ALLOWLIST.get(class_key, frozenset())
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_public_name(item.name):
                continue
            if item.name in allow:
                continue
            if isinstance(item, ast.FunctionDef):
                raise ServicesBridgeViolationError(
                    rel_path=rel_path,
                    lineno=item.lineno,
                    detail=(
                        f"public SSOT API {class_key}.{item.name} must be async def "
                        "(sync helpers must be allowlisted or removed)"
                    ),
                )


def check_services_file(path: Path, *, display_path: str | None = None) -> None:
    """Raise :class:`ServicesBridgeViolationError` on the first forbidden use."""
    rel = display_path or path.as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ServicesBridgeViolationError(
            rel_path=rel,
            lineno=exc.lineno or 0,
            detail="<syntax>",
        ) from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _check_import(node, rel_path=rel)
        elif isinstance(node, ast.ImportFrom):
            _check_import_from(node, rel_path=rel)
        elif isinstance(node, ast.Call):
            _check_call(node, rel_path=rel)

    _check_ssot_async_apis(tree, file_name=path.name, rel_path=rel)


def check_services_no_run_async(*, services_root: Path = SERVICES_ROOT) -> list[str]:
    """Return human-readable violation strings (empty when clean)."""
    errors: list[str] = []
    for path in _iter_service_python_files(services_root):
        try:
            if services_root == SERVICES_ROOT:
                display = path.relative_to(REPO_ROOT).as_posix()
            else:
                display = path.relative_to(services_root).as_posix()
            check_services_file(path, display_path=display)
        except ServicesBridgeViolationError as exc:
            errors.append(str(exc))
    return errors


def main() -> int:
    errors = check_services_no_run_async()
    if errors:
        print(f"{len(errors)} violation(s) found in backend/services/:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("0 violations found in backend/services/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
