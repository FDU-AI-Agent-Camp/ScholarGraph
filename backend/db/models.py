"""ORM models for papers and pipeline run state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

DEFAULT_GRAPH_VERSION = "1"
DEFAULT_EXTRACTOR_CONFIG_HASH = ""
PAPER_OPS_OPERATION_REEXTRACT = "reextract"
PAPER_OPS_OPERATION_DELETE = "delete"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PaperRow(Base):
    """Persistent paper metadata; large blobs stay on the filesystem."""

    __tablename__ = "papers"

    paper_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    paradigm: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    pdf_path: Mapped[str] = mapped_column(String(500))
    graph_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    head_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_available: Mapped[bool] = mapped_column(Boolean, default=False)
    classification: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    graph_version: Mapped[str] = mapped_column(String(20), default=DEFAULT_GRAPH_VERSION)
    extractor_config_hash: Mapped[str] = mapped_column(
        String(64),
        default=DEFAULT_EXTRACTOR_CONFIG_HASH,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )

    pipeline_run: Mapped[PipelineRunRow | None] = relationship(
        back_populates="paper",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PipelineRunRow(Base):
    """Latest pipeline status per paper (UPSERT semantics, not an event log)."""

    __tablename__ = "pipeline_runs"

    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.paper_id", ondelete="CASCADE"),
        primary_key=True,
    )
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    percent: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(1000), default="")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failed_during: Mapped[str | None] = mapped_column(String(30), nullable=True)
    head_refine_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    classify_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    extract_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    active_rag_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_generation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_graph: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    indexing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexing_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )

    paper: Mapped[PaperRow] = relationship(back_populates="pipeline_run")


class PaperOpsClaimRow(Base):
    """Cluster-wide wipe mutex for force reextract / force delete.

    Durable row (not a long-held DB transaction): covers await I/O during abort +
    Chroma/disk purge across multiple Uvicorn workers. Stale leases are stealable
    after ``expires_at`` so a crashed worker cannot permanently 409 a paper.
    """

    __tablename__ = "paper_ops_claims"

    paper_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation: Mapped[str] = mapped_column(String(20), default=PAPER_OPS_OPERATION_REEXTRACT)
    owner_token: Mapped[str] = mapped_column(String(64))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VectorCleanupQueueRow(Base):
    """Transactional outbox for Wave-2 delayed Chroma ``delete_run`` (survives restart).

    No FK to ``papers``: force DELETE removes the paper row before Wave-2 fires; the
    tombstone must outlive that cascade so cold-boot drain can still scrub vectors.
    """

    __tablename__ = "vector_cleanup_queue"
    __table_args__ = (UniqueConstraint("paper_id", "run_id", name="uq_vector_cleanup_paper_run"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    create_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    execute_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
