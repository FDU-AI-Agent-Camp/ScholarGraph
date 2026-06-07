"""
Phase G 红灯测试（classify_warnings 边界）

运行：uv run pytest -m red tests/agents/test_classify_g23_red.py -rx
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service

pytestmark = pytest.mark.red

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.fixture
def registered_paper() -> str:
    paper_id = "g23-red-paper"
    now = datetime.now(UTC)
    service = get_paper_service()
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="g23 red test",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    service._status.pop(paper_id, None)
    service._head_refine_warnings.pop(paper_id, None)
    service._classify_warnings.pop(paper_id, None)
    service._extract_warnings.pop(paper_id, None)
    return paper_id


@pytest.fixture
def live_classify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_red_record_classify_warnings_empty_list_is_noop(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_classify_warnings(registered_paper, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    service.record_classify_warnings(registered_paper, [])

    status = await service.get_status(registered_paper)
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_red_unknown_classify_warning_code_stored_and_returned(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_classify_warnings(registered_paper, ["unknown_future_code"])

    status = await service.get_status(registered_paper)
    paper = await service.get_paper(registered_paper)

    assert status.classify_warnings == ["unknown_future_code"]
    assert paper.classify_warnings == ["unknown_future_code"]


@pytest.mark.asyncio
async def test_red_get_paper_without_recorded_classify_warnings_returns_empty_list(
    registered_paper: str,
) -> None:
    service = get_paper_service()
    service._classify_warnings.pop(registered_paper, None)

    paper = await service.get_paper(registered_paper)

    assert paper.classify_warnings == []


def test_red_paper_detail_model_omitting_classify_warnings_defaults_empty() -> None:
    now = datetime.now(UTC)
    detail = PaperDetail.model_validate(
        {
            "paper_id": "red-detail-default",
            "title": "t",
            "status": "ready",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )
    assert detail.classify_warnings == []


def test_red_paper_status_data_rejects_non_list_classify_warnings() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PaperStatusData(
            paper_id="red-invalid",
            status=PaperStatus.READY,
            percent=100,
            message="ok",
            updated_at=datetime.now(UTC),
            classify_warnings="not-a-list",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_red_classify_and_extract_warnings_are_independent(registered_paper: str) -> None:
    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE

    service = get_paper_service()
    service.record_classify_warnings(registered_paper, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    service.record_extract_warnings(registered_paper, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    status = await service.get_status(registered_paper)

    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_red_head_refine_and_classify_warnings_are_independent(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_head_refine_warnings(registered_paper, ["mineru_unavailable"])
    service.record_classify_warnings(registered_paper, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    status = await service.get_status(registered_paper)

    assert "mineru_unavailable" in status.head_refine_warnings
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_red_live_empty_classifier_input_raises_value_error(live_classify_env: None) -> None:
    _ = live_classify_env
    with pytest.raises(ValueError, match="classifier_input must be a non-empty string"):
        await classify("   ")


@pytest.mark.asyncio
async def test_red_live_no_fallback_raises_service_error(
    live_classify_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = live_classify_env
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        with pytest.raises(ServiceError) as err:
            await classify(STEM_SAMPLE)
    assert err.value.code == "PIPELINE_FAILED"


@pytest.mark.asyncio
async def test_red_mock_mode_never_invokes_classify_with_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert result.warnings == []


@pytest.mark.parametrize(
    ("side_effect", "label"),
    [
        (TimeoutError("api timeout"), "api_timeout"),
        (ConnectionError("network down"), "network_error"),
        (RuntimeError("with_structured_output failed"), "structured_output"),
        (ValueError("json/schema invalid"), "schema_validation"),
    ],
)
@pytest.mark.asyncio
async def test_red_llm_failures_trigger_heuristic_fallback(
    live_classify_env: None,
    side_effect: Exception,
    label: str,
) -> None:
    _ = live_classify_env
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=side_effect),
    ):
        result = await classify(f"{STEM_SAMPLE} [{label}]")

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.classification.reason.strip()


@pytest.mark.asyncio
async def test_red_classifier_llm_disabled_writes_fallback_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings


@pytest.mark.asyncio
async def test_red_classify_with_llm_rejects_whitespace_reason(live_classify_env: None) -> None:
    """G2.1 red: structured output with blank reason fails validation."""
    from unittest.mock import MagicMock

    from backend.agents.classifier_llm import classify_with_llm
    from backend.llm.client import LlmClient
    from backend.schemas.paradigm import Paradigm, ParadigmClassification

    _ = live_classify_env
    bad = ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="   ")
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=bad)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable
    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    with pytest.raises(ValueError, match="reason is empty"):
        await classify_with_llm(STEM_SAMPLE, llm_client=client)


@pytest.mark.asyncio
async def test_red_classify_with_llm_primary_fail_no_fallback_client_raises(live_classify_env: None) -> None:
    """G2.2 red: no fallback_chat → primary failure propagates."""
    from unittest.mock import MagicMock

    from backend.agents.classifier_llm import classify_with_llm
    from backend.llm.client import LlmClient

    _ = live_classify_env
    primary_runnable = MagicMock()
    primary_runnable.ainvoke = AsyncMock(side_effect=RuntimeError("primary only"))
    chat = MagicMock()
    chat.with_structured_output.return_value = primary_runnable
    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    with pytest.raises(RuntimeError, match="primary only"):
        await classify_with_llm(STEM_SAMPLE, llm_client=client)

    primary_runnable.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_red_g25_agent_service_no_fallback_surfaces_pipeline_failed() -> None:
    from backend.services.agent_service import AgentService

    service = AgentService()
    with patch(
        "backend.services.agent_service.classify",
        new=AsyncMock(side_effect=ServiceError("PIPELINE_FAILED", "范式 LLM 分类失败")),
    ):
        with pytest.raises(ServiceError) as err:
            await service.classify_paradigm(STEM_SAMPLE)
    assert err.value.code == "PIPELINE_FAILED"


def test_red_g26_openapi_paper_status_data_lists_classify_warnings() -> None:
    from pathlib import Path

    openapi = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    assert "PaperStatusData:" in text
    assert "classify_warnings:" in text
