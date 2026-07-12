"""DB persistence assertions for PipelineCompletionService (SVC-FINALIZE-02)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from backend.config import get_settings
from backend.db.base import get_async_session_factory
from backend.db.models import PaperRow
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.extractor_config_fingerprint import compute_extractor_config_hash
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.pipeline_completion_service import PipelineCompletionService
from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service


@pytest.mark.asyncio
async def test_finalize_writes_graph_path_and_extractor_config_hash(
    persistence_env,
    sample_graph: UnifiedPaperGraph,
    sample_classification: ParadigmClassification,
) -> None:
    paper_id = "finalize-db-001"
    await register_test_paper(paper_id, title="Finalize DB")
    await restart_paper_service()

    graph = sample_graph.model_copy(update={"paper_id": paper_id})
    persistence = MagicMock(spec=GraphPersistenceService)
    PipelineCompletionService(graph_persistence=persistence).finalize(
        paper_id,
        graph_data=graph.model_dump(mode="json"),
        classification_data=sample_classification.model_dump(mode="json"),
    )

    expected_hash = compute_extractor_config_hash(get_settings())
    async with get_async_session_factory()() as session:
        row = await session.get(PaperRow, paper_id)
    assert row is not None
    assert row.graph_path is not None
    assert row.graph_path.endswith(f"{paper_id}.json")
    assert row.graph_version == "1"
    assert row.extractor_config_hash == expected_hash
    assert len(row.extractor_config_hash) == 64
