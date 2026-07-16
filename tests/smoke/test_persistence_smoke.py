"""Smoke tests for persistence-core scaffolding."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from backend.config import Settings
from backend.db import models as db_models
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.smoke
def test_smoke_persistence_tables_declared() -> None:
    assert db_models.PaperRow.__tablename__ == "papers"
    assert db_models.PipelineRunRow.__tablename__ == "pipeline_runs"


@pytest.mark.smoke
def test_smoke_repository_public_methods_exist() -> None:
    paper_methods = {name for name, _ in inspect.getmembers(PaperRepository, predicate=inspect.isfunction)}
    assert {"create", "get", "list", "update_paths", "is_empty"}.issubset(paper_methods)

    pipeline_methods = {name for name, _ in inspect.getmembers(PipelineRepository, predicate=inspect.isfunction)}
    assert {"save_status", "get_latest", "record_warnings"}.issubset(pipeline_methods)


@pytest.mark.smoke
def test_smoke_env_example_has_seed_demo_papers_flag() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "SEED_DEMO_PAPERS=false" in text


@pytest.mark.smoke
def test_smoke_settings_default_seed_demo_papers_false() -> None:
    settings = Settings(_env_file=None)
    assert settings.seed_demo_papers is False
    assert "sqlite" in settings.database_url


@pytest.mark.smoke
def test_smoke_alembic_head_revision_matches_code_constant() -> None:
    from backend.db.migrations import ALEMBIC_HEAD_REVISION, get_head_revision

    assert get_head_revision() == ALEMBIC_HEAD_REVISION


@pytest.mark.smoke
def test_smoke_init_db_script_is_runnable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    db_path = tmp_path / "init-db-smoke.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from backend.config import get_settings
    from backend.db.migrations import get_current_revision
    from tests.helpers.persistence_testkit import reset_persistence_singletons

    reset_persistence_singletons()
    get_settings.cache_clear()

    script = REPO_ROOT / "scripts" / "init_db.py"
    spec = importlib.util.spec_from_file_location("init_db", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--show-revision"]) == 0
    from backend.db.migrations import ALEMBIC_HEAD_REVISION

    assert get_current_revision() == ALEMBIC_HEAD_REVISION
