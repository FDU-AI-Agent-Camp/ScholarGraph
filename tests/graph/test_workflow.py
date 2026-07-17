# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Graph topology smoke tests (see also test_workflow_nodes / _integration / _red)."""

from backend.graph.state import (
    NODE_CLASSIFY,
    NODE_EXTRACT,
    NODE_INGEST,
    NODE_STORE,
    NODE_WAIT_HEAD_REFINE,
    PIPELINE_ORDER,
)
from backend.graph.workflow import build_paper_pipeline_graph, pipeline_node_names


def test_pipeline_node_order() -> None:
    assert pipeline_node_names() == PIPELINE_ORDER
    assert PIPELINE_ORDER == (
        NODE_INGEST,
        NODE_WAIT_HEAD_REFINE,
        NODE_CLASSIFY,
        NODE_EXTRACT,
        NODE_STORE,
    )


def test_graph_topology_includes_fail_path() -> None:
    graph = build_paper_pipeline_graph()
    node_names = set(graph.nodes.keys())
    assert {
        NODE_INGEST,
        NODE_WAIT_HEAD_REFINE,
        NODE_CLASSIFY,
        NODE_EXTRACT,
        NODE_STORE,
        "fail",
    }.issubset(node_names)
