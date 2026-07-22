# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for HeadStore persistence helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.graph.head_store import HeadStore
from backend.schemas.ingest_head import IngestHead


@pytest.fixture
def head_store(tmp_path: Path) -> HeadStore:
    return HeadStore(base_dir=tmp_path)


def test_head_path_for_uses_stable_filename(head_store: HeadStore, tmp_path: Path) -> None:
    assert head_store.head_path_for("paper-1") == tmp_path / "paper-1.head.json"


def test_head_store_delete_removes_record(head_store: HeadStore) -> None:
    head = IngestHead(title="T", abstract="A", intro="I")
    head_store.save("paper-1", merged=head)

    assert head_store.delete("paper-1") is True
    assert head_store.load("paper-1") is None
    assert head_store.delete("paper-1") is False
