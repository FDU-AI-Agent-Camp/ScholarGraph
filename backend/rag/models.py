"""Pydantic models and protocols for V2 RAG vector indexing (Phase 1+2+4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Question-scale routing (Phase 2 — rag-qa-evaluation / rag-hybrid-retriever)
# ---------------------------------------------------------------------------


class QuestionScale(StrEnum):
    """Routing scales for hybrid RAG (aligned with ``qa_golden_set.json`` ``scale``)."""

    SUMMARY = "summary"  # 摘要 / 整体结构 — A 尺度
    DETAIL = "detail"  # 方法 / 论证关系 / 结构细节 — A+B
    VERIFICATION = "verification"  # 证据 / 材料 / 实验与指标 — B 尺度
    CROSS_PAPER = "cross_paper"  # 跨论文对比 — Patrol 域，单篇 QA 熔断


# Early V2 draft used ``skeleton`` / ``cross``; golden set uses ``summary`` / ``verification``.
# ``cross`` legacy alias maps to ``cross_paper`` for Patrol-style multi-paper questions.
QUESTION_SCALE_LEGACY_ALIASES: dict[str, str] = {
    "skeleton": QuestionScale.SUMMARY,
    "cross": QuestionScale.CROSS_PAPER,
}


def coerce_question_scale(value: str) -> QuestionScale:
    """Parse a scale string from golden JSON, API, or legacy docs."""
    normalized = QUESTION_SCALE_LEGACY_ALIASES.get(value, value)
    return QuestionScale(normalized)


class VectorEvidenceType(StrEnum):
    """Evidence classes stored in separate ChromaDB collections."""

    CHUNK = "chunk"
    ENTITY = "entity"
    RELATION = "relation"


class PaperChunk(BaseModel):
    """A searchable slice of original paper text."""

    chunk_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    chunk_index: int = Field(ge=0)
    source: str = Field(default="pymupdf", min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class PaperEntity(BaseModel):
    """A graph node converted into searchable vector evidence."""

    entity_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_span: str | None = None


class PaperRelation(BaseModel):
    """A graph edge converted into searchable vector evidence."""

    relation_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    rationale: str | None = None
    source_span: str | None = None


class RetrievedEvidence(BaseModel):
    """Common fields shared by all retrieved RAG evidence types."""

    id: str = Field(min_length=1, description="Namespaced ChromaDB id.")
    paper_id: str = Field(min_length=1)
    text: str
    distance: float | None = None


class RetrievedChunk(RetrievedEvidence):
    """A retrieved original-text chunk, ready for downstream generation."""

    evidence_type: VectorEvidenceType = VectorEvidenceType.CHUNK
    chunk_id: str = Field(min_length=1)
    section: str | None = None
    chunk_index: int = Field(ge=0)
    source: str = Field(default="pymupdf", min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    page_start: int | None = None
    page_end: int | None = None


class RetrievedEntity(RetrievedEvidence):
    """A retrieved graph entity, ready for downstream generation."""

    evidence_type: VectorEvidenceType = VectorEvidenceType.ENTITY
    entity_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    source_span: str | None = None


class RetrievedRelation(RetrievedEvidence):
    """A retrieved graph relation, ready for downstream generation."""

    evidence_type: VectorEvidenceType = VectorEvidenceType.RELATION
    relation_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    rationale: str | None = None
    source_span: str | None = None


class EmbeddingClientProtocol(Protocol):
    """Minimal embedding client contract used by VectorStore and tests."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...


# ---------------------------------------------------------------------------
# Retrieval context (Phase 2 — consumed by QA + Patrol)
# ---------------------------------------------------------------------------


class SentenceLabel(StrEnum):
    """Per-sentence entailment label for bottom-up Judge (Track B Step 1)."""

    SUPPORTED = "supported"
    HALLUCINATED = "hallucinated"
    REDUNDANT = "redundant"


class SentenceJudgment(BaseModel):
    """One sentence from the model answer with a micro-level label."""

    sentence: str = Field(
        ...,
        min_length=1,
        description="The exact substring sentence from the model answer.",
    )
    label: SentenceLabel = Field(
        ...,
        description="Evaluation label for this specific sentence.",
    )


class JudgeMicroOutput(BaseModel):
    """Step 1 LLM binding — micro sentence labels only (macro derived in code)."""

    sentence_judgments: list[SentenceJudgment] = Field(
        ...,
        min_length=1,
        description="Break down the model answer into sentences and judge them one by one.",
    )


class TrackBJudgeSchema(BaseModel):
    """Full Track B Judge output: micro sentence_judgments + macro scores (asymmetric nesting)."""

    sentence_judgments: list[SentenceJudgment] = Field(
        ...,
        min_length=1,
        description="Break down the model answer into sentences and judge them one by one.",
    )
    hallucination_detected: bool = Field(
        ...,
        description="Must be true if ANY sentence is labeled as 'hallucinated'.",
    )
    factual_consistency: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Macro score (0.0-1.0) based on the percentage of supported semantic logic.",
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        description="Detailed justification connecting the sentence judgments to the macro scores.",
    )

    @model_validator(mode="after")
    def verify_consistency(self) -> Self:
        """Reject macro/micro contradictions (e.g. hallucinated sentence but macro flag false)."""
        has_hallucinated_sentence = any(
            item.label == SentenceLabel.HALLUCINATED for item in self.sentence_judgments
        )
        if has_hallucinated_sentence and not self.hallucination_detected:
            raise ValueError(
                "Macro 'hallucination_detected' must be True if hallucinated sentences exist.",
            )
        return self


# Backward-compatible alias used across benchmark / API reports.
QAJudgeResult = TrackBJudgeSchema

# LLM structured-output binding: Step 1 micro schema only — macro fields computed in code.
JudgeSchema = JudgeMicroOutput


class RetrievalContext(BaseModel):
    """Complete retrieval result passed to QA / Patrol prompt builders.

    Members:
        nodes / edges: graph topology subgraph (A 尺度).
        entities / relations / chunks: vector recall results (B 尺度).
        scale: the resolved question scale.
    """

    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    entities: list[RetrievedEntity] = Field(default_factory=list)
    relations: list[RetrievedRelation] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    scale: QuestionScale
