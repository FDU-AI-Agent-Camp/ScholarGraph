"""Chunked two-phase extraction for papers longer than ``EXTRACT_MAX_INPUT_CHARS``."""

from __future__ import annotations

import asyncio
import logging

from backend.agents.extract_edges import build_edges_with_llm
from backend.agents.extract_nodes import extract_nodes_with_llm
from backend.config import Settings, get_settings
from backend.graph.head_store import HeadStore
from backend.graph.merge_graphs import merge_graphs
from backend.graph.semantic_clustering import semantic_cluster_and_merge
from backend.ingest.chunking import TextChunk, chunk_text
from backend.llm.client import LlmClient, get_llm_client
from backend.llm.rate_limiter import get_extract_rate_limiter
from backend.schemas.extract_phase import ExtractedEdgeList, ExtractedGraph, ExtractedNodeList
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)


_DEFAULT_CHUNK_CONCURRENCY = 2


def _resolve_head_context(paper_id: str) -> str | None:
    """Load refined head text from HeadStore if available."""
    record = HeadStore().load(paper_id)
    if record is None:
        return None
    head = record.merged
    parts = [head.title.strip(), head.abstract.strip(), head.intro.strip()]
    merged = "\n\n".join(part for part in parts if part)
    return merged or None


def _prefix_node_ids(node_list: ExtractedNodeList, chunk_index: int) -> ExtractedNodeList:
    """Scope node ids with their chunk index to avoid cross-chunk collisions."""
    prefix = f"c{chunk_index}_"
    updated = []
    for node in node_list.nodes:
        updated.append(node.model_copy(update={"id": f"{prefix}{node.id}"}))
    return node_list.model_copy(update={"nodes": updated})


def _anchor_text(head_context: str | None, chunk_text_value: str) -> str:
    """Compose the anchored input passed to the LLM for a single chunk."""
    parts: list[str] = []
    if head_context and head_context.strip():
        parts.append(head_context.strip())
    parts.append(chunk_text_value)
    return "\n\n".join(parts)


def _effective_max_chunk_chars(head_context: str | None, max_input_chars: int, requested_max: int) -> int:
    """Make sure head_context + chunk fits into the model input budget."""
    head_len = len(head_context) if head_context else 0
    # Leave a small safety margin for JSON wrappers and prompt overhead.
    available = max_input_chars - head_len - 500
    if available < 1000:
        logger.warning(
            "head_context_very_long",
            extra={"head_context_length": head_len, "max_input_chars": max_input_chars},
        )
        available = max_input_chars - 500
    return min(requested_max, max(available, 1000))


