"""B10 boundary ③ — LLM hallucinated chunk_id on indexed stem-001."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.qa_samples import STEM_DEMO_PAPER_ID, seed_stem_qa_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.rag.static_mock_vector_store import StaticMockVectorStore
from backend.schemas.chunk_preview import CHUNK_PREVIEW_STATE_MESSAGES, ChunkPreviewState
from backend.services.paper_service import get_paper_service
from backend.services.qa_retrieval import build_retrieval_context_with_fallback

from tests.graph.test_qa import _fake_llm
from tests.helpers.b10_qa_boundary import chunk_citations, collect_qa_events


@pytest.fixture
def stem_indexed_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, GraphStore]:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_hybrid_retriever()
    reset_llm_client_cache()

    paper_id = STEM_DEMO_PAPER_ID
    seed_stem_qa_graph(graph_dir, paper_id=paper_id)
    store = GraphStore(base_dir=graph_dir)

    mock_vectors = StaticMockVectorStore.load_default()
    retriever = HybridRetriever(vector_store=mock_vectors)
    bind_hybrid_retriever(retriever)

    return paper_id, store


@pytest.mark.asyncio
async def test_hallucinated_chunk_id_emits_verification_failed_placeholder(
    stem_indexed_env: tuple[str, GraphStore],
) -> None:
    """Indexed stem-001 + fake chunk cite → L2 miss → hallucinated_id state token."""
    paper_id, graph_store = stem_indexed_env
    paper_service = get_paper_service()

    retrieval = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=HybridRetriever(vector_store=StaticMockVectorStore.load_default()),
        paper_service=paper_service,
        store=graph_store,
    )
    assert retrieval.context is not None

    fake_chunk_id = "stem-001_chunk_99999"
    llm_text = f"详见[CITE:chunk:{fake_chunk_id}]。"
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
    assert cite["chunk_id"] == fake_chunk_id
    assert cite["preview_state"] == ChunkPreviewState.HALLUCINATED_ID
    assert cite["text_preview"] == CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.HALLUCINATED_ID]
    assert cite["text_preview"] != ""


@pytest.mark.asyncio
async def test_hallucinated_canonical_chunk_id_also_degrades(
    stem_indexed_env: tuple[str, GraphStore],
) -> None:
    """Canonical id form stem-001:chunk:99999 is also rejected when absent from the index."""
    paper_id, graph_store = stem_indexed_env
    paper_service = get_paper_service()
    retriever = HybridRetriever(vector_store=StaticMockVectorStore.load_default())

    retrieval = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=graph_store,
    )

    fake_chunk_id = "stem-001:chunk:99999"
    llm_text = f"引用[CITE:chunk:{fake_chunk_id}]。"
    events = await collect_qa_events(
        qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
            retrieval_context=retrieval.context,
            retrieval_warning=retrieval.warning_event,
            llm=_fake_llm(llm_text),
        ),
    )

    cite = chunk_citations(events)[0]
    assert cite["chunk_id"] == fake_chunk_id
    assert cite["preview_state"] == ChunkPreviewState.HALLUCINATED_ID
