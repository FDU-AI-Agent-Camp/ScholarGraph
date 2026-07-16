#!/usr/bin/env python3
"""AST architecture guard: forbid piercing ``PaperService._pipeline_repo``.

Only ``paper_service.py`` and ``paper_pipeline_ops.py`` may reference the private
attribute. All other ``backend/`` modules must use PaperService public facade APIs.

Usage (repo root)::

    uv run python scripts/check_pipeline_repo_lod.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

# Mixins / the aggregate root may touch the private repository.
_ALLOWED_RELATIVE = frozenset(
    {
        "services/paper_service.py",
        "services/paper_pipeline_ops.py",
    },
)


class _PipelineRepoPiercingVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.hits: list[int] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "_pipeline_repo":
            self.hits.append(getattr(node, "lineno", 0) or 0)
        self.generic_visit(node)


def _iter_backend_py() -> list[Path]:
    return sorted(path for path in BACKEND.rglob("*.py") if "__pycache__" not in path.parts)


def check_pipeline_repo_lod() -> list[str]:
    errors: list[str] = []
    for path in _iter_backend_py():
        rel = path.relative_to(BACKEND).as_posix()
        if rel in _ALLOWED_RELATIVE:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error while scanning ({exc})")
            continue
        visitor = _PipelineRepoPiercingVisitor(rel)
        visitor.visit(tree)
        for lineno in visitor.hits:
            errors.append(
                f"{rel}:{lineno}: illegal Attribute access to ._pipeline_repo "
                "(use PaperService public pipeline facade instead)",
            )
    return errors


def main() -> int:
    errors = check_pipeline_repo_lod()
    if errors:
        sys.stderr.write("Pipeline repo LoD / architecture invariant violations:\n")
        for item in errors:
            sys.stderr.write(f"  - {item}\n")
        return 1
    sys.stdout.write("PaperService._pipeline_repo LoD audit OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
