# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared plain-text normalization utilities for PDF ingest (BE-1)."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_for_sections(text: str) -> str:
    """Preserve line breaks for section headers while trimming horizontal noise."""
    if not text:
        return ""
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _WHITESPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces and excessive blank lines (full-text export)."""
    section_text = normalize_for_sections(text)
    if not section_text:
        return ""
    return _BLANK_LINES_RE.sub("\n\n", section_text.replace("\n", "\n\n")).strip()
