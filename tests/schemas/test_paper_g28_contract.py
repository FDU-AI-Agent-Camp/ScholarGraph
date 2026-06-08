"""G2.8: ParadigmClassification contract unchanged; classify_warnings is a sibling field."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
API_CONTRACT_KEYS = frozenset({"paradigm", "confidence", "reason"})


def test_g28_paradigm_classification_model_fields_match_api_contract() -> None:
    fields = set(ParadigmClassification.model_fields.keys())
    assert fields == API_CONTRACT_KEYS


def test_g28_paper_detail_serializes_classification_and_warnings_separately() -> None:
    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="g28-contract",
        title="contract",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        classification=ParadigmClassification(
            paradigm=Paradigm.HSS,
            confidence=0.88,
            reason="Qualitative framing.",
        ),
        classify_warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    )
    payload = json.loads(detail.model_dump_json())

    assert set(payload["classification"].keys()) == API_CONTRACT_KEYS
    assert "classify_warnings" not in payload["classification"]
    assert payload["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_g28_openapi_paradigm_classification_has_no_classify_warnings() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    paradigm_schema = spec["components"]["schemas"]["ParadigmClassification"]

    assert set(paradigm_schema["required"]) == API_CONTRACT_KEYS
    assert set(paradigm_schema["properties"].keys()) == API_CONTRACT_KEYS
    assert "classify_warnings" not in paradigm_schema["properties"]
