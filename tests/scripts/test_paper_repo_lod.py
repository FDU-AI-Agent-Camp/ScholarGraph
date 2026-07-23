# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Capability-based AST guard tests for private repository attributes.

Includes a falsification matrix that locks the Owner ∩ self/cls rule and
proves non-owner ``self._paper_repo`` attribute-smuggling cannot bypass CI.
"""

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


def _collect_violations(source: str, *, rel_path: str) -> list[ArchitectureViolationError]:
    """Mirror production messaging: each hit becomes an ArchitectureViolationError."""
    return [
        ArchitectureViolationError(rel_path=rel_path, lineno=lineno, attr=attr)
        for lineno, attr in _hits(source, rel_path=rel_path)
    ]


def _enforce_source(source: str, *, rel_path: str) -> None:
    """Raise the first capability violation for *source* (CI fuse simulation)."""
    violations = _collect_violations(source, rel_path=rel_path)
    if violations:
        raise violations[0]


# ---------------------------------------------------------------------------
# Falsification matrix (Owner ∩ self/cls)
# ---------------------------------------------------------------------------


def test_matrix_owner_self_introspection_is_green() -> None:
    """TestCase 1: Owner + ``self._paper_repo`` → pass."""
    source = "result = await self._paper_repo.get(paper_id)"
    rel_path = "services/paper_core_service.py"

    assert is_repo_capability_owner(rel_path, "_paper_repo")
    _enforce_source(source, rel_path=rel_path)
    assert _collect_violations(source, rel_path=rel_path) == []


def test_matrix_non_owner_foreign_penetration_is_red() -> None:
    """TestCase 2: non-Owner + ``paper_service._paper_repo`` → ArchitectureViolationError."""
    source = "result = await paper_service._paper_repo.get(paper_id)"
    rel_path = "services/reextract_service.py"

    assert not is_repo_capability_owner(rel_path, "_paper_repo")
    with pytest.raises(ArchitectureViolationError) as exc_info:
        _enforce_source(source, rel_path=rel_path)

    err = exc_info.value
    assert err.rel_path == rel_path
    assert err.attr == "_paper_repo"
    assert "Disallowed private repository penetration detected" in str(err)
    assert "services/reextract_service.py" in str(err)
    assert "_paper_repo" in str(err)


def test_matrix_non_owner_self_smuggling_is_red() -> None:
    """TestCase 3: non-Owner + ``self._paper_repo`` smuggling → still melts.

    Proves capability denial is identity-based, not merely a foreign-receiver check.
    Lifecycle services must keep the lexical alias ``_paper_repository``.
    """
    source = "result = await self._paper_repo.get(paper_id)"
    rel_path = "services/reextract_service.py"

    assert not is_repo_capability_owner(rel_path, "_paper_repo")
    with pytest.raises(ArchitectureViolationError) as exc_info:
        _enforce_source(source, rel_path=rel_path)

    err = exc_info.value
    assert err.rel_path == rel_path
    assert err.attr == "_paper_repo"
    assert "Disallowed private repository penetration detected" in str(err)
    assert "line 1" in str(err)


def test_matrix_non_owner_may_use_lexical_alias_without_guarded_attr() -> None:
    """Control: ``_paper_repository`` is outside the guarded namespace → green."""
    source = "result = await self._paper_repository.get(paper_id)"
    rel_path = "services/reextract_service.py"

    _enforce_source(source, rel_path=rel_path)
    assert _collect_violations(source, rel_path=rel_path) == []


# ---------------------------------------------------------------------------
# Broader regression coverage
# ---------------------------------------------------------------------------


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


def test_delete_service_self_smuggling_is_rejected() -> None:
    hits = _hits(
        "result = await self._paper_repo.get(paper_id)",
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
