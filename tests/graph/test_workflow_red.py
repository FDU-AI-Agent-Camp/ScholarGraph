"""
红灯测试（Red tests）

在 BE 模块尚未交付前，这些用例**预期失败**（xfail strict）。
当 BE-1～2 实现对应 Service 后，应去掉 xfail 直至全部转绿。

ingest 语料详细红灯见 tests/ingest/test_red_corpus.py。

运行：uv run pytest -m red -rx
默认 CI / 日常：uv run pytest -m "not red"
"""

from pathlib import Path

import pytest
from backend.agents.classifier import classify
from backend.agents.extractor import extract
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service

# BE-1 ingest 红灯已迁移至 tests/ingest/test_red_corpus.py


@pytest.mark.red
@pytest.mark.xfail(strict=True, reason="BE-2: classify 尚未实现")
async def test_classify_returns_stem_or_hss_for_snippet() -> None:
    snippet = "We evaluate our agent framework on benchmark datasets with accuracy metrics."
    result = await classify(snippet)
    assert result.paradigm in (Paradigm.STEM, Paradigm.HSS)
    assert 0.0 <= result.confidence <= 1.0
    assert result.reason.strip()


@pytest.mark.red
@pytest.mark.xfail(strict=True, reason="BE-2: extract 尚未实现")
async def test_extract_returns_valid_graph_for_hss_text() -> None:
    text = "本文采用历史制度主义分析近代通商口岸的制度变迁。"
    graph = await extract(text, Paradigm.HSS)
    assert graph.nodes
    assert graph.paper_id or graph.paradigm == Paradigm.HSS


@pytest.mark.red
@pytest.mark.xfail(strict=True, reason="BE-1～2: 全链路未接真实 Service")
async def test_pipeline_end_to_end_without_service_mocks(workflow_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = workflow_paper
    final = await run_paper_pipeline(paper_id, pdf_path)
    assert final.get("failed") is not True
    assert final.get("status") == "ready"

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status.value == "ready"
    graph = await get_paper_service().get_graph(paper_id)
    assert len(graph.nodes) >= 1
