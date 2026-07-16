"""File-backed mock VectorStore for CI / LLM_MODE=mock benchmark runs (no Chroma)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import cast

from backend.rag.models import RetrievedChunk, RetrievedEntity, RetrievedRelation
from backend.rag.protocols import VectorStoreProtocol

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FIXTURE_PATH = _REPO_ROOT / "data" / "mock_vector_store.json"
_TOKEN_RE = re.compile(r"[a-zA-Z0-9][\w.-]*")


class StaticMockVectorStore:
    """用于测试与 Benchmark 的静态 Mock 向量数据库桩。"""

    def __init__(self, chunks_by_paper: dict[str, list[RetrievedChunk]]) -> None:
        self._chunks_by_paper = chunks_by_paper
        self._bind_chunk_text_lru()

    def _bind_chunk_text_lru(self) -> None:
        @lru_cache(maxsize=512)
        def _get_chunk_text_cached(paper_id: str, chunk_id: str) -> str:
            text = self._fetch_chunk_text(paper_id, chunk_id)
            return text if text else ""

        self._get_chunk_text_cached = _get_chunk_text_cached

    def clear_chunk_text_lru(self) -> None:
        self._get_chunk_text_cached.cache_clear()

    def _fetch_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        for chunk in self._chunks_by_paper.get(paper_id, []):
            if chunk.chunk_id == chunk_id:
                return chunk.text
        return None

    @classmethod
    def load(cls, path: Path = _DEFAULT_FIXTURE_PATH) -> StaticMockVectorStore:
        payload = json.loads(path.read_text(encoding="utf-8"))
        chunks_by_paper: dict[str, list[RetrievedChunk]] = {}
        papers = payload.get("papers", {})
        if not isinstance(papers, dict):
            return cls(chunks_by_paper)

        for paper_id, paper_payload in papers.items():
            raw_chunks = paper_payload.get("chunks", []) if isinstance(paper_payload, dict) else []
            parsed: list[RetrievedChunk] = []
            for index, raw in enumerate(raw_chunks):
                if not isinstance(raw, dict):
                    continue
                chunk_id = str(raw.get("chunk_id", "")).strip()
                text = str(raw.get("text", "")).strip()
                if not chunk_id or not text:
                    continue
                chunk_index = int(raw.get("chunk_index", index))
                char_end = len(text)
                parsed.append(
                    RetrievedChunk(
                        id=f"mock:{paper_id}:{chunk_id}",
                        paper_id=str(paper_id),
                        text=text,
                        chunk_id=chunk_id,
                        chunk_index=chunk_index,
                        char_start=0,
                        char_end=char_end,
                        section=raw.get("section"),
                        page_start=raw.get("page_start"),
                        page_end=raw.get("page_end"),
                        source="mock_vector_store",
                    ),
                )
            if parsed:
                chunks_by_paper[str(paper_id)] = parsed
        return cls(chunks_by_paper)

    @classmethod
    def load_default(cls) -> StaticMockVectorStore:
        return cls.load(_DEFAULT_FIXTURE_PATH)

    def chunk_count(self) -> int:
        return sum(len(chunks) for chunks in self._chunks_by_paper.values())

    async def exists(self, paper_id: str) -> bool:
        return paper_id in self._chunks_by_paper

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedEntity]:
        """兼容 ``VectorStoreProtocol``；mock 路径不召回 entity 向量。"""
        _ = query_embedding
        return self._get_mock_entities(paper_id, query_text, top_k)

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedRelation]:
        """兼容 ``VectorStoreProtocol``；mock 路径不召回 relation 向量。"""
        _ = query_embedding
        return self._get_mock_relations(paper_id, query_text, top_k)

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        """兼容 ``VectorStoreProtocol``；按 fixture 关键词启发式召回 chunk。"""
        _ = query_embedding
        return self._get_mock_chunks(paper_id, query_text, top_k)

    def _get_mock_entities(self, paper_id: str, query_text: str, top_k: int | None) -> list[RetrievedEntity]:
        _ = (paper_id, query_text, top_k)
        return []

    def _get_mock_relations(self, paper_id: str, query_text: str, top_k: int | None) -> list[RetrievedRelation]:
        _ = (paper_id, query_text, top_k)
        return []

    def _get_mock_chunks(
        self,
        paper_id: str,
        query_text: str,
        top_k: int | None,
    ) -> list[RetrievedChunk]:
        chunks = list(self._chunks_by_paper.get(paper_id, []))
        if not chunks:
            return []

        ranked = sorted(
            chunks,
            key=lambda chunk: _score_chunk(query_text, chunk.text),
            reverse=True,
        )
        limit = top_k if top_k is not None and top_k > 0 else len(ranked)
        return ranked[:limit]

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        """Return fixture chunk text by logical id (L2 citation preview lookup)."""
        cached = self._get_chunk_text_cached(paper_id, chunk_id)
        return cached if cached else None


_inspect_mock_compliance: VectorStoreProtocol = cast(StaticMockVectorStore, None)


def _score_chunk(query_text: str, chunk_text: str) -> int:
    query_tokens = {token.lower() for token in _TOKEN_RE.findall(query_text) if len(token) >= 2}
    if not query_tokens:
        return 0
    haystack = chunk_text.lower()
    return sum(1 for token in query_tokens if token in haystack)
