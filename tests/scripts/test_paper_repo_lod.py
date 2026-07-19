# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Capability-based AST guard tests for private repository attributes."""

from __future__ import annotations

import ast

import pytest
from scripts.check_pipeline_repo_lod import (
    ArchitectureViolationError,
    _CapabilityRepoGuardVisitor,
    check_pipeline_repo_lod,
    is_repo_capability_owner,
)


def _hits(source: str, *, rel_path: str) -> list[tuple[int, str]]:
    visitor = _CapabilityRepoGuardVisitor(rel_path)
    visitor.visit(ast.parse(source))
    return visitor.violations


def test_core_service_may_own_self_paper_repo() -> None:
    assert (
        _hits(
            "result = await self._paper_repo.get(paper_id)",
            rel_path="services/paper_core_service.py",
        )
        == []
    )


def test_paper_service_may_own_self_pipeline_repo() -> None:
    assert (
        _hits(
            "row = await self._pipeline_repo.get_latest(paper_id)",
            rel_path="services/paper_service.py",
        )
        == []
    )


def test_repository_module_may_reference_private_repo_fields() -> None:
    assert is_repo_capability_owner("repositories/paper_repository.py", "_paper_repo")
    assert is_repo_capability_owner("repositories/pipeline_repository.py", "_pipeline_repo")


def test_non_owner_self_paper_repo_is_rejected() -> None:
    hits = _hits(
        "result = await self._paper_repo.get(paper_id)",
        rel_path="services/paper_delete_service.py",
    )
    assert hits == [(1, "_paper_repo")]


def test_foreign_paper_repo_penetration_is_rejected_even_for_owners() -> None:
    hits = _hits(
        "result = await paper_service._paper_repo.get(paper_id)",
        rel_path="services/paper_core_service.py",
    )
    assert hits == [(1, "_paper_repo")]


def test_nested_foreign_pipeline_repo_penetration_is_rejected() -> None:
    hits = _hits(
        "row = await container.service._pipeline_repo.get_latest(paper_id)",
        rel_path="services/paper_pipeline_ops.py",
    )
    assert hits == [(1, "_pipeline_repo")]


def test_delete_service_piercing_paper_service_repo_is_rejected() -> None:
    hits = _hits(
        "paper = await paper_service._paper_repo.get(paper_id)",
        rel_path="services/paper_delete_service.py",
    )
    assert hits == [(1, "_paper_repo")]


def test_architecture_violation_message_includes_knowledge_chain() -> None:
    with pytest.raises(ArchitectureViolationError) as exc_info:
        raise ArchitectureViolationError(
            rel_path="services/paper_delete_service.py",
            lineno=42,
            attr="_paper_repo",
        )
    message = str(exc_info.value)
    assert "Disallowed private repository penetration detected" in message
    assert "line 42" in message
    assert "services/paper_delete_service.py" in message
    assert "_paper_repo" in message


def test_repo_wide_capability_guard_is_clean() -> None:
    assert check_pipeline_repo_lod() == []


def test_capability_owner_patterns_are_role_based_not_caller_allowlist() -> None:
    """Owners are declared by role globs; lifecycle orchestrators are not owners."""
    assert is_repo_capability_owner("services/paper_core_service.py", "_paper_repo")
    assert is_repo_capability_owner("services/paper_service.py", "_paper_repo")
    assert is_repo_capability_owner("services/paper_pipeline_ops.py", "_pipeline_repo")
    assert not is_repo_capability_owner("services/paper_delete_service.py", "_paper_repo")
    assert not is_repo_capability_owner("services/reextract_service.py", "_paper_repo")
    assert not is_repo_capability_owner("services/paper_delete_service.py", "_pipeline_repo")
