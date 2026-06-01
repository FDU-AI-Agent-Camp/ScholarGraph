"""Shared validators for V1 DoD §6.4 D — code-base standards gates."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Align with AGENTS.md §8.2 and @commitlint/config-conventional types.
CONVENTIONAL_COMMIT_TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)

CONVENTIONAL_COMMIT_HEADER = re.compile(
    rf"^({'|'.join(CONVENTIONAL_COMMIT_TYPES)})(\([a-z0-9./_-]+\))?!?: .+",
    re.IGNORECASE,
)

# work-assignment §3: feature/frontend/{slug} | feature/backend/{module[/slug]}
FEATURE_BRANCH = re.compile(
    r"^feature/(frontend/[a-z0-9._-]+|backend/[a-z0-9._-]+(?:/[a-z0-9._-]+)?)$",
    re.IGNORECASE,
)

INTEGRATION_BRANCHES = frozenset({"develop", "main", "master"})


def validate_conventional_commit_subject(subject: str) -> bool:
    """Return True when *subject* is a valid Conventional Commits header line."""
    line = subject.strip()
    if not line or line.lower().startswith("merge "):
        return True
    return CONVENTIONAL_COMMIT_HEADER.match(line) is not None


def validate_feature_branch_name(branch: str) -> bool:
    """Return True for integration branches or documented feature/* patterns."""
    name = branch.strip()
    if not name or name == "HEAD":
        return True
    if name in INTEGRATION_BRANCHES:
        return True
    return FEATURE_BRANCH.match(name) is not None


def git_current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (result.stdout or "").strip()


def git_recent_commit_subjects(*, count: int = 10) -> list[str]:
    result = subprocess.run(
        ["git", "log", f"-{count}", "--format=%s"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in (result.stdout or "").splitlines() if line.strip()]
