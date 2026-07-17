#!/usr/bin/env python3
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Idempotently add SPDX / copyright headers to project source files."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPYRIGHT = "Copyright 2026 FDU-AI-Agent-Camp"
SPDX = "SPDX-License-Identifier: Apache-2.0"
MARKER = "SPDX-License-Identifier: Apache-2.0"

HEADER_HASH = f"# {COPYRIGHT}\n# {SPDX}\n"
HEADER_BLOCK = f"/**\n * {COPYRIGHT}\n * {SPDX}\n */\n"
HEADER_HTML = f"<!--\n{COPYRIGHT}\n{SPDX}\n-->\n"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "coverage",
    "generated",
}
PYTHON_GLOBS = (
    "backend/**/*.py",
    "scripts/**/*.py",
    "tests/**/*.py",
)
FRONTEND_GLOBS = (
    "frontend/src/**/*.ts",
    "frontend/src/**/*.js",
    "frontend/src/**/*.vue",
    "frontend/src/**/*.css",
    "frontend/src/**/*.scss",
    "frontend/*.ts",
    "frontend/*.js",
    "frontend/*.mjs",
    "frontend/*.cjs",
)


def _should_skip(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    normalized = path.as_posix()
    return "/api/generated/" in normalized


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _with_newline(header: str, newline: str) -> str:
    if newline == "\n":
        return header
    return header.replace("\n", newline)


def _iter_targets() -> list[Path]:
    found: set[Path] = set()
    for pattern in (*PYTHON_GLOBS, *FRONTEND_GLOBS):
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            if _should_skip(path):
                continue
            found.add(path.resolve())
    return sorted(found)


def _has_header(text: str) -> bool:
    return MARKER in text[:400]


def _insert_python_header(text: str, newline: str) -> str:
    header = _with_newline(HEADER_HASH, newline)
    lines = text.splitlines(keepends=True)
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    if insert_at < len(lines) and "coding" in lines[insert_at] and lines[insert_at].lstrip().startswith("#"):
        insert_at += 1
    prefix = "".join(lines[:insert_at])
    rest = "".join(lines[insert_at:])
    spacer = "" if not rest or rest.startswith(("\n", "\r\n")) else newline
    return f"{prefix}{header}{spacer}{rest}"


def _insert_block_header(text: str, newline: str) -> str:
    header = _with_newline(HEADER_BLOCK, newline)
    spacer = "" if not text or text.startswith(("\n", "\r\n")) else newline
    return f"{header}{spacer}{text}"


def _insert_vue_header(text: str, newline: str) -> str:
    header = _with_newline(HEADER_HTML, newline)
    spacer = "" if not text or text.startswith(("\n", "\r\n")) else newline
    return f"{header}{spacer}{text}"


def _apply(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    if _has_header(original):
        return False
    newline = _detect_newline(original)
    suffix = path.suffix.lower()
    if suffix == ".py":
        updated = _insert_python_header(original, newline)
    elif suffix == ".vue":
        updated = _insert_vue_header(original, newline)
    elif suffix in {".ts", ".js", ".mjs", ".cjs", ".css", ".scss"}:
        updated = _insert_block_header(original, newline)
    else:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    targets = _iter_targets()
    changed = 0
    for path in targets:
        if _apply(path):
            changed += 1
            print(f"updated: {path.relative_to(ROOT).as_posix()}")
    print(f"done: {changed}/{len(targets)} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
