"""LLM-assisted patrol summaries with Pydantic JSON schema (BE-4)."""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm.client import LlmClient, get_llm_client
from backend.schemas.patrol import PatrolMode
from backend.schemas.patrol_llm import PatrolSummaryOutput

logger = logging.getLogger(__name__)

LENS_CLASH_SYSTEM = (
    "你是学术共同体巡检助手。根据两篇论文的分析视角（Analytical Lens）标签，"
    "用中文写一段 80–200 字的 Lens Clash 洞察摘要，说明理论框架是否存在潜在学派冲突。"
    "只输出 JSON，字段 summary。"
)

CONTRADICTION_SYSTEM = (
    "你是学术共同体巡检助手。根据两篇论文图谱中的核心论点（Thesis）与分论点（SubArgument），"
    "用中文写一段 80–200 字的 Contradiction 洞察摘要，说明核心论证是否存在张力或潜在矛盾。"
    "只输出 JSON，字段 summary。"
)


async def generate_patrol_summary(
    mode: PatrolMode,
    context: str,
    *,
    llm_client: LlmClient | None = None,
) -> str | None:
    """
    Invoke LLM with structured JSON schema; return None to signal caller should use template fallback.

    API keys are read from Settings via LlmClient — never hardcoded here.
    """
    if not context.strip():
        return None
    system = LENS_CLASH_SYSTEM if mode == PatrolMode.LENS_CLASH else CONTRADICTION_SYSTEM
    try:
        client = llm_client or get_llm_client()
        structured = client.chat.with_structured_output(PatrolSummaryOutput)
        result = await structured.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=context),
            ],
        )
        if isinstance(result, PatrolSummaryOutput):
            return result.summary.strip()
        return PatrolSummaryOutput.model_validate(result).summary.strip()
    except ValueError:
        return None
    except Exception as exc:
        logger.warning("patrol LLM summary failed, using template fallback: %s", exc)
        return None
