"""Benchmark mock-mode STEM full-path smoke (A+B retrieval → SSE → guardrails)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.llm.client import get_judge_llm_client, get_qa_llm_client, reset_llm_client_cache
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.static_mock_vector_store import StaticMockVectorStore
from backend.services.qa_service import QaService
from tests.conftest import REPO_ROOT

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa_stem_mock", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa_stem_mock"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mock_benchmark_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    get_settings.cache_clear()
    reset_llm_client_cache()
    yield graph_dir
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_benchmark_stem_detail_mock_path_numeric_and_chunk_recall(
    benchmark_qa_module,
    mock_benchmark_env: Path,
) -> None:
    mod = benchmark_qa_module
    os.environ["GRAPH_DATA_DIR"] = str(mock_benchmark_env)

    golden_path = mock_benchmark_env / "stem_golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "test",
                "allowed_recall_floor": 0.80,
                "items": [
                    {
                        "id": "stem-001-q13",
                        "question": (
                            "What is the top-1 accuracy of the proposed ResNet-Light model "
                            "on the ImageNet dataset, and what was the learning rate?"
                        ),
                        "paradigm": "STEM",
                        "paper_id": "stem-001",
                        "scale": "detail",
                        "gold": {
                            "nodes": ["n_method", "n_dataset"],
                            "edges": ["e_eval"],
                            "paragraphs": ["stem-001:chunk:42", "stem-001:chunk:43"],
                            "required_patterns": ["78.5%", "ImageNet", "0.001"],
                            "forbidden_patterns": ["ResNet-50", "90%"],
                            "numeric_rel_tol": 0.001,
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    mod._build_benchmark_qa_service(mock_benchmark_env)
    golden = mod.load_golden_set(golden_path)
    item = golden["items"][0]
    qa_service = QaService(
        store=GraphStore(base_dir=mock_benchmark_env),
        hybrid_retriever=HybridRetriever(vector_store=StaticMockVectorStore.load_default()),
        paper_service=mod._build_benchmark_paper_service(),
    )

    result = await mod.run_full_eval(
        item,
        paper_id="stem-001",
        qa_client=get_qa_llm_client(),
        judge_client=get_judge_llm_client(),
        qa_service=qa_service,
    )

    assert result["error_code"] is None
    assert result["numeric_match"] is True
    assert result.get("chunk_recall") is not None
    assert result["chunk_recall"] > 0.0
    assert result["evaluation"]["faithfulness"]["hallucination_rate"] == 0.0
