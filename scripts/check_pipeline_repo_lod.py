#!/usr/bin/env python3
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Capability-based AST guard for private repository attributes.

Philosophy (not a caller-file allowlist):
  Reverse-declare which modules may *own* repository internals, then reject
  every ``._paper_repo`` / ``._pipeline_repo`` Attribute access outside that
  capability set — including ``self._paper_repo`` in non-owners.

Owner capabilities are role patterns (``*core_service.py``, ``*repository.py``,
aggregate ``paper_service.py``, pipeline ops / facade / coordinator roles).
First-class lifecycle orchestrators (delete / re-extract) are intentionally
**not** owners: they inject repositories under a different attribute name and
cannot pierce ``paper_service._paper_repo``.

Usage (repo root)::

    uv run python scripts/check_pipeline_repo_lod.py
"""

from __future__ import annotations

import ast
import fnmatch
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

_GUARDED_REPO_ATTRS = frozenset({"_paper_repo", "_pipeline_repo"})

# Role-based capability declarations (globs matched against backend-relative paths).
_PAPER_REPO_OWNER_GLOBS = (
    "services/paper_service.py",
    "*core_service.py",
    "**/core_service.py",
    "*repository.py",
    "**/repositories/*.py",
    "*facade.py",
    "*coordinator.py",
)
_PIPELINE_REPO_OWNER_GLOBS = (
    "services/paper_service.py",
    "*pipeline_ops.py",
    "*warning_service.py",
    "*facade.py",
    "*coordinator.py",
    "*repository.py",
    "**/repositories/*.py",
)


class ArchitectureViolationError(Exception):
    """Raised when a module pierces private repository attributes without capability."""

    def __init__(self, *, rel_path: str, lineno: int, attr: str) -> None:
        self.rel_path = rel_path
        self.lineno = lineno
        self.attr = attr
        super().__init__(
            f"Disallowed private repository penetration detected in line {lineno} of {rel_path} (attr={attr})"
        )


def is_repo_capability_owner(rel_path: str, attr: str) -> bool:
    """Return whether *rel_path* may legally own/use the guarded repository attribute."""
    if attr == "_paper_repo":
        globs = _PAPER_REPO_OWNER_GLOBS
    elif attr == "_pipeline_repo":
        globs = _PIPELINE_REPO_OWNER_GLOBS
    else:
        return False
    name = Path(rel_path).name
    return any(fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern) for pattern in globs)


def _is_self_or_cls_receiver(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id in {"self", "cls"}


class _CapabilityRepoGuardVisitor(ast.NodeVisitor):
    """Flag guarded repo Attribute nodes that violate capability or LoD rules."""

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.violations: list[tuple[int, str]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr = node.attr
        if attr in _GUARDED_REPO_ATTRS:
            lineno = getattr(node, "lineno", 0) or 0
            owns = is_repo_capability_owner(self.rel_path, attr)
            is_self = _is_self_or_cls_receiver(node.value)
            # Non-owners: any mention is penetration (incl. self._paper_repo).
            # Owners: only self/cls ownership is legal (foreign pierce still melts).
            if not owns or not is_self:
                self.violations.append((lineno, attr))
        self.generic_visit(node)


def _iter_backend_py() -> list[Path]:
    return sorted(path for path in BACKEND.rglob("*.py") if "__pycache__" not in path.parts)


def check_pipeline_repo_lod() -> list[str]:
    """Scan ``backend/`` and return human-readable capability-guard violations."""
    errors: list[str] = []
    for path in _iter_backend_py():
        rel = path.relative_to(BACKEND).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error while scanning ({exc})")
            continue
        visitor = _CapabilityRepoGuardVisitor(rel)
        visitor.visit(tree)
        for lineno, attr in visitor.violations:
            violation = ArchitectureViolationError(rel_path=rel, lineno=lineno, attr=attr)
            errors.append(str(violation))
    return errors


def enforce_repo_capability_guard() -> None:
    """Raise the first :class:`ArchitectureViolationError` if any violation exists."""
    for path in _iter_backend_py():
        rel = path.relative_to(BACKEND).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            raise ArchitectureViolationError(rel_path=rel, lineno=0, attr="<syntax>") from exc
        visitor = _CapabilityRepoGuardVisitor(rel)
        visitor.visit(tree)
        if visitor.violations:
            lineno, attr = visitor.violations[0]
            raise ArchitectureViolationError(rel_path=rel, lineno=lineno, attr=attr)


def main() -> int:
    errors = check_pipeline_repo_lod()
    if errors:
        sys.stderr.write("Private repo capability-guard / architecture violations:\n")
        for item in errors:
            sys.stderr.write(f"  - {item}\n")
        return 1
    sys.stdout.write("Private repository capability-guard audit OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
