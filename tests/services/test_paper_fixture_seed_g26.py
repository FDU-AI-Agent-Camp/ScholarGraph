"""G2.6 unit: paper_fixture_seed loads OpenAPI fixtures."""

from __future__ import annotations

import json

from backend.schemas.paper import PaperDetail, PaperStatusData
from backend.services.paper_fixture_seed import FIXTURES_DIR, seed_from_fixtures
from backend.services.paper_service import PaperService

FIXTURES = FIXTURES_DIR


def test_g26_seed_from_fixtures_loads_hss_001_detail() -> None:
    service = PaperService()
    service._papers.clear()
    service._status.clear()
    seed_from_fixtures(service)

    assert "hss-001" in service._papers
    detail = service._papers["hss-001"]
    assert detail.status.value == "ready"
    assert detail.classify_warnings == []


def test_g26_classify_fallback_fixtures_validate_independently() -> None:
    status_payload = json.loads((FIXTURES / "paper-status-classify-fallback.json").read_text(encoding="utf-8"))
    detail_payload = json.loads((FIXTURES / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))

    status = PaperStatusData.model_validate(status_payload["data"])
    detail = PaperDetail.model_validate(detail_payload["data"])

    assert status.classify_warnings == ["classifier_heuristic_fallback"]
    assert detail.classify_warnings == ["classifier_heuristic_fallback"]