async def extract_chunked(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str | None = None,
    head_context: str | None = None,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
) -> ExtractedGraph:
    """Extract a graph from a long paper by anchored chunking and merging.

    The algorithm:
    1. Split ``full_text`` into semantic chunks (section-aware + sliding window).
    2. Extract nodes from each chunk in parallel, scoping ids with chunk prefix.
    3. Merge all nodes globally (union-find on normalized label + type).
    4. Extract edges for each chunk in parallel, passing the global node directory
       and applying paradigm × chapter dynamic masking when it grows large.
    5. Merge edges and return a single ``ExtractedGraph``.
    """
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    resolved_head = head_context or _resolve_head_context(paper_id)
    max_chunk_chars = _effective_max_chunk_chars(
        resolved_head,
        cfg.extract_max_input_chars,
        cfg.extract_chunk_max_chars,
    )

    chunks = chunk_text(
        full_text,
        paradigm,
        max_chunk_chars=max_chunk_chars,
        overlap_ratio=cfg.extract_chunk_overlap_ratio,
    )
    if not chunks:
        raise ValueError("Chunking produced no usable text chunks.")

    if len(chunks) > cfg.extract_chunk_max_chunks:
        logger.warning(
            "chunk_count_exceeds_safety_limit",
            extra={
                "paper_id": paper_id,
                "chunk_count": len(chunks),
                "max_chunks": cfg.extract_chunk_max_chunks,
            },
        )
        chunks = chunks[: cfg.extract_chunk_max_chunks]

    logger.info(
        "chunked_extraction_start",
        extra={
            "paper_id": paper_id,
            "paradigm": paradigm.value,
            "chunk_count": len(chunks),
            "max_chunk_chars": max_chunk_chars,
        },
    )

    rate_limiter = get_extract_rate_limiter()
    semaphore = asyncio.Semaphore(cfg.extract_chunk_concurrency or _DEFAULT_CHUNK_CONCURRENCY)
    chunk_warnings: list[str] = []
    retry_attempts = max(1, cfg.extract_chunk_retry_attempts)
    retry_delay = cfg.extract_chunk_retry_delay_s

    async def _nodes_for_chunk(chunk: TextChunk) -> ExtractedNodeList | None:
        prompt = _anchor_text(resolved_head, chunk.text)
        await rate_limiter.acquire(tokens=1, chars=len(prompt))
        async with semaphore:
            for attempt in range(retry_attempts):
                try:
                    node_list = await extract_nodes_with_llm(
                        prompt,
                        paradigm,
                        paper_id=paper_id,
                        title=title,
                        head_context=resolved_head,
                        settings=cfg,
                        llm_client=client,
                    )
                    if not node_list.nodes:
                        logger.warning(
                            "chunked_node_extraction_empty",
                            extra={"paper_id": paper_id, "chunk_index": chunk.index, "chunk_title": chunk.title},
                        )
                        return None
                    return _prefix_node_ids(node_list, chunk.index)
                except Exception as exc:
                    if attempt < retry_attempts - 1:
                        logger.warning(
                            "chunked_node_extraction_attempt_failed",
                            extra={
                                "paper_id": paper_id,
                                "chunk_index": chunk.index,
                                "attempt": attempt + 1,
                                "error": type(exc).__name__,
                            },
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    warning = f"chunk_{chunk.index}_node_extraction_failed:{type(exc).__name__}"
                    chunk_warnings.append(warning)
                    logger.warning(
                        "chunked_node_extraction_failed",
                        extra={
                            "paper_id": paper_id,
                            "chunk_index": chunk.index,
                            "chunk_title": chunk.title,
                            "error": type(exc).__name__,
                        },
                    )
                    return None
            return None

    per_chunk_nodes = [n for n in await asyncio.gather(*(_nodes_for_chunk(chunk) for chunk in chunks)) if n is not None]
    if not per_chunk_nodes:
        raise ValueError("All chunks produced empty node lists.")

    from backend.graph.merge_graphs import merge_node_lists

    global_nodes, _ = merge_node_lists(per_chunk_nodes, prefixed=True)

    async def _edges_for_chunk(chunk: TextChunk) -> ExtractedEdgeList | None:
        prompt = _anchor_text(resolved_head, chunk.text)
        await rate_limiter.acquire(tokens=1, chars=len(prompt))
        async with semaphore:
            if not global_nodes.nodes:
                return None
            for attempt in range(retry_attempts):
                try:
                    return await build_edges_with_llm(
                        global_nodes,
                        prompt,
                        paper_id=paper_id,
                        title=title,
                        head_context=resolved_head,
                        chunk_title=chunk.title,
                        settings=cfg,
                        llm_client=client,
                    )
                except Exception as exc:
                    if attempt < retry_attempts - 1:
                        logger.warning(
                            "chunked_edge_extraction_attempt_failed",
                            extra={
                                "paper_id": paper_id,
                                "chunk_index": chunk.index,
                                "attempt": attempt + 1,
                                "error": type(exc).__name__,
                            },
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    warning = f"chunk_{chunk.index}_edge_extraction_failed:{type(exc).__name__}"
                    chunk_warnings.append(warning)
                    logger.warning(
                        "chunked_edge_extraction_failed",
                        extra={
                            "paper_id": paper_id,
                            "chunk_index": chunk.index,
                            "chunk_title": chunk.title,
                            "error": type(exc).__name__,
                        },
                    )
                    return None
            return None

    per_chunk_edges = [e for e in await asyncio.gather(*(_edges_for_chunk(chunk) for chunk in chunks)) if e is not None]

    summary = f"Chunked two-phase extraction ({paradigm.value}): {len(chunks)} chunks, {len(global_nodes.nodes)} nodes."

    result = merge_graphs(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        node_lists=per_chunk_nodes,
        edge_lists=per_chunk_edges,
        summary=summary,
        node_ids_prefixed=True,
        extra_warnings=chunk_warnings,
        prune=True,
    )

    if cfg.semantic_clustering_enabled:
        result = await semantic_cluster_and_merge(result, cfg)

    logger.info(
        "chunked_extraction_success",
        extra={
            "paper_id": paper_id,
            "paradigm": paradigm.value,
            "chunk_count": len(chunks),
            "node_count": len(result.nodes),
            "edge_count": len(result.edges),
        },
    )
    return result
