"""V1 DoD §6.4 D-01～D-12 — code-base standards (static + gate wiring)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from scripts.d_gates_lib import (
    CONVENTIONAL_COMMIT_TYPES,
    REPO_ROOT,
    api_route_handlers_missing_docstrings,
    backend_files_defining_api_router_outside_platform,
    backend_python_files_exceeding_line_budget,
    git_paths_are_ignored,
    git_sensitive_paths_must_not_be_tracked,
    lockfile_declares_npm_package,
    lockfile_declares_python_project,
    scan_handoff_modules_for_private_routes,
    validate_conventional_commit_subject,
    validate_feature_branch_name,
    validate_gitignore_sensitive_entries,
    validate_lockfiles_present,
)

RUN_D_GATES = REPO_ROOT / "scripts" / "run_d_gates.py"
CHECK_BACKEND = REPO_ROOT / "scripts" / "check_backend.py"
BACKEND_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "backend.yml"
FRONTEND_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "frontend.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("feat(qa): wire SSE to qa_stream", True),
        ("test(integration): E robustness FE↔BE", True),
        ("docs(README): 完善协作说明", True),
        ("fix: patch patrol 409 mapping", True),
        ("chore: bump lockfile", True),
        ("Merge branch 'develop' into feature/x", True),
        ("update stuff", False),
        ("feat bad subject", False),
        ("WIP: temp", False),
    ],
)
def test_d05_conventional_commit_header(subject: str, expected: bool) -> None:
    assert validate_conventional_commit_subject(subject) is expected


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("develop", True),
        ("main", True),
        ("feature/frontend/scaffold-mock", True),
        ("feature/backend/graph-qa/multiscale-qa", True),
        ("feature/backend/be3-graph-qa-complete", True),
        ("feature/be1/ingest", False),
        ("feature/agent/foo", False),
        ("random-branch", False),
    ],
)
def test_d06_feature_branch_naming(branch: str, expected: bool) -> None:
    assert validate_feature_branch_name(branch) is expected


def test_d01_check_backend_script_exists_and_ruff_targets() -> None:
    source = CHECK_BACKEND.read_text(encoding="utf-8")
    assert "ruff check" in source
    assert "ruff format --check" in source
    assert "backend" in source and "tests" in source and "scripts" in source


def test_d02_pyproject_excludes_red_marker_by_default() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "addopts = \"-m 'not red'\"" in text or 'addopts = "-m not red"' in text
    assert "red:" in text


def test_d01_d02_backend_ci_matches_check_backend_commands() -> None:
    workflow = BACKEND_WORKFLOW.read_text(encoding="utf-8")
    assert "uv run ruff check backend tests scripts" in workflow
    assert "uv run ruff format --check backend tests scripts" in workflow
    assert 'pytest -q -m "not red"' in workflow


def test_d03_d04_frontend_ci_runs_check_not_only_typecheck() -> None:
    workflow = FRONTEND_WORKFLOW.read_text(encoding="utf-8")
    assert "npm run check" in workflow
    assert "npm run test" in workflow
    assert "npm run build" in workflow


def test_d05_agents_md_lists_conventional_commit_types() -> None:
    text = AGENTS_MD.read_text(encoding="utf-8")
    for commit_type in CONVENTIONAL_COMMIT_TYPES:
        assert f"`{commit_type}`" in text


def test_d05_recent_git_commits_follow_conventional_commits_if_history_exists() -> None:
    result = subprocess.run(
        ["git", "log", "-5", "--format=%s"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git repo")
    subjects = [line for line in result.stdout.splitlines() if line.strip()]
    if not subjects:
        pytest.skip("empty git history")
    bad = [subject for subject in subjects if not validate_conventional_commit_subject(subject)]
    assert not bad, f"non-conventional recent commits: {bad}"


def test_run_d_gates_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_D_GATES), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "D-01" in result.stdout or "check_backend" in result.stdout


def test_run_d_gates_commit_and_branch_checks_pass_on_repo() -> None:
    """Fast D-05/D-06 only — no ruff/pytest/npm."""
    from scripts.run_d_gates import check_d05_commits, check_d06_branch

    d05 = check_d05_commits(sample_size=10)
    d06 = check_d06_branch()
    assert d05.ok, d05.detail
    assert d06.ok, d06.detail


def test_d07_handoff_modules_do_not_register_http_routes() -> None:
    """BE-1～4 delivery dirs must not define APIRouter / include_router."""
    violations = scan_handoff_modules_for_private_routes()
    assert not violations, f"handoff route leaks: {violations}"


def test_d09_gitignore_blocks_sensitive_local_files() -> None:
    missing = validate_gitignore_sensitive_entries()
    assert not missing, f".gitignore missing: {missing}"


def test_d10_lockfiles_exist_next_to_manifests() -> None:
    missing = validate_lockfiles_present()
    assert not missing, f"lock/manifest missing: {missing}"


def test_d11_public_api_route_handlers_have_docstrings() -> None:
    missing = api_route_handlers_missing_docstrings()
    assert not missing, f"undocumented route handlers: {missing}"


def test_d12_backend_python_files_stay_under_god_file_budget() -> None:
    offenders = backend_python_files_exceeding_line_budget()
    assert not offenders, f"oversized backend modules: {offenders}"


def test_d07_handoff_doc_reiterates_no_private_routes() -> None:
    handoff = REPO_ROOT / "docs" / "v1" / "handoff-to-platform.md"
    text = handoff.read_text(encoding="utf-8")
    assert "不要" in text and "HTTP 路由" in text
    assert "APIRouter" in text or "只交付 Service" in text


def test_d07_platform_layer_is_only_api_router_owner() -> None:
    assert not backend_files_defining_api_router_outside_platform()


def test_d09_git_ignores_env_and_progress_when_in_work_tree() -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git work tree")
    assert not git_paths_are_ignored((".env", "progress.md"))


def test_d09_sensitive_paths_not_in_git_index() -> None:
    assert not git_sensitive_paths_must_not_be_tracked()


def test_d10_lockfiles_declare_project_names() -> None:
    assert lockfile_declares_python_project("scholargraph")
    assert lockfile_declares_npm_package("scholargraph-frontend")
