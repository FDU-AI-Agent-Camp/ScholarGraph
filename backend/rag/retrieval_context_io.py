"""Serialize / deserialize ``RetrievalContext`` for offline QA replay (B7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from backend.rag.models import QuestionScale, RetrievalContext, RetrievedChunk, RetrievedEntity, RetrievedRelation

REPLAY_SCHEMA_VERSION = 1


class RetrievalContextReplayBundle(BaseModel):
    """Frozen retrieval → prompt bundle for deterministic offline replay."""

    schema_version: int = Field(default=REPLAY_SCHEMA_VERSION, ge=1)
    paper_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    retrieval_context: RetrievalContext
    expected_prompt_sha256: str = Field(min_length=64, max_length=64)
    expected_prompt: str = Field(min_length=1)


def sha256_prompt(text: str) -> str:
    """Return hex SHA-256 of UTF-8 *text* (prompt tuning / CI drift guard)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def serialize_retrieval_context(rc: RetrievalContext) -> dict:
    """Export RC to a JSON-ready dict (Pydantic ``mode='json'``)."""
    return rc.model_dump(mode="json")


def deserialize_retrieval_context(data: dict) -> RetrievalContext:
    """Restore RC from a JSON dict."""
    return RetrievalContext.model_validate(data)


def build_replay_bundle(
    *,
    paper_id: str,
    question: str,
    retrieval_context: RetrievalContext,
    expected_prompt: str,
) -> RetrievalContextReplayBundle:
    """Wrap RC + golden prompt into a versioned replay bundle."""
    return RetrievalContextReplayBundle(
        paper_id=paper_id,
        question=question,
        retrieval_context=retrieval_context,
        expected_prompt=expected_prompt,
        expected_prompt_sha256=sha256_prompt(expected_prompt),
    )


def dump_replay_bundle(bundle: RetrievalContextReplayBundle, path: Path) -> None:
    """Persist a replay bundle as indented UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_replay_bundle(path: Path) -> RetrievalContextReplayBundle:
    """Load a replay bundle from disk."""
    return RetrievalContextReplayBundle.model_validate_json(path.read_text(encoding="utf-8"))


def enrich_hss_detail_replay_vectors(rc: RetrievalContext) -> RetrievalContext:
    """Attach deterministic B-scale evidence for hss-001 detail replay fixtures."""
    return rc.model_copy(
        update={
            "entities": [
                RetrievedEntity(
                    id="hss-001:entity:n2",
                    paper_id="hss-001",
                    text="分论点：制度路径依赖",
                    entity_id="n2",
                    label="分论点：制度路径依赖",
                    node_type="SubArgument",
                ),
            ],
            "relations": [
                RetrievedRelation(
                    id="hss-001:relation:e1",
                    paper_id="hss-001",
                    text="分论点从制度路径依赖角度支撑核心论点，构成论证树的主干。",
                    relation_id="e1",
                    source_id="n2",
                    target_id="n1",
                    relation_type="SUB_ARGUMENT_OF",
                ),
            ],
            "chunks": [
                RetrievedChunk(
                    id="hss-001:chunk:12",
                    paper_id="hss-001",
                    text="制度一旦形成便会产生路径依赖，长期锁定后续演变方向，这是本文分论点的核心机制。",
                    chunk_id="hss-001:chunk:12",
                    chunk_index=12,
                    char_start=4800,
                    char_end=5100,
                    page_start=4,
                ),
            ],
        },
    )
