"""Alembic migration entrypoints for production and operator scripts."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from backend.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

ALEMBIC_BASELINE_REVISION = "17bad1e1a105"
ALEMBIC_HEAD_REVISION = "a8c91f2e4d10"
# Tables required by the current Alembic head (create_all may materialise these early).
_HEAD_SCHEMA_TABLES = frozenset({"papers", "pipeline_runs", "paper_ops_claims", "vector_cleanup_queue"})


def alembic_config() -> Config:
    """Build Alembic config bound to the current ``DATABASE_URL``."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def stamp_revision(revision: str) -> None:
    """Record *revision* in ``alembic_version`` without running DDL."""
    engine = create_engine(get_settings().database_url)
    inspector = inspect(engine)
    if not inspector.has_table("alembic_version"):
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )


def stamp_head_if_unversioned() -> None:
    """Align test ``create_all`` snapshots with Alembic head without Alembic CLI logging hooks."""
    if get_current_revision() is not None:
        return
    engine = create_engine(get_settings().database_url)
    inspector = inspect(engine)
    if inspector.has_table("papers"):
        stamp_revision(ALEMBIC_HEAD_REVISION)


def _head_schema_present(inspector: object) -> bool:
    table_names = set(inspector.get_table_names())  # type: ignore[attr-defined]
    return _HEAD_SCHEMA_TABLES.issubset(table_names)


def ensure_migrated() -> None:
    """Bring ``DATABASE_URL`` to Alembic head (prod upgrade or test snapshot stamp)."""
    current = get_current_revision()
    if current == ALEMBIC_HEAD_REVISION:
        return
    engine = create_engine(get_settings().database_url)
    inspector = inspect(engine)
    if current is None:
        if inspector.has_table("papers"):
            stamp_revision(ALEMBIC_HEAD_REVISION)
            return
        upgrade_head()
        return
    # create_all may already materialise head ORM tables while alembic_version lags.
    if _head_schema_present(inspector):
        stamp_revision(ALEMBIC_HEAD_REVISION)
        return
    upgrade_head()


def upgrade_head() -> None:
    """Apply all pending migrations."""
    command.upgrade(alembic_config(), "head")


def downgrade_base() -> None:
    """Revert schema to empty (pre-baseline)."""
    command.downgrade(alembic_config(), "base")


def downgrade_to(revision: str) -> None:
    """Revert schema to a specific revision."""
    command.downgrade(alembic_config(), revision)


def get_current_revision() -> str | None:
    """Return the revision stored in ``alembic_version``, if any."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def get_head_revision() -> str:
    """Return the latest revision id from the Alembic script directory."""
    script = ScriptDirectory.from_config(alembic_config())
    head = script.get_current_head()
    if head is None:
        msg = "no Alembic head revision configured"
        raise RuntimeError(msg)
    return head
