"""Stage 2 edge extraction for two-phase graph extraction (v2)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import Settings, get_settings
from backend.llm.client import LlmClient, get_llm_client
from backend.llm.structured_output import ainvoke_structured
from backend.schemas.extract_phase import ExtractedEdgeList, ExtractedNodeList
from backend.schemas.graph import HSS_NODE_TYPES, STEM_NODE_TYPES
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_EDGE_PROMPT_FILES = {
    Paradigm.HSS: PROMPTS_DIR / "extract_edges_hss.md",
    Paradigm.STEM: PROMPTS_DIR / "extract_edges_stem.md",
}


def _load_base_prompt() -> str:
    base_path = PROMPTS_DIR / "extract_base.md"
    if base_path.is_file():
        return base_path.read_text(encoding="utf-8")
    return ""


def load_edge_prompt(paradigm: Paradigm) -> str:
    """Load base + paradigm-specific edge extraction prompt."""
    specific_path = _EDGE_PROMPT_FILES[paradigm]
    specific = ""
    if specific_path.is_file():
        specific = specific_path.read_text(encoding="utf-8")
    parts = [part for part in (_load_base_prompt(), specific) if part.strip()]
    return "\n\n".join(parts)


def _format_nodes_for_prompt(nodes: ExtractedNodeList) -> str:
    """Render available nodes as JSON for the edge extraction prompt."""
    simplified = [
        {
            "id": node.id,
            "label": node.label,
            "type": node.type,
        }
        for node in nodes.nodes
    ]
    return json.dumps(simplified, ensure_ascii=False, indent=2)


# Hard-coded masks by paradigm × chapter keyword.
# When the global node directory exceeds the attention threshold, only node types
# relevant to the current chunk are exposed to the edge-extraction LLM.
_EDGE_MASKS: dict[tuple[Paradigm, str], set[str]] = {
    (Paradigm.STEM, "experiments"): {
        t.value for t in STEM_NODE_TYPES if t.value != "ResearchQuestion"
    },
    (Paradigm.STEM, "results"): {
        t.value for t in STEM_NODE_TYPES if t.value != "ResearchQuestion"
    },
    (Paradigm.STEM, "methods"): {
        t.value for t in STEM_NODE_TYPES if t.value not in {"ResearchQuestion", "Baseline", "Claim"}
    },
    (Paradigm.HSS, "theoretical framework"): {
        t.value for t in HSS_NODE_TYPES if t.value != "ObjectOrData"
    },
    (Paradigm.HSS, "analysis"): {
        t.value for t in HSS_NODE_TYPES if t.value not in {"IntellectualContext"}
    },
}

_DEFAULT_MASK_NODE_THRESHOLD = 80


def _chapter_keyword(chunk_title: str | None) -> str | None:
    """Return a normalized chapter keyword for masking lookup."""
    if not chunk_title:
        return None
    lowered = chunk_title.lower()
    for (_paradigm, keyword) in _EDGE_MASKS:
        if keyword in lowered:
            return keyword
    return None


def _filter_nodes_for_chunk(
    nodes: ExtractedNodeList,
    chunk_title: str | None,
    threshold: int = _DEFAULT_MASK_NODE_THRESHOLD,
) -> ExtractedNodeList:
    """Return a masked view of ``nodes`` when the directory is too large.

    The mask is keyed by paradigm and chunk chapter title. If no mask applies
    or the directory is below the threshold, ``nodes`` is returned unchanged.
    """
    if len(nodes.nodes) <= threshold:
        return nodes

    keyword = _chapter_keyword(chunk_title)
    if keyword is None:
        return nodes

    allowed = _EDGE_MASKS.get((nodes.paradigm, keyword))
    if not allowed:
        return nodes

    filtered = [node for node in nodes.nodes if node.type in allowed]
    return nodes.model_copy(update={"nodes": filtered})


_DEFAULT_MAX_EDGES_PER_CHUNK = 25


def _anchor_prompt(nodes_json: str, max_edges: int = _DEFAULT_MAX_EDGES_PER_CHUNK) -> str:
    """Build the strict node-directory anchor appended to the system prompt."""
    return (
        "\n\n## 全局实体通讯录\n\n"
        "你现在的任务是为当前文本块构建知识图谱的关系边。\n"
        "以下是系统已确认存在的合法节点集合（ID、标签、类型）：\n\n"
        f"```json\n{nodes_json}\n```\n\n"
        "## 绝对禁令\n\n"
        "- 你构建的每一条边，其 source 和 target 的 ID 必须且只能从上述通讯录中严格复制！\n"
        "- 绝不允许创造新的 ID！\n"
        "- 绝不允许修改已有 ID 的格式或内容！\n"
        "- 如果文本中提到了通讯录之外的新概念，请忽略它，只建立通讯录中已有节点间的关系。\n"
        "- 任何违反上述禁令的输出都会被视为非法并被丢弃。\n\n"
        "## 输出长度控制\n\n"
        f"- 当前块只需输出最多 **{max_edges} 条**最重要的关系边。\n"
        "- 优先输出明确、高质量的关系；不要为了凑数生成弱关系。\n"
        "- 每条边的 `source_span` 尽量简短（≤100 字符），如果证据太长可省略。\n"
        "- 确保返回的 JSON 完整、格式正确，不要截断。"
    )


def _build_user_payload(
    nodes: ExtractedNodeList,
    full_text: str,
    paper_id: str,
    title: str | None,
    head_context: str | None,
    max_chars: int,
) -> str:
    """Build the JSON user payload for edge extraction."""
    if max_chars > 0 and len(full_text) > max_chars:
        text = full_text[:max_chars]
        truncated = True
    else:
        text = full_text
        truncated = False

    payload: dict[str, object] = {
        "paper_id": paper_id,
        "paradigm": nodes.paradigm.value,
        "title": title or "",
        "full_text": text,
        "truncated": truncated,
        "available_nodes": [{"id": node.id, "label": node.label, "type": node.type} for node in nodes.nodes],
    }
    if head_context and head_context.strip():
        payload["document_head"] = head_context.strip()
    return json.dumps(payload, ensure_ascii=False)


async def build_edges_with_llm(
    nodes: ExtractedNodeList,
    full_text: str,
    *,
    paper_id: str,
    title: str | None = None,
    head_context: str | None = None,
    chunk_title: str | None = None,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
    previous_error: str | None = None,
) -> ExtractedEdgeList:
    """Build edges from extracted nodes via structured LLM call (Stage 2).

    Args:
        nodes: Validated node list from Stage 1.
        full_text: Paper full text or current chunk text.
        paper_id: Paper identifier.
        title: Optional paper title.
        head_context: Optional refined document head.
        chunk_title: Optional chapter title of the current chunk; used for
            dynamic node masking when the global node directory is large.
        settings: Optional settings override.
        llm_client: Optional LLM client override (for tests).
        previous_error: When set, the prompt asks the LLM to fix this error.

    Returns:
        Validated ExtractedEdgeList.
    """
    cfg = settings or get_settings()
    client = llm_client or get_llm_client()
    cfg.require_llm_key()

    masked_nodes = _filter_nodes_for_chunk(nodes, chunk_title)
    nodes_json = _format_nodes_for_prompt(masked_nodes)

    system_prompt = load_edge_prompt(nodes.paradigm)
    system_prompt = system_prompt.replace("{nodes_json}", nodes_json)
    system_prompt += _anchor_prompt(nodes_json)
    if previous_error:
        system_prompt += (
            f"\n\n## Previous Error to Fix\n\n{previous_error}\n\nPlease fix the above error when building edges."
        )

    user_content = _build_user_payload(
        nodes=masked_nodes,
        full_text=full_text,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
        max_chars=cfg.extract_max_input_chars,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    started_at = time.perf_counter()
    try:
        result = await ainvoke_structured(
            client,
            ExtractedEdgeList,
            messages,
            context={"warnings": []},
        )
    except Exception as exc:
        logger.warning(
            "build_edges_failed",
            extra={"paper_id": paper_id, "paradigm": nodes.paradigm.value, "error": str(exc)},
        )
        raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "build_edges_success",
        extra={
            "paper_id": paper_id,
            "paradigm": nodes.paradigm.value,
            "edge_count": len(result.edges),
            "elapsed_ms": elapsed_ms,
        },
    )
    return result
