"""V1 DoD §6.5 E-01～E-05 — 边界鲁棒性前后端联调联试（BE 侧）.

与 ``frontend/src/test/v1-dod-e01-e05-fe-be.integration.test.ts`` 成对：
图谱未就绪、论文不存在、上传失败、流水线失败、巡检 paper_ids 边界。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.services.paper_service import MAX_UPLOAD_BYTES, get_paper_service
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope, assert_success_envelope

VALID_PDF = b"%PDF-1.4\n% E-01-E-05 FE-BE upload test"
READY_ID = "hss-001"
PROCESSING_ID = "hss-002"
FAILED_ID = "hss-failed-001"
GHOST_ID = "ghost-e01-e05-404"


# ---------------------------------------------------------------------------
# E-01 — 图谱未就绪 / 就绪
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e01_green_ready_paper_graph_returns_200(api_client: AsyncClient) -> None:
    """E-01 功能：ready 论文 GET graph → 200 + UnifiedPaperGraph."""
    response = await api_client.get(f"/api/v1/papers/{READY_ID}/graph")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["paper_id"] == READY_ID
    assert len(body["data"]["nodes"]) >= 1


@pytest.mark.asyncio
async def test_e01_red_processing_paper_graph_returns_graph_not_ready(api_client: AsyncClient) -> None:
    """E-01 红灯：processing 论文 GET graph → 409 GRAPH_NOT_READY + 可读 message."""
    response = await api_client.get(f"/api/v1/papers/{PROCESSING_ID}/graph")
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert body["error"]["message"]


@pytest.mark.asyncio
async def test_e01_processing_status_confirms_not_ready_before_graph(api_client: AsyncClient) -> None:
    """E-01 边界：processing status 与 graph 409 语义一致."""
    status_resp = await api_client.get(f"/api/v1/papers/{PROCESSING_ID}/status")
    graph_resp = await api_client.get(f"/api/v1/papers/{PROCESSING_ID}/graph")

    assert status_resp.json()["data"]["status"] == "processing"
    assert graph_resp.status_code == 409
    assert_error_envelope(graph_resp.json(), code="GRAPH_NOT_READY")


@pytest.mark.asyncio
async def test_e01_red_failed_paper_graph_also_graph_not_ready(api_client: AsyncClient) -> None:
    """E-01 红灯：failed 论文亦不可拉图谱."""
    response = await api_client.get(f"/api/v1/papers/{FAILED_ID}/graph")
    assert response.status_code == 409
    assert_error_envelope(response.json(), code="GRAPH_NOT_READY")


# ---------------------------------------------------------------------------
# E-02 — 论文不存在
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix",
    ["", "/status", "/graph"],
)
async def test_e02_paper_not_found_on_core_endpoints(
    api_client: AsyncClient,
    suffix: str,
) -> None:
    """E-02：不存在论文在详情 / status / graph → 404 PAPER_NOT_FOUND."""
    response = await api_client.get(f"/api/v1/papers/{GHOST_ID}{suffix}")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")
    assert response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# E-03 — 上传边界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e03_red_non_pdf_returns_ingest_failed(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-03 红灯：非 PDF 内容 → 400 INGEST_FAILED."""
    from backend.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("fake.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")


@pytest.mark.asyncio
async def test_e03_red_oversized_pdf_returns_ingest_failed_with_size_hint(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-03 红灯：超过 32MB → 400 INGEST_FAILED + 大小提示."""
    from backend.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    oversized = b"%PDF" + b"x" * (MAX_UPLOAD_BYTES + 1)
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("big.pdf", oversized, "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    assert_error_envelope(body, code="INGEST_FAILED")
    assert "32MB" in body["error"]["message"]


@pytest.mark.asyncio
async def test_e03_green_valid_pdf_upload_returns_pending(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-03 功能：合法 PDF → 201 pending."""
    from backend.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("ok.pdf", VALID_PDF, "application/pdf")},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["paper_id"]


# ---------------------------------------------------------------------------
# E-04 — 流水线失败
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e04_failed_status_exposes_error_code_failed_during_message(
    api_client: AsyncClient,
) -> None:
    """E-04：failed status 含 error_code + failed_during + message（FE 红面板数据源）."""
    response = await api_client.get(f"/api/v1/papers/{FAILED_ID}/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "LLM_JSON_INVALID"
    assert data["failed_during"] == "classifying"
    assert "JSON" in data["message"] or data["message"]


@pytest.mark.asyncio
async def test_e04_failed_paper_detail_still_fetchable(api_client: AsyncClient) -> None:
    """E-04 边界：failed 论文详情可 200，由 status 驱动 FE 禁用问答."""
    response = await api_client.get(f"/api/v1/papers/{FAILED_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "failed"


# ---------------------------------------------------------------------------
# E-05 — 巡检 paper_ids 数量
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "paper_ids",
    [
        [],
        ["hss-001"],
        ["hss-001", "hss-002", "hss-003"],
    ],
)
async def test_e05_patrol_invalid_paper_count_returns_422_not_500(
    api_client: AsyncClient,
    paper_ids: list[str],
) -> None:
    """E-05 红灯：paper_ids 数量 ≠ 2 → 422（Pydantic detail 或 error envelope）."""
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": paper_ids, "mode": "lens_clash"},
    )
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body or "error" in body


@pytest.mark.asyncio
async def test_e05_patrol_valid_two_papers_functional_when_graphs_ready(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-05 功能对照：恰好 2 篇且图谱就绪时巡检可 200."""
    from tests.helpers.patrol_graphs import seed_patrol_graphs

    seed_patrol_graphs(
        mock_llm_env,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 200
    assert_success_envelope(response.json())
