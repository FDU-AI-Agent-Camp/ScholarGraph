"""V1 DoD §6.4 D-07～D-12 — 治理项前后端联调联试（BE 侧）.

与 ``frontend/src/test/v1-dod-d-fe-be-governance.integration.test.ts`` 成对：
功能可用（handoff 经平台路由接线）、边界鲁棒、红灯路径 envelope/可读 message。
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.patrol.errors import PatrolError
from backend.schemas.patrol import PatrolMode
from backend.services.patrol_service import PatrolService
from httpx import AsyncClient
from scripts.d_gates_lib import (
    REPO_ROOT,
    api_route_handlers_missing_docstrings,
    backend_files_defining_api_router_outside_platform,
    backend_python_files_exceeding_line_budget,
    git_paths_are_ignored,
    git_sensitive_paths_must_not_be_tracked,
    lockfile_declares_npm_package,
    lockfile_declares_python_project,
    scan_handoff_modules_for_private_routes,
)

from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.helpers.patrol_graphs import seed_patrol_graphs

PAPERS_ROUTE = REPO_ROOT / "backend" / "api" / "routes" / "papers.py"


# ---------------------------------------------------------------------------
# D-07 — handoff：业务模块不私自注册路由，经 BE-L 平台层可用
# ---------------------------------------------------------------------------


def test_d07_handoff_modules_have_no_private_routers() -> None:
    violations = scan_handoff_modules_for_private_routes()
    assert not violations, violations


def test_d07_only_platform_layer_defines_api_router() -> None:
    leaks = backend_files_defining_api_router_outside_platform()
    assert not leaks, f"APIRouter outside platform: {leaks}"


def test_d07_qa_route_delegates_to_graph_qa_stream() -> None:
    """D-07 功能：SSE 路由在 papers.py 内延迟导入 qa_stream，而非在 graph 模块注册 HTTP。"""
    source = PAPERS_ROUTE.read_text(encoding="utf-8")
    assert "from backend.graph.qa import qa_stream" in source
    assert "async for evt in qa_stream" in source


@pytest.mark.asyncio
async def test_d07_green_patrol_http_uses_service_facade_not_module_router(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """D-07 功能：POST /patrol 经 PatrolService → backend.patrol.run_patrol 返回 200。"""
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
    assert response.json()["data"]["insights"]


@pytest.mark.asyncio
async def test_d07_red_patrol_service_maps_patrol_error_to_api_envelope(
    mock_llm_env: Path,
) -> None:
    """D-07 红灯：PatrolError → ApiError，供路由层返回标准 error envelope。"""
    _ = mock_llm_env
    vector_store = AsyncMock()
    service = PatrolService(vector_store=vector_store)

    with patch(
        "backend.services.patrol_service.patrol_run",
        new=AsyncMock(
            side_effect=PatrolError(
                "PATROL_INSUFFICIENT_DATA",
                "缺少 Thesis 节点",
                status_code=422,
            ),
        ),
    ):
        from backend.api.exceptions import ApiError

        with pytest.raises(ApiError) as exc_info:
            await service.run_patrol(["hss-001", "hss-002"], PatrolMode.CONTRADICTION)

    assert exc_info.value.code == "PATROL_INSUFFICIENT_DATA"
    assert exc_info.value.status_code == 422
    assert "Thesis" in exc_info.value.message


def test_d07_patrol_service_is_thin_delegate_under_d12_budget() -> None:
    """D-12：PatrolService 仅委托 run_patrol，无 HTTP 接线逻辑。"""
    source = (REPO_ROOT / "backend" / "services" / "patrol_service.py").read_text(encoding="utf-8")
    assert "patrol_run" in source
    assert "APIRouter" not in source
    # Cache fingerprint / degrade-skip branches grow the method; keep it a thin delegate.
    assert len(inspect.getsource(PatrolService.run_patrol).splitlines()) < 40


# ---------------------------------------------------------------------------
# D-08 — API error envelope（与 FE ApiClientError 对齐）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d08_red_paper_not_found_envelope_for_fe_client(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    _ = mock_llm_env
    response = await api_client.get("/api/v1/papers/ghost-d08-404")
    assert response.status_code == 404
    body = response.json()
    assert_error_envelope(body, code="PAPER_NOT_FOUND")
    assert body["error"]["message"]


@pytest.mark.asyncio
async def test_d08_red_patrol_invalid_count_returns_422_not_500(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001"], "mode": "lens_clash"},
    )
    assert response.status_code == 422
    body = response.json()
    assert "error" in body or "detail" in body


@pytest.mark.asyncio
async def test_d08_green_success_envelope_includes_request_id(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    _ = mock_llm_env
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["meta"]["request_id"]


# ---------------------------------------------------------------------------
# D-09 — 敏感文件不入库
# ---------------------------------------------------------------------------


def test_d09_sensitive_paths_not_tracked_by_git() -> None:
    tracked = git_sensitive_paths_must_not_be_tracked()
    assert not tracked, f"sensitive files tracked: {tracked}"


def test_d09_git_check_ignore_covers_env_and_progress() -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git work tree")
    not_ignored = git_paths_are_ignored((".env", "progress.md", ".cursor/"))
    assert not not_ignored, f"paths not gitignored: {not_ignored}"


# ---------------------------------------------------------------------------
# D-10 — lock 与 manifest 同步
# ---------------------------------------------------------------------------


def test_d10_uv_lock_declares_python_project() -> None:
    assert lockfile_declares_python_project("scholargraph")


def test_d10_package_lock_declares_frontend_package() -> None:
    assert lockfile_declares_npm_package("scholargraph-frontend")


# ---------------------------------------------------------------------------
# D-11 — 公开 API 文档与 health 契约
# ---------------------------------------------------------------------------


def test_d11_all_route_handlers_documented() -> None:
    missing = api_route_handlers_missing_docstrings()
    assert not missing, missing


@pytest.mark.asyncio
async def test_d11_health_payload_exposes_llm_note_for_fe_banner(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """D-11 功能：health 返回 llm_mode / llm_note，供 FE 展示 Mock 提示。"""
    _ = mock_llm_env
    response = await api_client.get("/api/v1/health")
    data = response.json()["data"]
    assert data["llm_mode"] == "mock"
    assert isinstance(data["llm_note"], str) and data["llm_note"]


@pytest.mark.asyncio
async def test_d11_red_qa_empty_question_422_with_validation_detail(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": ""},
    )
    assert response.status_code == 422
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# D-12 — 避免 God 文件；复杂逻辑有边界
# ---------------------------------------------------------------------------


def test_d12_backend_modules_stay_under_line_budget() -> None:
    offenders = backend_python_files_exceeding_line_budget()
    assert not offenders, offenders


@pytest.mark.asyncio
async def test_d12_green_qa_sse_ends_with_done_after_messages(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """D-12 功能路径：SSE 流式问答完整结束，不中途裸断。"""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点？"},
    )
    assert response.status_code == 200
    events: list[str] = []
    for line in response.text.splitlines():
        if line.startswith("event:"):
            events.append(line.split(":", 1)[1].strip())
    assert events[-1] == "done"
    assert "message" in events
