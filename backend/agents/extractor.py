"""Deterministic paper graph extractor for BE-2.

This module provides the `extract(full_text, paradigm)` service contract. The
heuristic path is intentionally conservative and schema-first; an LLM extractor
can replace the internals later as long as it returns `UnifiedPaperGraph`.
"""

from __future__ import annotations

import hashlib
import re

from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


TITLE_PREFIXES = ("title:", "标题：", "标题:")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？.!?])\s*|\n+")


def _paper_id_for_text(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"paper-{digest}"


def _extract_title(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line:
            continue
        lower_line = line.lower()
        for prefix in TITLE_PREFIXES:
            if lower_line.startswith(prefix):
                title_value = line[len(prefix) :].strip()
                if not title_value:
                    return "未命名论文"
                return re.split(r"[。！？.!?]", title_value, maxsplit=1)[0].strip()[:80]
        return line[:80]
    return "未命名论文"


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(text) if sentence.strip()]


def _first_sentence_matching(text: str, keywords: tuple[str, ...], fallback: str) -> str:
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if any(keyword.lower() in lowered for keyword in keywords):
            return sentence[:120]
    return fallback


def _extract_lens(text: str) -> str:
    known_lenses = (
        "历史制度主义",
        "公共领域",
        "消费社会",
        "结构洞",
        "差序格局",
        "女性主义",
        "后殖民",
        "制度主义",
        "discourse theory",
        "public sphere",
    )
    lowered = text.lower()
    for lens in known_lenses:
        if lens.lower() in lowered:
            return lens
    return _first_sentence_matching(text, ("理论", "视角", "lens", "framework"), "理论视角")


def _extract_object_or_data(text: str, title: str) -> str:
    known_objects = (
        "平台零工经济劳动者",
        "平台零工经济",
        "通商口岸",
        "近代中国",
        "访谈材料",
        "档案材料",
        "口述史材料",
    )
    for object_label in known_objects:
        if object_label in text:
            return object_label
    return _first_sentence_matching(text, ("访谈", "档案", "材料", "对象", "case", "data"), title)


def _sub_arguments(text: str, title: str) -> list[str]:
    candidates: list[str] = []
    markers = ("首先", "其次", "再次", "此外", "第一", "第二", "第三", "一方面", "另一方面")
    for sentence in _sentences(text):
        if any(marker in sentence for marker in markers):
            candidates.append(sentence[:90])
        if len(candidates) >= 3:
            break
    while len(candidates) < 2:
        candidates.append(f"{title} 的分论点 {len(candidates) + 1}")
    return candidates[:3]


def _build_hss_graph(full_text: str, title: str) -> UnifiedPaperGraph:
    thesis_label = _first_sentence_matching(
        full_text,
        ("本文认为", "核心论点", "主张", "argue", "thesis"),
        f"{title} 的核心论点",
    )
    lens_label = _extract_lens(full_text)
    object_label = _extract_object_or_data(full_text, title)
    context_label = _first_sentence_matching(
        full_text,
        ("既有研究", "传统观点", "忽略", "批判", "修正", "literature"),
        "既有研究或传统解释",
    )
    nodes = [
        GraphNode(id="n_thesis", label=thesis_label, type=NodeType.THESIS),
        GraphNode(id="n_lens", label=lens_label, type=NodeType.ANALYTICAL_LENS),
        GraphNode(id="n_object", label=object_label, type=NodeType.OBJECT_OR_DATA),
        GraphNode(id="n_context", label=context_label, type=NodeType.INTELLECTUAL_CONTEXT),
    ]
    edges = [
        GraphEdge(
            id="e_object_lens",
            source="n_object",
            target="n_lens",
            label="EXAMINES_THROUGH",
            type="EXAMINES_THROUGH",
        ),
        GraphEdge(
            id="e_thesis_context",
            source="n_thesis",
            target="n_context",
            label="CHALLENGES",
            type="CHALLENGES",
        ),
    ]
    for index, argument in enumerate(_sub_arguments(full_text, title), start=1):
        node_id = f"n_sub_{index}"
        nodes.append(GraphNode(id=node_id, label=argument, type=NodeType.SUB_ARGUMENT))
        edges.append(
            GraphEdge(
                id=f"e_sub_{index}",
                source=node_id,
                target="n_thesis",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            )
        )
    return UnifiedPaperGraph(
        paper_id=_paper_id_for_text(full_text),
        title=title,
        paradigm=Paradigm.HSS,
        nodes=nodes,
        edges=edges,
        summary=f"抽取出 HSS 论证图谱：核心论点、分论点、理论视角、研究对象与学术谱系。",
    )


def _build_stem_graph(full_text: str, title: str) -> UnifiedPaperGraph:
    question_label = _first_sentence_matching(full_text, ("problem", "task", "问题", "任务"), f"{title} 的研究问题")
    method_label = _first_sentence_matching(full_text, ("method", "model", "algorithm", "方法", "模型", "算法"), "主要方法")
    dataset_label = _first_sentence_matching(full_text, ("dataset", "benchmark", "数据集", "基准"), "实验数据集")
    metric_label = _first_sentence_matching(full_text, ("accuracy", "f1", "metric", "指标", "准确率"), "评测指标")
    baseline_label = _first_sentence_matching(full_text, ("baseline", "基线", "对比方法"), "对比基线")
    claim_label = _first_sentence_matching(full_text, ("claim", "improve", "outperform", "提升", "优于"), "核心实验声称")
    evidence_label = _first_sentence_matching(full_text, ("experiment", "result", "实验", "结果"), "实验结果证据")
    nodes = [
        GraphNode(id="n_question", label=question_label, type=NodeType.RESEARCH_QUESTION),
        GraphNode(id="n_method", label=method_label, type=NodeType.METHOD),
        GraphNode(id="n_dataset", label=dataset_label, type=NodeType.DATASET),
        GraphNode(id="n_metric", label=metric_label, type=NodeType.METRIC),
        GraphNode(id="n_baseline", label=baseline_label, type=NodeType.BASELINE),
        GraphNode(id="n_claim", label=claim_label, type=NodeType.CLAIM),
        GraphNode(id="n_evidence", label=evidence_label, type=NodeType.EVIDENCE),
    ]
    edges = [
        GraphEdge(id="e_method_question", source="n_method", target="n_question", label="ADDRESSES", type="ADDRESSES"),
        GraphEdge(id="e_method_dataset", source="n_method", target="n_dataset", label="EVALUATED_ON", type="EVALUATED_ON"),
        GraphEdge(id="e_claim_metric", source="n_claim", target="n_metric", label="MEASURED_BY", type="MEASURED_BY"),
        GraphEdge(id="e_claim_baseline", source="n_claim", target="n_baseline", label="COMPARES_TO", type="COMPARES_TO"),
        GraphEdge(id="e_evidence_claim", source="n_evidence", target="n_claim", label="SUPPORTS", type="SUPPORTS"),
    ]
    return UnifiedPaperGraph(
        paper_id=_paper_id_for_text(full_text),
        title=title,
        paradigm=Paradigm.STEM,
        nodes=nodes,
        edges=edges,
        summary="抽取出 STEM 实验验证图谱：问题、方法、数据集、指标、基线、声称与证据。",
    )


async def extract(full_text: str, paradigm: Paradigm) -> UnifiedPaperGraph:
    """Extract a validated `UnifiedPaperGraph` for the requested paradigm."""

    if not full_text or not full_text.strip():
        raise ValueError("full_text must be a non-empty string.")
    normalized_paradigm = Paradigm(paradigm)
    title = _extract_title(full_text)
    if normalized_paradigm == Paradigm.HSS:
        return _build_hss_graph(full_text, title)
    return _build_stem_graph(full_text, title)
