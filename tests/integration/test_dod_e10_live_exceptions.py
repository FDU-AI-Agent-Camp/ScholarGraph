"""V1 DoD §6.5 E-10 — live 异常路径（无效 Key / 超时）.

与 ``scripts/probe_e10_live_exceptions.py`` 抽验对齐；无效 Key 用例不依赖有效 MaaS Key。
超时用例在无 Key 时用 mock 模拟，有 Key 时可选 ``pytest -m live_e10`` 打真云。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from backend.config import get_settings
from backend.graph.qa import QaEvent, _GraphQaEngine, qa_stream
from backend.graph.store import GraphStore
from backend.llm.client import LlmClient, reset_llm_client_cache
from httpx import AsyncClient

from tests.helpers.patrol_graphs import seed_patrol_graphs

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

INVALID_E10_KEY = "invalid-e10-test-key-not-valid"
MAAS_V2_BASE = "https://api.modelarts-maas.com/v2"


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((event_name, payload))
    return events


def _bind_live_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", INVALID_E10_KEY)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_API_BASE_URL", MAAS_V2_BASE)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.fixture
def live_invalid_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _bind_live_invalid_key(monkeypatch)
    yield
    get_settings.cache_clear()
    reset_llm_client_cache()


def test_e10_live_maas_invalid_key_returns_401() -> None:
    """无效 Key：直连 MaaS 返回 401 / ModelArts.81003."""
    response = httpx.post(
        f"{MAAS_V2_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {INVALID_E10_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 8,
        },
        timeout=30.0,
    )
    assert response.status_code == 401
    payload = response.json()
    code = payload.get("error_code") or (payload.get("error") or {}).get("code")
    assert code == "ModelArts.81003"


@pytest.mark.asyncio
async def test_e10_live_qa_sse_invalid_key_emits_qa_stream_error(
    api_client: AsyncClient,
    graph_hss_fixture_env: Path,
    live_invalid_key_env: None,
) -> None:
    """无效 Key：QA SSE → QA_STREAM_ERROR + done（非 HTTP 500）."""
    _ = graph_hss_fixture_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点是什么？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    error = next((payload for name, payload in events if name == "error"), None)
    assert error is not None
    assert error["code"] == "QA_STREAM_ERROR"
    assert error["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_e10_live_patrol_invalid_key_uses_template_fallback(
    api_client: AsyncClient,
    tmp_path: Path,
    live_invalid_key_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无效 Key：Patrol → 200 + 模板摘要 fallback（非 500）."""
    graph_dir = tmp_path / "graphs"
    seed_patrol_graphs(
        graph_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )

    assert response.status_code == 200
    summary = response.json()["data"]["insights"][0]["summary"]
    assert "分析视角" in summary
    assert "Mock" not in summary


@pytest.mark.asyncio
async def test_e10_qa_timeout_emits_qa_stream_error(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超时：LLM 调用超时 → QA_STREAM_ERROR（mock 慢流，不依赖外网）."""

    class _TimeoutChat:
        async def astream(self, _prompt: str) -> AsyncIterator[object]:
            raise TimeoutError("LLM request timed out after 1 seconds")
            yield  # pragma: no cover

    class _TimeoutLlm:
        def __init__(self) -> None:
            self.chat = _TimeoutChat()

    engine = _GraphQaEngine(store=GraphStore(base_dir=mock_llm_env), llm=_TimeoutLlm())

    async def _timeout_stream(paper_id: str, question: str) -> AsyncIterator[QaEvent]:
        async for evt in engine.stream(paper_id, question):
            yield evt

    monkeypatch.setattr("backend.graph.qa.qa_stream", _timeout_stream)

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "会超时吗？"},
    )
    events = _parse_sse(response.text)
    error = next((payload for name, payload in events if name == "error"), None)
    assert error is not None
    assert error["code"] == "QA_STREAM_ERROR"
    assert "timed out" in error["message"].lower() or "timeout" in error["message"].lower()


def _has_valid_live_key() -> bool:
    settings = get_settings()
    return settings.is_llm_live and bool(settings.scholargraph_api_key.strip())


@pytest.mark.live_e10
@pytest.mark.asyncio
async def test_e10_live_qa_timeout_with_real_maas(
    graph_hss_fixture_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超时（真云）：LLM_TIMEOUT_SECONDS=1 + 有效 Key → QA_STREAM_ERROR."""
    if not _has_valid_live_key():
        pytest.skip("SCHOLARGRAPH_API_KEY not configured for live_e10")

    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_hss_fixture_env))
    get_settings.cache_clear()
    reset_llm_client_cache()

    events: list[tuple[str, dict]] = []
    async for evt in qa_stream("hss-001", "请详细展开核心论点、分论点与理论视角的完整论证链条。"):
        events.append((evt.event, evt.data))

    error = next((data for name, data in events if name == "error"), None)
    if error is None:
        pytest.skip("MaaS responded within 1s; timeout not triggered on this run")
    assert error["code"] == "QA_STREAM_ERROR"
    message = str(error["message"]).lower()
    if any(token in message for token in ("429", "too many requests", "81101", "rate limit")):
        pytest.skip("MaaS rate limited; retry live_e10 later")
    assert any(token in message for token in ("timeout", "timed out", "time out", "超时", "request timed out"))


def test_e10_live_mode_missing_key_still_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """回归：live 缺 Key 时 LlmClient 早失败."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with pytest.raises(ValueError, match="缺少 LLM API Key"):
        LlmClient()
