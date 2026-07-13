"""Tests for Patrol golden config_snapshot layered gating."""

from __future__ import annotations

import pytest
from backend.config import Settings
from tests.fixtures.patrol_golden_config_snapshot import (
    GoldenConfigSnapshotMismatch,
    collect_config_snapshot_mismatches,
    validate_golden_config_snapshot,
)
from tests.fixtures.patrol_method_overlap_golden import (
    GoldenConfigSnapshot,
    load_method_overlap_golden_set,
)


def test_method_overlap_golden_includes_config_snapshot() -> None:
    golden = load_method_overlap_golden_set()
    assert golden.schema_version == 3
    assert golden.config_snapshot.embedding_model == "bge-m3"
    assert golden.config_snapshot.patrol_semantic_threshold == 0.88
    assert golden.config_snapshot.enable_patrol_semantic_path is True


def test_validate_golden_config_snapshot_passes_with_aligned_settings() -> None:
    golden = load_method_overlap_golden_set()
    settings = Settings(
        llm_mode="mock",
        embedding_model=golden.config_snapshot.embedding_model,
        patrol_semantic_threshold=golden.config_snapshot.patrol_semantic_threshold,
        enable_patrol_semantic_path=golden.config_snapshot.enable_patrol_semantic_path,
    )
    snapshot = validate_golden_config_snapshot(settings=settings, golden=golden)
    assert snapshot.embedding_model == "bge-m3"


def test_validate_golden_config_snapshot_blocks_embedding_model_drift() -> None:
    golden = load_method_overlap_golden_set()
    settings = Settings(
        llm_mode="mock",
        embedding_model="text-embedding-3-small",
        patrol_semantic_threshold=golden.config_snapshot.patrol_semantic_threshold,
        enable_patrol_semantic_path=golden.config_snapshot.enable_patrol_semantic_path,
    )
    with pytest.raises(GoldenConfigSnapshotMismatch, match="EMBEDDING_MODEL"):
        validate_golden_config_snapshot(settings=settings, golden=golden)


def test_collect_config_snapshot_mismatches_reports_threshold_delta() -> None:
    snapshot = GoldenConfigSnapshot(
        patrol_semantic_threshold=0.88,
        embedding_model="bge-m3",
        enable_patrol_semantic_path=True,
    )
    settings = Settings(llm_mode="mock", patrol_semantic_threshold=0.90, embedding_model="bge-m3")
    mismatches = collect_config_snapshot_mismatches(snapshot, settings)
    assert any("PATROL_SEMANTIC_THRESHOLD" in line for line in mismatches)
