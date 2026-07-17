# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Deterministic LLM stand-ins when ``LLM_MODE=mock`` (no cloud API calls)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import BaseMessage

from backend.rag.models import JudgeMicroOutput, QAJudgeResult, QuestionScale, SentenceJudgment, SentenceLabel
from backend.rag.qa_judge_aggregate import aggregate_sentence_judgments, split_answer_sentences
from backend.rag.qa_router import detect_question_scale, preferred_node_types
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol_llm import PatrolSummaryOutput

MOCK_DISCLAIMER = "（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）"
MOCK_PATROL_PREFIX = "【Mock 巡检摘要】"
_MOCK_CHUNK_SIZE = 8
_NODE_LINE_RE = re.compile(r"- \[(?P<id>\S+)\] (?P<label>.+?) \(类型: (?P<type>\w+)\)")
_CHUNK_LINE_RE = re.compile(r"- \[(?P<chunk_id>[^\]]+)\](?: \[[^\]]+\])? (?P<text>.+)")
_LEGACY_CHUNK_ID_RE = re.compile(r"^(?P<paper>[\w-]+)_chunk_(?P<index>\d+)$")
_BRACKETED_CHUNK_ID_RE = re.compile(r"\[(?P<id>(?:[\w-]+:chunk:\d+|[\w-]+_chunk_\d+))\]")
_CITE_CHUNK_IN_PROMPT_RE = re.compile(r"\[CITE:chunk:(?P<id>[^\]]+)\]")
_VECTOR_BLOCK_ID_RE = re.compile(
    r"【向量块\s*\d+】\s*ID:\s*(?P<chunk_id>[\w-]+(?:_chunk_\d+|[\w-]+:chunk:\d+))",
)
_EDGE_TYPE_RE = re.compile(r"--\[(?P<type>[^\]]+)\]-->")
_STEM_EVIDENCE_TOKEN_RE = re.compile(
    r"78\.5%|0\.001|\b256\b|\bAdam\b|ResNet-50|ImageNet|ResNet-Light",
    re.IGNORECASE,
)
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
    excerpt_clause = _format_chunk_excerpt_clause(prompt, scale, paradigm)
    evidence_clause = _format_evidence_clause(prompt, paradigm)
    body = f"【{scale_label}尺度】{evidence_clause}关于「{question}」参见节点[CITE:{cite_target}]{excerpt_clause}。"
    if _should_inject_chunk_citations(scale, paradigm):
        chunk_ids = _extract_authoritative_chunk_ids(prompt)
        body = _append_chunk_citation_anchors(body, chunk_ids)
    return f"{body}{MOCK_DISCLAIMER}"


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


def _parse_edge_types_from_prompt(prompt: str) -> list[str]:
    relations_section = _extract_prompt_section(prompt, "关系")
    if not relations_section:
        return []
    return [match.group("type").strip() for match in _EDGE_TYPE_RE.finditer(relations_section)]


def _collect_evidence_keywords(prompt: str, paradigm: Paradigm | None) -> list[str]:
    """Compact gold-aligned tokens for mock benchmark guardrails (patterns + pseudo-datasets)."""
    seen: set[str] = set()
    keywords: list[str] = []

    def _add(token: str) -> None:
        text = token.strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        keywords.append(text)

    question_match = _QUESTION_RE.search(prompt)
    question = question_match.group(1).strip().lower() if question_match else ""

    for _node_id, label, _node_type in _parse_nodes_from_prompt(prompt):
        if (
            paradigm == Paradigm.STEM
            and "resnet-50" in label.lower()
            and not any(token in question for token in ("baseline", "resnet-50", "相比"))
        ):
            continue
        _add(label)
        if "：" in label:
            _add(label.split("：", 1)[1])

    for edge_type in _parse_edge_types_from_prompt(prompt):
        _add(edge_type)

    if paradigm == Paradigm.HSS:
        _add("HSS")
        _add("人文社科")
        _add("核心论点")
        _add("分论点")
        _add("支撑")
        _add("制度")
    elif paradigm == Paradigm.STEM:
        _add("ImageNet")

    chunks = _parse_chunks_from_prompt(prompt)
    for _chunk_id, chunk_text in chunks[:1]:
        for match in _STEM_EVIDENCE_TOKEN_RE.finditer(chunk_text):
            _add(match.group(0))

    if paradigm == Paradigm.STEM and any(token in question for token in ("baseline", "resnet-50", "相比")):
        for _chunk_id, chunk_text in chunks:
            if "ResNet-50" in chunk_text:
                _add("ResNet-50")

    return keywords


