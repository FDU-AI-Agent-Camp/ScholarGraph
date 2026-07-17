# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for service-layer tests."""

from __future__ import annotations

import asyncio

import pytest
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from tests.helpers.persistence_testkit import register_test_paper, reset_persistence_singletons


@pytest.fixture
def sample_classification() -> ParadigmClassification:
    return ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.91,
        reason="测试分类理由",
    )


@pytest.fixture
def sample_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="svc-test-paper",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="REF",
                type="REF",
            ),
        ],
    )


@pytest.fixture
def registered_paper(persistence_env) -> str:
    paper_id = "svc-test-paper"
    asyncio.run(register_test_paper(paper_id, title="service test"))
    reset_persistence_singletons()
    from backend.graph.head_store import HeadStore

    HeadStore()._path(paper_id).unlink(missing_ok=True)
    return paper_id
