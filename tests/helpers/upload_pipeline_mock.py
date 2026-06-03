"""Patch pipeline nodes so HTTP upload tests reach ready without real PDF ingest."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tests.conftest import mock_pipeline_node_services


@contextmanager
def mock_http_upload_pipeline_run() -> Iterator[None]:
    """Wrap ``run_paper_pipeline`` with per-paper mocked ingest/classify/extract."""

    from backend.graph.workflow import run_paper_pipeline as real_run_paper_pipeline

    async def run_with_mock_nodes(paper_id: str, pdf_path: Path):
        with mock_pipeline_node_services(paper_id):
            return await real_run_paper_pipeline(paper_id, pdf_path)

    with patch(
        "backend.graph.workflow.run_paper_pipeline",
        side_effect=run_with_mock_nodes,
    ):
        yield
