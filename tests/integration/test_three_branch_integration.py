"""
三分支联调：BE-1 ingest（真） + BE-L platform workflow/HTTP（真） + FE 契约（fixtures）。

语料 PDF 未就位时相关用例 skip；不 mock ingest。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.graph.workflow import run_paper_pipeline
from backend.main import app
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError
from httpx import ASGITransport, AsyncClient

from tests.conftest import mock_agent_services_only
from tests.helpers.classifier_labels import labels_by_paper_id
from tests.helpers.status_contract import assert_snapshot_matches_contract
from tests.ingest.conftest import CORPUS_HSS, CORPUS_PAPER_IDS, CORPUS_STEM, register_pending_paper
from tests.ingest.test_corpus_smoke import TITLE_HINTS

pytestmark = [pytest.mark.integration, pytest.mark.three_branch]

STEM_PAPER_ID = "three-branch-stem"
HSS_PAPER_ID = "three-branch-hss"


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _require_corpus_pdf(path: Path) -> Path:
    if not path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {path}")
    return path


async def test_three_branch_real_ingest_feeds_classifier_input_to_platform() -> None:
    """BE-1 ingest_pdf → platform classify_node 接收真实 classifier_input。"""
    pdf_path = _require_corpus_pdf(CORPUS_STEM)
    register_pending_paper(STEM_PAPER_ID, title=labels_by_paper_id()["stem-001"]["title"])
    captured_inputs: list[str] = []

    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.9,
        reason="mock after real ingest",
    )

    with mock_agent_services_only(STEM_PAPER_ID) as mocks:

        async def capture_classify(text: str) -> ParadigmClassification:
            captured_inputs.append(text)
            return classification

        mocks["agent"].classify_paradigm.side_effect = capture_classify
        final = await run_paper_pipeline(STEM_PAPER_ID, pdf_path)

    assert final.get("failed") is not True
    assert len(captured_inputs) == 1
    snippet = captured_inputs[0]
    assert snippet.strip()
    for hint in TITLE_HINTS["stem-001"]:
        if hint.isascii():
            assert hint.lower() in snippet.lower()
        else:
            assert hint in snippet


async def test_three_branch_http_status_ready_after_real_ingest_and_mock_downstream(
    api_client: AsyncClient,
) -> None:
    """ingest + mock classify/extract/store 后，FE 可读 status=ready 契约。"""
    pdf_path = _require_corpus_pdf(CORPUS_STEM)
    register_pending_paper(STEM_PAPER_ID, title="three-branch HTTP smoke")

    with mock_agent_services_only(STEM_PAPER_ID):
        await run_paper_pipeline(STEM_PAPER_ID, pdf_path)

    response = await api_client.get(f"/api/v1/papers/{STEM_PAPER_ID}/status")
    assert response.status_code == 200
    data = response.json()["data"]
    snapshot = PaperStatusData.model_validate(data)
    assert_snapshot_matches_contract(snapshot)
    assert snapshot.status == PaperStatus.READY
    assert snapshot.stage == PipelineStage.READY

    detail = await api_client.get(f"/api/v1/papers/{STEM_PAPER_ID}")
    assert detail.status_code == 200
    assert detail.json()["data"]["paradigm"] == Paradigm.STEM.value


async def test_three_branch_http_status_failed_during_classify_after_real_ingest(
    api_client: AsyncClient,
) -> None:
    """ingest 成功后 classify 失败 → status 含 failed_during=classifying（FE 失败态 UI）。"""
    pdf_path = _require_corpus_pdf(CORPUS_HSS)
    register_pending_paper(HSS_PAPER_ID, title=labels_by_paper_id()["hss-001"]["title"])

    with mock_agent_services_only(HSS_PAPER_ID) as mocks:
        mocks["agent"].classify_paradigm.side_effect = ServiceError(
            "LLM_JSON_INVALID",
            "范式分类 JSON 无效",
        )
        final = await run_paper_pipeline(HSS_PAPER_ID, pdf_path)

    assert final.get("failed") is True
    assert final.get("error_code") == "LLM_JSON_INVALID"

    response = await api_client.get(f"/api/v1/papers/{HSS_PAPER_ID}/status")
    assert response.status_code == 200
    snapshot = PaperStatusData.model_validate(response.json()["data"])
    assert snapshot.status == PaperStatus.FAILED
    assert snapshot.error_code == "LLM_JSON_INVALID"
    assert snapshot.failed_during == PipelineStage.CLASSIFYING
    assert_snapshot_matches_contract(snapshot)


@pytest.mark.parametrize("paper_id", CORPUS_PAPER_IDS)
async def test_three_branch_gold_labels_match_corpus_classifier_snippets(paper_id: str) -> None:
    """金标 CSV ↔ 语料 ingest 切片关键词一致（供 BE-2 评测）。"""
    from backend.ingest.pdf import ingest_pdf

    pdf_path = Path("data/corpus") / f"{paper_id}.pdf"
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    label = labels_by_paper_id()[paper_id]
    snippet = (await ingest_pdf(pdf_path, paper_id=paper_id))["classifier_input"]

    for hint in TITLE_HINTS[paper_id]:
        if hint.isascii():
            assert hint.lower() in snippet.lower(), f"{paper_id}: missing {hint!r}"
        else:
            assert hint in snippet, f"{paper_id}: missing {hint!r}"
    assert label["paradigm_gold"] in ("STEM", "HSS")
