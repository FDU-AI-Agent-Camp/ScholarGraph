# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Fingerprint current extract configuration for persistence invalidation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.config import Settings

PROMPT_GLOB = "extract*.md"


def compute_extractor_config_hash(settings: Settings) -> str:
    """Return a stable SHA-256 hex digest of extract-related settings and prompts."""
    payload: dict[str, object] = {
        "extract_llm_enabled": settings.extract_llm_enabled,
        "extract_two_phase_enabled": settings.extract_two_phase_enabled,
        "extract_chunked_enabled": settings.extract_chunked_enabled,
        "extract_chunk_max_chars": settings.extract_chunk_max_chars,
        "extract_heuristic_fallback": settings.extract_heuristic_fallback,
        "llm_model_primary": settings.llm_model_primary,
        "llm_model_fallback": settings.llm_model_fallback,
        "prompts": _prompt_hashes(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _prompt_hashes() -> dict[str, str]:
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
    if not prompts_dir.is_dir():
        return {}
    result: dict[str, str] = {}
    for path in sorted(prompts_dir.glob(PROMPT_GLOB)):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[path.name] = digest
    return result
