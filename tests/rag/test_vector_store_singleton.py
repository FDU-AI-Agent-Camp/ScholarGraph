# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for process-wide VectorStore bind / get / reset."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest
from backend.rag.vector_store import VectorStore
from backend.rag.vector_store_wiring import bind_vector_store, get_vector_store, reset_vector_store


def test_bind_get_returns_same_instance() -> None:
    reset_vector_store()
    store = cast(VectorStore, MagicMock(name="bound-vector-store"))
    bind_vector_store(store)

    assert get_vector_store() is store
    assert get_vector_store() is store


def test_reset_clears_singleton() -> None:
    reset_vector_store()
    first = cast(VectorStore, MagicMock(name="first-store"))
    bind_vector_store(first)
    assert get_vector_store() is first

    reset_vector_store()
    second = cast(VectorStore, MagicMock(name="second-store"))
    bind_vector_store(second)
    assert get_vector_store() is second
    assert get_vector_store() is not first


def test_get_unbound_under_pytest_raises() -> None:
    reset_vector_store()
    with pytest.raises(RuntimeError, match="unbound under pytest"):
        get_vector_store()