def _format_evidence_clause(prompt: str, paradigm: Paradigm | None) -> str:
    keywords = _collect_evidence_keywords(prompt, paradigm)
    if not keywords:
        return "根据知识图谱上下文，"
    return f"要点：{'、'.join(keywords[:10])}。"


def _normalize_chunk_id(raw: str) -> str:
    """Map legacy ``paper_chunk_N`` IDs to canonical ``paper:chunk:N`` form."""
    text = raw.strip()
    if not text:
        return ""
    legacy = _LEGACY_CHUNK_ID_RE.match(text)
    if legacy:
        return f"{legacy.group('paper')}:chunk:{legacy.group('index')}"
    return text


def _parse_chunks_from_prompt(prompt: str) -> list[tuple[str, str]]:
    chunks_section = _extract_prompt_section(prompt, "相关原文片段")
    if not chunks_section:
        return []
    parsed: list[tuple[str, str]] = []
    for match in _CHUNK_LINE_RE.finditer(chunks_section):
        chunk_id = _normalize_chunk_id(match.group("chunk_id"))
        if not chunk_id:
            continue
        parsed.append((chunk_id, match.group("text").strip()))
    return parsed


def _extract_authoritative_chunk_ids(prompt: str) -> list[str]:
    """Collect deduplicated chunk IDs from the retrieval-context section (and prompt fallbacks)."""
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(raw: str) -> None:
        normalized = _normalize_chunk_id(raw)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        ordered.append(normalized)

    for chunk_id, _ in _parse_chunks_from_prompt(prompt):
        _add(chunk_id)

    chunks_section = _extract_prompt_section(prompt, "相关原文片段")
    scan_targets = [chunks_section] if chunks_section else [prompt]
    for target in scan_targets:
        for match in _BRACKETED_CHUNK_ID_RE.finditer(target):
            _add(match.group("id"))
        for match in _CITE_CHUNK_IN_PROMPT_RE.finditer(target):
            _add(match.group("id"))
        for match in _VECTOR_BLOCK_ID_RE.finditer(target):
            _add(match.group("chunk_id"))

    return ordered


def _should_inject_chunk_citations(scale: QuestionScale, paradigm: Paradigm | None) -> bool:
    """STEM detail prompts carry vector chunks; mock answers must cite them for chunk_recall gates."""
    return paradigm == Paradigm.STEM and scale == QuestionScale.DETAIL


def _append_chunk_citation_anchors(text: str, chunk_ids: list[str]) -> str:
    if not chunk_ids:
        return text
    markers = "".join(f" [CITE:chunk:{chunk_id}]" for chunk_id in chunk_ids)
    return f"{text.rstrip()}{markers}"


def _format_chunk_excerpt_clause(prompt: str, scale: QuestionScale, paradigm: Paradigm | None) -> str:
    if not _should_inject_chunk_citations(scale, paradigm):
        return ""
    chunks = _parse_chunks_from_prompt(prompt)
    if not chunks:
        return ""
    _primary_id, primary_text = chunks[0]
    excerpt = primary_text[:220].strip()
    return f" 依据原文「{excerpt}」"


def _extract_prompt_section(prompt: str, heading: str) -> str:
    marker = f"### {heading}"
    start = prompt.find(marker)
    if start < 0:
        return ""
    start = prompt.find("\n", start)
    if start < 0:
        return ""
    rest = prompt[start + 1 :]
    end = rest.find("\n### ")
    if end < 0:
        end = rest.find("\n## ")
    return rest[:end] if end >= 0 else rest


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
