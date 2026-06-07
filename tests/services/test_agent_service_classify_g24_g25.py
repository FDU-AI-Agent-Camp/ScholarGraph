"""G2.4–G2.5 AgentService classify delegation tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.classifier_types import ClassifyResult
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError

STEM_SAMPLE = "Title: benchmark dataset accuracy F1 baseline ablation."


@pytest.mark.asyncio
async def test_g24_agent_service_returns_classify_warnings_when_llm_disabled_path() -> None:
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.75,
        reason="Heuristic STEM match.",
    )
    expected = ClassifyResult(
        classification=classification,
        warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    )
    service = AgentService()
    with patch("backend.services.agent_service.classify", new_callable=AsyncMock) as raw:
        raw.return_value = expected
        result = await service.classify_paradigm(STEM_SAMPLE)

    assert result.warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert result.classification.paradigm == Paradigm.STEM


@pytest.mark.asyncio
async def test_g25_agent_service_propagates_pipeline_failed_from_classify() -> None:
    service = AgentService()
    with patch("backend.services.agent_service.classify", new_callable=AsyncMock) as raw:
        raw.side_effect = ServiceError("PIPELINE_FAILED", "范式 LLM 分类失败: simulated")
        with pytest.raises(ServiceError) as err:
            await service.classify_paradigm(STEM_SAMPLE)
    assert err.value.code == "PIPELINE_FAILED"
