# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""handoff §5 / collaboration §4.4 contract checks."""

from __future__ import annotations

import inspect
from pathlib import Path

import yaml
from backend.patrol import run_patrol as exported_run_patrol
from backend.patrol.service import run_patrol
from backend.schemas.patrol import PatrolMode


def test_run_patrol_exported_from_backend_patrol_package() -> None:
    assert exported_run_patrol is run_patrol


def test_run_patrol_signature_matches_collaboration_contract() -> None:
    signature = inspect.signature(run_patrol)
    required = ("paper_ids", "mode")
    for name in required:
        assert name in signature.parameters
    assert list(signature.parameters)[:2] == list(required)


def test_seed_corpus_exported_from_backend_patrol_package() -> None:
    from backend.patrol import seed_corpus_patrol_graphs as exported_seed
    from backend.patrol.samples import seed_corpus_patrol_graphs

    assert exported_seed is seed_corpus_patrol_graphs


def _load_openapi_patrol_mode_enum() -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    openapi_path = repo_root / "docs" / "api" / "openapi.yaml"
    with openapi_path.open("r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    return spec["components"]["schemas"]["PatrolMode"]["enum"]


def test_patrol_mode_values_match_openapi() -> None:
    openapi_enum = _load_openapi_patrol_mode_enum()
    code_values = sorted(mode.value for mode in PatrolMode)
    assert sorted(openapi_enum) == code_values, (
        f"OpenAPI PatrolMode enum {openapi_enum} does not match code values {code_values}"
    )
