# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Self-correction helpers for two-phase graph extraction (v2)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from backend.schemas.extract_phase import (
    ExtractedEdgeList,
    ExtractedGraph,
    ExtractedNodeList,
)
from backend.schemas.graph import HSS_EDGE_TYPES, HSS_NODE_TYPES, STEM_EDGE_TYPES, STEM_NODE_TYPES
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

RepairLevel = Literal["nodes", "edges"]

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def classify_validation_error(exc: ValidationError) -> RepairLevel:
    """Classify a ValidationError as node-level or edge-level.

    Heuristic: if any error location or message mentions 'node', treat as node-level;
    otherwise assume edge-level (dangling references, duplicate edge ids, etc.).
    """
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        msg = error.get("msg", "").lower()
        if "node" in loc or "node" in msg:
            return "nodes"
    return "edges"


def format_error_messages(exc: ValidationError) -> str:
    """Format a ValidationError into a human-readable bullet list."""
    lines = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        msg = error.get("msg", "")
        lines.append(f"- [{loc}] {msg}")
    return "\n".join(lines)


def build_repair_prompt(
    *,
    paradigm: Paradigm,
    error_messages: str,
    previous_data: ExtractedNodeList | ExtractedEdgeList,
    level: RepairLevel,
) -> str:
    """Build a system prompt asking the LLM to fix extraction errors.

    Args:
        paradigm: STEM or HSS.
        error_messages: Human-readable validation errors.
        previous_data: The previous Stage 1 or Stage 2 output.
        level: Whether the error is at node or edge level.

    Returns:
        A system prompt string ready to be sent to the LLM.
    """
    template_path = PROMPTS_DIR / "extract_repair.md"
    if template_path.is_file():
        template = template_path.read_text(encoding="utf-8")
    else:
        template = (
            "Fix the following validation errors in the previous extraction output:\n\n"
            "{error_messages}\n\n"
            "Previous attempt:\n{previous_json}\n\n"
            "Allowed node types: {allowed_node_types}\n"
            "Allowed edge types: {allowed_edge_types}"
        )

    previous_json = previous_data.model_dump_json(indent=2)
    allowed_node_types = sorted(t.value for t in (HSS_NODE_TYPES if paradigm == Paradigm.HSS else STEM_NODE_TYPES))
    allowed_edge_types = sorted(t for t in (HSS_EDGE_TYPES if paradigm == Paradigm.HSS else STEM_EDGE_TYPES))

    prompt = template.format(
        error_messages=error_messages,
        previous_json=previous_json,
        paradigm=paradigm.value,
        allowed_node_types=", ".join(allowed_node_types),
        allowed_edge_types=", ".join(allowed_edge_types),
    )
    prompt += f"\n\n## Repair Scope\n\nFocus on fixing the {level}-level errors listed above."
    return prompt


def build_extracted_graph(
    paper_id: str,
    title: str | None,
    paradigm: Paradigm,
    nodes: ExtractedNodeList,
    edges: ExtractedEdgeList,
    summary: str | None = None,
) -> ExtractedGraph:
    """Combine Stage 1 and Stage 2 outputs and run final validation.

    Raises:
        ValidationError: When the combined graph violates schema constraints.
    """
    return ExtractedGraph(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        nodes=nodes.nodes,
        edges=edges.edges,
        summary=summary,
    )
