"""B10 boundary ② — vector retrieval timeout + L2 lazy chunk preview patch."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.qa_samples import STEM_DEMO_PAPER_ID, seed_stem_qa_graph
from backend.llm.client import reset_llm_client_cache
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.rag.models import QuestionScale, RetrievalContext
from backend.rag.static_mock_vector_store import StaticMockVectorStore
from backend.schemas.chunk_preview import CHUNK_PREVIEW_STATE_MESSAGES, ChunkPreviewState
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service
from backend.services.qa_retrieval import (
    VECTOR_RETRIEVAL_TIMEOUT_CODE,
    build_retrieval_context_with_fallback,
)

from tests.graph.test_qa import _fake_llm
from tests.helpers.b10_qa_boundary import chunk_citations, collect_qa_events


class _SlowGetChunkStore(StaticMockVectorStore):
    """Vector store whose L2 lookup exceeds the 200 ms B10 gate."""

    def __init__(self, *, delay_seconds: float = 0.5) -> None:
        base = StaticMockVectorStore.load_default()
        super().__init__(base._chunks_by_paper)  # noqa: SLF001
        self._delay_seconds = delay_seconds

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        await asyncio.sleep(self._delay_seconds)
        return await super().get_chunk_text(paper_id, chunk_id)


@pytest.fixture
def stem_qa_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_hybrid_retriever()
    reset_llm_client_cache()
    seed_stem_qa_graph(graph_dir, paper_id=STEM_DEMO_PAPER_ID)
    return STEM_DEMO_PAPER_ID, graph_dir


async def _slow_retrieve(*_args, **_kwargs) -> RetrievalContext:
    """Simulate HybridRetriever vector branch sleeping past the QA retrieval fuse."""
    await asyncio.sleep(0.05)
    return RetrievalContext(
        scale=QuestionScale.DETAIL,
        chunks=[
            # Would have been returned if retrieve finished — must NOT appear after timeout.
        ],
    )


@pytest.mark.asyncio
async def test_retrieval_timeout_emits_warning_and_graph_only_context(
    stem_qa_env: tuple[str, Path],
) -> None:
    """4s-equivalent: slow retrieve + 3s fuse (scaled to 50ms/10ms in test) triggers graph-only."""
    paper_id, graph_dir = stem_qa_env
    from backend.graph.store import GraphStore

    retriever = HybridRetriever(vector_store=StaticMockVectorStore.load_default())
    retriever.retrieve = _slow_retrieve  # type: ignore[method-assign]
    bind_hybrid_retriever(retriever)

    paper_service = get_paper_service()
    paper = await paper_service.get_paper(paper_id)
    assert paper.status == PaperStatus.READY

    result = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=GraphStore(base_dir=graph_dir),
        timeout_seconds=0.01,
    )

    assert result.warning_event is not None
    assert result.warning_event["code"] == VECTOR_RETRIEVAL_TIMEOUT_CODE
    assert result.context is not None
    assert result.context.chunks == []


@pytest.mark.asyncio
async def test_l2_lazy_lookup_recovers_chunk_text_after_retrieval_timeout(
    stem_qa_env: tuple[str, Path],
) -> None:
    """After graph-only fallback, L2 must fetch indexed chunk within 200 ms and emit ready preview."""
    paper_id, graph_dir = stem_qa_env
    from backend.graph.store import GraphStore

    mock_store = StaticMockVectorStore.load_default()
    retriever = HybridRetriever(vector_store=mock_store)
    retriever.retrieve = _slow_retrieve  # type: ignore[method-assign]
    bind_hybrid_retriever(retriever)

    paper_service = get_paper_service()
    store = GraphStore(base_dir=graph_dir)
    retrieval = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        timeout_seconds=0.01,
    )
    assert retrieval.warning_event is not None

    chunk_id = "stem-001:chunk:42"
    llm_text = f"准确率见原文[CITE:chunk:{chunk_id}]。"
    events = await collect_qa_events(
        qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
            retrieval_context=retrieval.context,
            retrieval_warning=retrieval.warning_event,
            llm=_fake_llm(llm_text),
        ),
    )

    cites = chunk_citations(events)
    assert len(cites) == 1, events
    cite = cites[0]
    assert cite["chunk_id"] == chunk_id
    assert cite["preview_state"] == ChunkPreviewState.READY
    assert "78.5%" in cite["text_preview"]
    assert cite["text_preview"] != CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.RETRIEVAL_TIMEOUT]


@pytest.mark.asyncio
async def test_l2_lazy_lookup_times_out_after_retrieval_timeout(
    stem_qa_env: tuple[str, Path],
) -> None:
    """When L2 lookup itself exceeds 200 ms, emit vector-timeout placeholder (l2_timeout)."""
    paper_id, graph_dir = stem_qa_env
    from backend.graph.store import GraphStore

    slow_store = _SlowGetChunkStore(delay_seconds=0.5)
    retriever = HybridRetriever(vector_store=slow_store)
    retriever.retrieve = _slow_retrieve  # type: ignore[method-assign]
    bind_hybrid_retriever(retriever)

    paper_service = get_paper_service()
    store = GraphStore(base_dir=graph_dir)
    retrieval = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        timeout_seconds=0.01,
    )

    chunk_id = "stem-001:chunk:42"
    llm_text = f"引用[CITE:chunk:{chunk_id}]。"
    events = await collect_qa_events(
        qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
            retrieval_context=retrieval.context,
            retrieval_warning=retrieval.warning_event,
            llm=_fake_llm(llm_text),
        ),
    )

    cites = chunk_citations(events)
    assert len(cites) == 1
    cite = cites[0]
    assert cite["preview_state"] in {
        ChunkPreviewState.L2_TIMEOUT,
        ChunkPreviewState.RETRIEVAL_TIMEOUT,
    }
    assert cite["text_preview"] == CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.RETRIEVAL_TIMEOUT]
    assert cite["text_preview"] != ""
