"""Multi-scale QA over paper graph (BE-3 / V2 RAG Phase 2).

Exposes ``qa_stream()`` — an async generator that yields ``QaEvent``
objects for the SSE route in ``backend/api/routes/papers.py``.

V2 extensions (rag-qa-evaluation):
- Multi-type citation markers: ``[CITE:node_id]`` / ``[CITE:edge:{eid}]`` /
  ``[CITE:chunk:{cid}]`` / ``[CITE:page:{n}]``.
- Edge citation labels auto-joined from source/target node labels.
- Optional ``RetrievalContext`` for hybrid graph + vector QA prompt.
"""

import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from backend.graph.query import GraphQuery
from backend.graph.store import GraphStore
from backend.llm.client import LlmClient, get_qa_llm_client
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import PaperService, get_paper_service

if TYPE_CHECKING:
    from backend.rag.models import RetrievalContext

from backend.graph.qa_v2 import (
    build_chunk_text_cache,
    dispatch_citation,
    format_retrieval_context,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inline citation patterns — V2 supports four citation formats:
#   [CITE:node_id]        → node reference (existing V1)
#   [CITE:edge:{edge_id}] → edge / relation reference
#   [CITE:chunk:{chunk_id}] → source-text chunk reference
#   [CITE:page:{page}]     → page-number reference
# ---------------------------------------------------------------------------
_CITE_RE = re.compile(r"\[CITE:(edge:|chunk:|page:)?(\S+?)\]")
_CITE_DELIM = "[CITE:"

# Injected into the QA prompt when the user queries an MVP skeleton graph.
_MVP_PREVIEW_PREFIX = (
    "\n\n## 系统提示（SYSTEM NOTIFICATION）\n\n"
    "当前加载的是论文的 **MVP 宏观骨架图谱**：仅包含核心研究问题、主要理论视角/方法、"
    "以及核心结论等高层节点。深度论证链、实验细节与细分材料仍在后台全量解构中。"
    "请仅在宏观摘要尺度下回答问题，避免对细节证据做过度推断。"
)


def _split_incomplete_cite(buffer: str) -> tuple[str, str] | None:
    """Return ``(safe_prefix, held_suffix)`` when *buffer* ends with a partial ``[CITE:…]``."""
    cite_start = buffer.rfind(_CITE_DELIM)
    if cite_start != -1:
        tail = buffer[cite_start:]
        if _CITE_RE.search(tail) is None:
            return buffer[:cite_start], tail

    for prefix_len in range(len(_CITE_DELIM), 0, -1):
        prefix = _CITE_DELIM[:prefix_len]
        if buffer.endswith(prefix):
            return buffer[:-prefix_len], prefix

    if buffer.endswith("["):
        return buffer[:-1], "["

    return None


def _build_edge_label_cache(graph: UnifiedPaperGraph) -> dict[str, str]:
    """Build a cache mapping edge ids to human-readable auto-joined labels.

    Format: ``"{source_label} → {target_label}"`` or
    ``"{source_label} --[{relation_type}]--> {target_label}"``.
    """
    node_labels: dict[str, str] = {n.id: n.label for n in graph.nodes}
    cache: dict[str, str] = {}
    for edge in graph.edges:
        source_label = node_labels.get(edge.source, edge.source)
        target_label = node_labels.get(edge.target, edge.target)
        cache[edge.id] = f"{source_label} → {target_label}"
    return cache


# ---------------------------------------------------------------------------
# Resolve the prompts directory once at import time.
# ---------------------------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_QA_PROMPT_PATH = _PROMPTS_DIR / "qa.md"

# Fallback prompt used when qa.md is missing.
_FALLBACK_QA_PROMPT = """\
你是一个学术研究助手，正在分析一篇{paradigm}范式的学术论文。

## 知识图谱上下文
### 节点
{nodes}

### 关系
{edges}

### 相关实体
{entities}

### 相关关系描述
{relations}

### 相关原文片段
{chunks}

## 引用要求
- 引用图谱节点时使用格式 [CITE:节点ID]
- 引用图谱关系时使用格式 [CITE:edge:边ID]
- 引用原文片段时使用格式 [CITE:chunk:片段ID] 或 [CITE:page:页码]

## 回答要求
- 根据图谱上下文回答问题，引用具体来源作为依据。
- 细节/数值问题优先用原文片段回答。
- 若上下文不足，明确说明"根据已有信息无法判断"。
- 使用中文回答。

## 用户问题
{question}

## 回答
"""


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class QaEvent:
    """One SSE event emitted by ``qa_stream``.

    Attributes:
        event: SSE event type — ``message`` | ``citation`` | ``done`` | ``error``.
        data: Payload dict, serialised to JSON by the SSE route.
    """

    __slots__ = ("event", "data")

    def __init__(self, event: str, data: dict) -> None:
        self.event = event
        self.data = data

    def __repr__(self) -> str:
        return f"QaEvent({self.event!r}, {self.data!r})"


# ---------------------------------------------------------------------------
# Main entry-point (imported by BE-L for SSE wiring)
# ---------------------------------------------------------------------------


async def qa_stream(
    paper_id: str,
    question: str,
    *,
    retrieval_context: "RetrievalContext | None" = None,
    llm: LlmClient | None = None,
) -> AsyncIterator[QaEvent]:
    """Stream multi-scale QA events for the SSE endpoint.

    Usage by BE-L (in ``backend/api/routes/papers.py``)::

        async for evt in qa_stream(paper_id, body.question):
            yield f"event: {evt.event}\\ndata: {json.dumps(evt.data)}\\n\\n"

    Args:
        paper_id: Target paper.
        question: User question string.
        retrieval_context: Optional hybrid retrieval context from
            ``HybridRetriever.retrieve()`` (V2 Phase 2).  When ``None``,
            QA falls back to pure graph mode (V1 behaviour).
        llm: Optional QA Generator client. Defaults to ``get_qa_llm_client()``
            (``LLM_MODEL_QA``), decoupled from the Judge evaluator.
    """
    engine = _GraphQaEngine(llm=llm)
    async for evt in engine.stream(paper_id, question, retrieval_context=retrieval_context):
        yield evt


# ---------------------------------------------------------------------------
# Engine (class-based for testability — dependencies are injectable)
# ---------------------------------------------------------------------------


class _GraphQaEngine:
    """Orchestrates graph-load → subgraph-retrieve → prompt → LLM-stream."""

    def __init__(
        self,
        *,
        store: GraphStore | None = None,
        llm: LlmClient | None = None,
        query: GraphQuery | None = None,
        paper_service: PaperService | None = None,
    ) -> None:
        self._store = store or GraphStore()
        self._llm = llm or get_qa_llm_client()
        self._query = query or GraphQuery()
        self._paper_service = paper_service or get_paper_service()

    # ── public ───────────────────────────────────────────────────────

    async def stream(
        self,
        paper_id: str,
        question: str,
        *,
        retrieval_context: "RetrievalContext | None" = None,
    ) -> AsyncIterator[QaEvent]:
        """Yield ``QaEvent`` items for a single QA turn.

        Allows QA over an MVP skeleton graph while the full pipeline is still
        running, as long as ``preview_available`` has been marked.

        When *retrieval_context* is provided, the prompt is enriched with
        vector-retrieved entities, relations, and chunks (V2 hybrid RAG).
        """
        try:
            paper = await self._paper_service.get_paper(paper_id)
        except Exception:
            yield QaEvent(
                "error",
                {"code": "GRAPH_NOT_FOUND", "message": f"论文 {paper_id} 不存在或图谱尚未建好，请等待流水线完成。"},
            )
            yield QaEvent("done", {"answer_id": ""})
            return

        is_preview = paper.status not in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS}

        if is_preview and not paper.preview_available:
            yield QaEvent(
                "error",
                {"code": "GRAPH_NOT_FOUND", "message": f"论文 {paper_id} 的图谱尚未建好，请等待流水线完成。"},
            )
            yield QaEvent("done", {"answer_id": ""})
            return

        graph = self._store.load(paper_id)
        if graph is None:
            # Fall back to the in-memory preview graph for non-ready papers.
            graph = self._paper_service.get_preview_graph(paper_id)

        if graph is None:
            yield QaEvent(
                "error",
                {"code": "GRAPH_NOT_FOUND", "message": f"论文 {paper_id} 的图谱数据缺失。"},
            )
            yield QaEvent("done", {"answer_id": ""})
            return

        subgraph = self._query.subgraph_for_question(graph, question)
        prompt = self._build_prompt(
            graph,
            subgraph,
            question,
            is_preview=is_preview,
            retrieval_context=retrieval_context,
        )

        chunks_list = retrieval_context.chunks if retrieval_context else None

        answer_id = f"ans-{paper_id}"
        try:
            async for evt in self._stream_llm(prompt, graph, paper_id, chunks=chunks_list):
                yield evt
        except Exception as exc:
            logger.exception("qa_stream failed for paper_id=%s", paper_id)
            yield QaEvent("error", {"code": "QA_STREAM_ERROR", "message": str(exc)})
        finally:
            yield QaEvent("done", {"answer_id": answer_id})

    # ── internal ─────────────────────────────────────────────────────

    async def _stream_llm(
        self,
        prompt: str,
        graph: UnifiedPaperGraph,
        paper_id: str,
        *,
        chunks: list | None = None,
    ) -> AsyncIterator[QaEvent]:
        """Stream LLM response, splitting on [CITE:...] markers of all four types."""
        buffer = ""
        node_label_cache: dict[str, str] = {n.id: n.label for n in graph.nodes}
        edge_label_cache: dict[str, str] = _build_edge_label_cache(graph)
        chunk_text_cache: dict[str, str] = build_chunk_text_cache(chunks)

        async for chunk in self._llm.chat.astream(prompt):
            delta: str = ""
            content = getattr(chunk, "content", None)
            if isinstance(content, str):
                delta = content
            elif isinstance(content, list):
                delta = "".join(c if isinstance(c, str) else str(c) for c in content)
            else:
                delta = str(chunk) if chunk else ""

            if not delta:
                continue

            buffer += delta

            while buffer:
                match = _CITE_RE.search(buffer)
                if match:
                    text_before = buffer[: match.start()]
                    if text_before:
                        yield QaEvent("message", {"delta": text_before})

                    prefix = match.group(1) or ""
                    cite_value = match.group(2)
                    yield dispatch_citation(
                        prefix,
                        cite_value,
                        paper_id,
                        node_label_cache,
                        edge_label_cache,
                        chunk_text_cache,
                    )
                    buffer = buffer[match.end() :]
                    continue

                # Hold partial ``[CITE:…]`` markers that span chunk boundaries.
                incomplete = _split_incomplete_cite(buffer)
                if incomplete is not None:
                    safe, held = incomplete
                    if safe:
                        yield QaEvent("message", {"delta": safe})
                    buffer = held
                else:
                    yield QaEvent("message", {"delta": buffer})
                    buffer = ""

                break

        # Drain remaining buffer (process any complete trailing cites first).
        while buffer:
            match = _CITE_RE.search(buffer)
            if not match:
                if buffer.strip():
                    yield QaEvent("message", {"delta": buffer})
                break

            text_before = buffer[: match.start()]
            if text_before:
                yield QaEvent("message", {"delta": text_before})

            prefix = match.group(1) or ""
            cite_value = match.group(2)
            yield dispatch_citation(
                prefix,
                cite_value,
                paper_id,
                node_label_cache,
                edge_label_cache,
                chunk_text_cache,
            )
            buffer = buffer[match.end() :]

    def _build_prompt(
        self,
        graph: UnifiedPaperGraph,
        subgraph: dict,
        question: str,
        *,
        is_preview: bool = False,
        retrieval_context: "RetrievalContext | None" = None,
    ) -> str:
        """Format the QA prompt with graph context.

        When *retrieval_context* is provided, the template is enriched with
        additional placeholder sections for entities, relations, and chunks
        (V2 hybrid RAG).
        """
        template = self._load_prompt_template()

        nodes_desc = "\n".join(f"- [{n['id']}] {n['label']} (类型: {n['type']})" for n in subgraph.get("nodes", []))
        edges_desc = "\n".join(f"- {e['source']} --[{e['label']}]--> {e['target']}" for e in subgraph.get("edges", []))

        if not nodes_desc:
            nodes_desc = "（图谱中暂无匹配节点）"
        if not edges_desc:
            edges_desc = "（无匹配关系）"

        # Build extra sections from RetrievalContext (V2 Phase 2).
        from backend.config import get_settings

        max_context_chars = get_settings().qa_retrieval_context_max_chars if retrieval_context is not None else None
        entities_desc, relations_desc, chunks_desc = format_retrieval_context(
            retrieval_context,
            max_total_chars=max_context_chars,
        )

        prompt = template.format(
            paradigm=graph.paradigm.value,
            nodes=nodes_desc,
            edges=edges_desc,
            entities=entities_desc,
            relations=relations_desc,
            chunks=chunks_desc,
            question=question,
        )
        if is_preview:
            prompt += _MVP_PREVIEW_PREFIX
        return prompt

    @staticmethod
    def _load_prompt_template() -> str:
        """Load qa.md or return the built-in fallback."""
        if _QA_PROMPT_PATH.is_file():
            return _QA_PROMPT_PATH.read_text(encoding="utf-8")
        return _FALLBACK_QA_PROMPT
