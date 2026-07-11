"""LLM-assisted patrol summaries with Pydantic JSON schema (BE-4)."""

from __future__ import annotations

import logging
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.llm.client import LlmClient, get_llm_client
from backend.schemas.patrol import PatrolMode
from backend.schemas.patrol_llm import (
    ClaimEvolutionOutput,
    MethodOverlapOutput,
    PatrolSummaryOutput,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

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

METHOD_OVERLAP_SYSTEM = (
    "你是学术共同体巡检助手。根据两篇 STEM 论文的方法（Method）与数据集（Dataset）节点，"
    "用中文写一段 80–200 字的方法论宏观对比综述，并针对每一对显著重叠的方法给出结构化对比细节。"
    "只输出 JSON，字段："
    "summary（宏观对比综述）、"
    "comparison_details（数组，每个元素包含 method_pair_name、paper_a_usage、paper_b_usage、evidence_summary）。"
)

CLAIM_EVOLUTION_SYSTEM = (
    "你是学术共同体巡检助手。根据两篇论文的研究问题（ResearchQuestion）与结论（Claim/Finding），"
    "判定它们是否关注同一核心命题，以及结论之间是继承深化、矛盾冲突还是在特定条件下修正细化。"
    "只输出 JSON，字段："
    "evolution_type（枚举：inherit / contradict / refined）、"
    "problem_fit_score（0-100 整数，研究问题契合度）、"
    "comparison_summary（80-200 字中文观点对比摘要）、"
    "evidence_summary（可选，基于证据链的额外说明）。"
)

_SYSTEM_PROMPTS: dict[PatrolMode, str] = {
    PatrolMode.LENS_CLASH: LENS_CLASH_SYSTEM,
    PatrolMode.CONTRADICTION: CONTRADICTION_SYSTEM,
    PatrolMode.METHOD_OVERLAP: METHOD_OVERLAP_SYSTEM,
    PatrolMode.CLAIM_EVOLUTION: CLAIM_EVOLUTION_SYSTEM,
}


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
    system = _SYSTEM_PROMPTS.get(mode)
    if system is None:
        return None
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


async def _generate_structured_output(
    schema: type[_T],
    system: str,
    context: str,
    *,
    llm_client: LlmClient | None = None,
) -> _T | None:
    """Invoke LLM with an arbitrary Pydantic schema and validate the result."""
    if not context.strip():
        return None
    try:
        client = llm_client or get_llm_client()
        structured = client.chat.with_structured_output(schema)
        result = await structured.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=context),
            ],
        )
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)
    except ValueError:
        return None
    except Exception as exc:
        logger.warning("patrol LLM structured output failed for %s: %s", schema.__name__, exc)
        return None


async def generate_method_overlap_summary(
    context: str,
    *,
    llm_client: LlmClient | None = None,
) -> MethodOverlapOutput | None:
    """Invoke LLM with the mode-specific structured schema for method_overlap."""
    return await _generate_structured_output(
        MethodOverlapOutput,
        METHOD_OVERLAP_SYSTEM,
        context,
        llm_client=llm_client,
    )


async def generate_claim_evolution_summary(
    context: str,
    *,
    llm_client: LlmClient | None = None,
) -> ClaimEvolutionOutput | None:
    """Invoke LLM with NLI-style structured schema for claim_evolution mode."""
    if not context.strip():
        return None
    try:
        client = llm_client or get_llm_client()
        structured = client.chat.with_structured_output(ClaimEvolutionOutput)
        result = await structured.ainvoke(
            [
                SystemMessage(content=CLAIM_EVOLUTION_SYSTEM),
                HumanMessage(content=context),
            ],
        )
        if isinstance(result, ClaimEvolutionOutput):
            return result
        return ClaimEvolutionOutput.model_validate(result)
    except ValueError:
        return None
    except Exception as exc:
        logger.warning("claim evolution LLM summary failed, using template fallback: %s", exc)
        return None
