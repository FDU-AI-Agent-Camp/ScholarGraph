"""G2.6 unit: paper_fixture_seed loads OpenAPI fixtures into the database."""

from __future__ import annotations

import asyncio
import json

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import PaperDetail, PaperStatusData
from backend.services.paper_fixture_seed import FIXTURES_DIR, seed_from_fixtures

FIXTURES = FIXTURES_DIR


@pytest.mark.asyncio
async def test_g26_seed_from_fixtures_loads_hss_001_detail(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await seed_from_fixtures(paper_repo, pipeline_repo)

    detail = await paper_repo.get("hss-001")
    assert detail is not None
    assert detail.status.value == "ready"


def test_g26_classify_fallback_fixtures_validate_independently() -> None:
    status_payload = json.loads((FIXTURES / "paper-status-classify-fallback.json").read_text(encoding="utf-8"))
    detail_payload = json.loads((FIXTURES / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))

    status = PaperStatusData.model_validate(status_payload["data"])
    detail = PaperDetail.model_validate(detail_payload["data"])

    assert status.classify_warnings == ["classifier_heuristic_fallback"]
    assert detail.classify_warnings == ["classifier_heuristic_fallback"]
