"""Multi-scale QA over paper graph (BE-3).

Exposes ``qa_stream()`` — an async generator that yields ``QaEvent``
objects for the SSE route in ``backend/api/routes/papers.py``.
"""

import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path

from backend.graph.query import GraphQuery
from backend.graph.store import GraphStore
from backend.llm.client import LlmClient, get_llm_client
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import PaperService, get_paper_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inline citation pattern: LLM emits [CITE:node_id] markers; the generator
# splits on them and emits discrete ``citation`` SSE events.
# ---------------------------------------------------------------------------
_CITE_RE = re.compile(r"\[CITE:(\S+?)\]")
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

## 回答要求
- 根据图谱上下文回答问题，引用具体节点作为依据。
- 引用节点时使用格式 [CITE:节点ID]。
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


async def qa_stream(paper_id: str, question: str) -> AsyncIterator[QaEvent]:
    """Stream multi-scale QA events for the SSE endpoint.

    Usage by BE-L (in ``backend/api/routes/papers.py``)::

        async for evt in qa_stream(paper_id, body.question):
            yield f"event: {evt.event}\\ndata: {json.dumps(evt.data)}\\n\\n"
    """
    engine = _GraphQaEngine()
    async for evt in engine.stream(paper_id, question):
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
        self._llm = llm or get_llm_client()
        self._query = query or GraphQuery()
        self._paper_service = paper_service or get_paper_service()

    # ── public ───────────────────────────────────────────────────────

    async def stream(
        self,
        paper_id: str,
        question: str,
    ) -> AsyncIterator[QaEvent]:
        """Yield ``QaEvent`` items for a single QA turn.

        Allows QA over an MVP skeleton graph while the full pipeline is still
        running, as long as ``preview_available`` has been marked.
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
        prompt = self._build_prompt(graph, subgraph, question, is_preview=is_preview)

        answer_id = f"ans-{paper_id}"
        try:
            async for evt in self._stream_llm(prompt, graph, paper_id):
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
    ) -> AsyncIterator[QaEvent]:
        """Stream LLM response, splitting on [CITE:...] markers."""
        buffer = ""
        node_label_cache: dict[str, str] = {n.id: n.label for n in graph.nodes}

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

                    node_id = match.group(1)
                    label = node_label_cache.get(node_id, node_id)
                    yield QaEvent(
                        "citation",
                        {"paper_id": paper_id, "node_id": node_id, "label": label},
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

        # Drain remaining buffer (process any trailing complete cites first).
        while buffer:
            match = _CITE_RE.search(buffer)
            if not match:
                if buffer.strip():
                    yield QaEvent("message", {"delta": buffer})
                break

            text_before = buffer[: match.start()]
            if text_before:
                yield QaEvent("message", {"delta": text_before})

            node_id = match.group(1)
            label = node_label_cache.get(node_id, node_id)
            yield QaEvent(
                "citation",
                {"paper_id": paper_id, "node_id": node_id, "label": label},
            )
            buffer = buffer[match.end() :]

    def _build_prompt(
        self,
        graph: UnifiedPaperGraph,
        subgraph: dict,
        question: str,
        *,
        is_preview: bool = False,
    ) -> str:
        """Format the QA prompt with graph context."""
        template = self._load_prompt_template()

        nodes_desc = "\n".join(f"- [{n['id']}] {n['label']} (类型: {n['type']})" for n in subgraph.get("nodes", []))
        edges_desc = "\n".join(f"- {e['source']} --[{e['label']}]--> {e['target']}" for e in subgraph.get("edges", []))

        if not nodes_desc:
            nodes_desc = "（图谱中暂无匹配节点）"
        if not edges_desc:
            edges_desc = "（无匹配关系）"

        prompt = template.format(
            paradigm=graph.paradigm.value,
            nodes=nodes_desc,
            edges=edges_desc,
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
