"""Deterministic LLM stand-ins when ``LLM_MODE=mock`` (no cloud API calls)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import BaseMessage

from backend.rag.models import JudgeMicroOutput, QAJudgeResult, SentenceJudgment, SentenceLabel
from backend.rag.qa_judge_aggregate import aggregate_sentence_judgments, split_answer_sentences
from backend.rag.qa_router import detect_question_scale, preferred_node_types
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol_llm import PatrolSummaryOutput

MOCK_DISCLAIMER = "（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）"
MOCK_PATROL_PREFIX = "【Mock 巡检摘要】"
_MOCK_CHUNK_SIZE = 8
_NODE_LINE_RE = re.compile(r"- \[(?P<id>\S+)\] (?P<label>.+?) \(类型: (?P<type>\w+)\)")
_PARADIGM_RE = re.compile(r"## 当前论文范式\s*\n\s*(\w+)", re.MULTILINE)
_QUESTION_RE = re.compile(r"## 用户问题(?:\r?\n)+?(.*?)(?=\r?\n##|\Z)", re.DOTALL)


class MockChunk:
    """Minimal stand-in for a LangChain AIMessageChunk."""

    def __init__(self, content: str) -> None:
        self.content = content


class MockStructuredOutput:
    """Fake ``with_structured_output`` runnable for patrol summaries."""

    def __init__(self, schema: type[Any]) -> None:
        self._schema = schema

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> Any:
        context = _human_content(messages)
        if self._schema is PatrolSummaryOutput:
            return PatrolSummaryOutput(summary=_mock_patrol_summary(context))
        if self._schema is JudgeMicroOutput:
            return _mock_qa_judge_micro(context)
        if self._schema is QAJudgeResult:
            micro = _mock_qa_judge_micro(context)
            return aggregate_sentence_judgments(micro.sentence_judgments)
        return self._schema.model_validate({"summary": _mock_patrol_summary(context)})


class MockChat:
    """OpenAI-compatible chat surface backed by local templates."""

    def __init__(self, *, model: str) -> None:
        self.model_name = model

    async def astream(self, prompt: str) -> AsyncIterator[MockChunk]:
        text = _mock_qa_response(prompt)
        for index in range(0, len(text), _MOCK_CHUNK_SIZE):
            yield MockChunk(text[index : index + _MOCK_CHUNK_SIZE])

    def with_structured_output(self, schema: type[Any]) -> MockStructuredOutput:
        return MockStructuredOutput(schema)


def _human_content(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _mock_qa_response(prompt: str) -> str:
    question_match = _QUESTION_RE.search(prompt)
    question = question_match.group(1).strip() if question_match else "您的问题"
    paradigm = _parse_paradigm(prompt)
    scale = detect_question_scale(question, paradigm=paradigm)
    nodes = _parse_nodes_from_prompt(prompt)
    cite_target = _pick_citation_node(nodes, scale, paradigm)
    scale_label = {"summary": "摘要", "detail": "细节", "verification": "验证"}[scale]
    return (
        f"【{scale_label}尺度】根据知识图谱上下文，关于「{question}」可参考节点[CITE:{cite_target}]。{MOCK_DISCLAIMER}"
    )


def _parse_paradigm(prompt: str) -> Paradigm | None:
    match = _PARADIGM_RE.search(prompt)
    if not match:
        return None
    raw = match.group(1).strip().upper()
    if raw == Paradigm.STEM.value:
        return Paradigm.STEM
    if raw == Paradigm.HSS.value:
        return Paradigm.HSS
    return None


def _parse_nodes_from_prompt(prompt: str) -> list[tuple[str, str, str]]:
    return [
        (match.group("id"), match.group("label").strip(), match.group("type"))
        for match in _NODE_LINE_RE.finditer(prompt)
    ]


def _pick_citation_node(
    nodes: list[tuple[str, str, str]],
    scale: str,
    paradigm: Paradigm | None,
) -> str:
    if not nodes:
        return "n1"

    resolved_paradigm = paradigm or Paradigm.HSS
    preferred = preferred_node_types(scale, paradigm=resolved_paradigm)  # type: ignore[arg-type]
    for node_type in preferred:
        for node_id, _label, ntype in nodes:
            if ntype == node_type:
                return node_id
    return nodes[0][0]


def _mock_patrol_summary(context: str) -> str:
    if not context.strip():
        return f"{MOCK_PATROL_PREFIX}当前无可用上下文，已回退模板逻辑。{MOCK_DISCLAIMER}"
    return (
        f"{MOCK_PATROL_PREFIX}基于两篇论文的图谱节点差异生成摘要（未调用华为云 LLM）。"
        f"上下文摘要：{context[:120]}… {MOCK_DISCLAIMER}"
    )


def _mock_qa_judge_micro(context: str) -> JudgeMicroOutput:
    """Deterministic Step-1 sentence labels derived from gold patterns."""
    import json as _json

    payload: dict[str, Any] = {}
    fence_start = context.find("```json")
    if fence_start >= 0:
        json_start = context.find("{", fence_start)
        json_end = context.rfind("}")
        if json_start >= 0 and json_end > json_start:
            try:
                payload = _json.loads(context[json_start : json_end + 1])
            except _json.JSONDecodeError:
                payload = {}

    answer_text = str(payload.get("answer_text", ""))
    gold = payload.get("gold", {}) if isinstance(payload.get("gold"), dict) else {}

    forbidden_patterns = [str(p) for p in gold.get("forbidden_patterns", [])]
    sentences = split_answer_sentences(answer_text)
    judgments: list[SentenceJudgment] = []

    for sentence in sentences:
        sentence_lower = sentence.lower()
        if any(pattern.lower() in sentence_lower for pattern in forbidden_patterns):
            label = SentenceLabel.HALLUCINATED
        elif len(sentence.strip()) > 120:
            label = SentenceLabel.REDUNDANT
        else:
            label = SentenceLabel.SUPPORTED
        judgments.append(SentenceJudgment(sentence=sentence, label=label))

    if not judgments:
        placeholder = answer_text.strip() or "(empty answer)"
        label = SentenceLabel.HALLUCINATED if not answer_text.strip() else SentenceLabel.SUPPORTED
        judgments = [SentenceJudgment(sentence=placeholder, label=label)]

    return JudgeMicroOutput(sentence_judgments=judgments)
