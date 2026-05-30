"""handoff §5 / collaboration §4.4 contract checks."""

from __future__ import annotations

import inspect

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


def test_patrol_mode_values_match_openapi() -> None:
    assert PatrolMode.LENS_CLASH.value == "lens_clash"
    assert PatrolMode.CONTRADICTION.value == "contradiction"
