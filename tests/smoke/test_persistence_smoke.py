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
def test_smoke_alembic_baseline_revision_exists() -> None:
    versions = list((REPO_ROOT / "alembic" / "versions").glob("*.py"))
    assert versions, "expected at least one Alembic revision"
