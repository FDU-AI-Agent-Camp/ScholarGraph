"""Shared validators for V1 DoD §6.4 D — code-base standards gates."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
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
    rf"^({'|'.join(CONVENTIONAL_COMMIT_TYPES)})(\([a-z0-9./_,-]+\))?!?: .+",
    re.IGNORECASE,
)

# work-assignment §3: feature/frontend/{slug} | feature/backend/{module[/slug]}
# Also allow hotfix/{slug} for urgent production fixes.
FEATURE_BRANCH = re.compile(
    r"^(feature/(frontend/[a-z0-9._-]+|backend/[a-z0-9._-]+(?:/[a-z0-9._-]+)?)|hotfix/[a-z0-9._-]+(?:/[a-z0-9._-]+)?)$",
    re.IGNORECASE,
)

INTEGRATION_BRANCHES = frozenset({"develop", "main", "master", "feature/integration"})

# handoff-to-platform.md §1 — BE-1～4 deliver services only; routes live under backend/api/.
BE_HANDOFF_MODULE_DIRS = (
    "backend/ingest",
    "backend/agents",
    "backend/patrol",
    "backend/graph",
    "backend/services",
    "backend/llm",
)

FORBIDDEN_HANDOFF_ROUTE_MARKERS = (
    "APIRouter",
    "include_router",
    "app.include_router",
)

# D-09 — must stay gitignored (see repo .gitignore).
REQUIRED_GITIGNORE_SENSITIVE_ENTRIES = (
    ".env",
    ".cursor/",
    "progress.md",
    "API KEY.txt",
)

# D-12 — AGENTS.md suggests keeping functions small; flag egregious files in CI.
BACKEND_GOD_FILE_LINE_BUDGET = 500


def scan_handoff_modules_for_private_routes() -> list[str]:
    """Return ``path: marker`` strings when BE delivery dirs import/register HTTP routes."""
    violations: list[str] = []
    for relative in BE_HANDOFF_MODULE_DIRS:
        root = REPO_ROOT / relative
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.name == "__pycache__":
                continue
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_HANDOFF_ROUTE_MARKERS:
                if marker in text:
                    violations.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {marker}")
    return violations


def validate_gitignore_sensitive_entries() -> list[str]:
    """Return missing required patterns from ``.gitignore``."""
    gitignore_path = REPO_ROOT / ".gitignore"
    if not gitignore_path.is_file():
        return ["missing .gitignore"]
    text = gitignore_path.read_text(encoding="utf-8")
    missing: list[str] = []
    for entry in REQUIRED_GITIGNORE_SENSITIVE_ENTRIES:
        if entry not in text:
            missing.append(entry)
    return missing


def validate_lockfiles_present() -> list[str]:
    """Return human-readable issues when manifest lock files are absent."""
    missing: list[str] = []
    if not (REPO_ROOT / "pyproject.toml").is_file():
        missing.append("pyproject.toml")
    if not (REPO_ROOT / "uv.lock").is_file():
        missing.append("uv.lock")
    if not (REPO_ROOT / "frontend" / "package.json").is_file():
        missing.append("frontend/package.json")
    if not (REPO_ROOT / "frontend" / "package-lock.json").is_file():
        missing.append("frontend/package-lock.json")
    return missing


def backend_python_files_exceeding_line_budget(*, budget: int = BACKEND_GOD_FILE_LINE_BUDGET) -> list[str]:
    """Return ``path (N lines)`` for backend ``*.py`` files over *budget*."""
    offenders: list[str] = []
    backend_root = REPO_ROOT / "backend"
    if not backend_root.is_dir():
        return offenders
    for path in sorted(backend_root.rglob("*.py")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > budget:
            rel = path.relative_to(REPO_ROOT).as_posix()
            offenders.append(f"{rel} ({line_count} lines)")
    return offenders


def api_route_handlers_missing_docstrings() -> list[str]:
    """Return route handler names in ``backend/api/routes`` lacking a docstring."""
    import ast

    missing: list[str] = []
    routes_dir = REPO_ROOT / "backend" / "api" / "routes"
    if not routes_dir.is_dir():
        return ["backend/api/routes missing"]
    for path in sorted(routes_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                target = decorator
                if isinstance(decorator, ast.Call):
                    target = decorator.func
                if isinstance(target, ast.Attribute) and target.attr in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                }:
                    if ast.get_docstring(node) is None:
                        rel = path.relative_to(REPO_ROOT).as_posix()
                        missing.append(f"{rel}::{node.name}")
                    break
    return missing


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


# Paths that must never appear in ``git ls-files`` (D-09).
SENSITIVE_TRACKED_PATHS = (
    ".env",
    "progress.md",
    "ui-design-progress.md",
    "API KEY.txt",
)

# Only BE-L platform layer may define FastAPI routers (D-07).
PLATFORM_ROUTER_PREFIXES = (
    "backend/api/routes/",
    "backend/api/router.py",
)


def backend_files_defining_api_router_outside_platform() -> list[str]:
    """Return backend ``*.py`` paths outside platform layer that reference ``APIRouter``."""
    violations: list[str] = []
    backend_root = REPO_ROOT / "backend"
    if not backend_root.is_dir():
        return violations
    for path in sorted(backend_root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "APIRouter" not in path.read_text(encoding="utf-8"):
            continue
        if any(rel.startswith(prefix) or rel == prefix for prefix in PLATFORM_ROUTER_PREFIXES):
            continue
        violations.append(rel)
    return violations


def git_sensitive_paths_must_not_be_tracked() -> list[str]:
    """Return sensitive paths that are currently tracked by git."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", *SENSITIVE_TRACKED_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode == 1 and "did not match" in (result.stderr or ""):
        return []
    return []


def git_paths_are_ignored(relative_paths: tuple[str, ...]) -> list[str]:
    """Return paths from *relative_paths* that are not ignored by git."""
    not_ignored: list[str] = []
    for rel in relative_paths:
        check = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        if check.returncode != 0:
            not_ignored.append(rel)
    return not_ignored


def lockfile_declares_python_project(project_name: str) -> bool:
    lock_path = REPO_ROOT / "uv.lock"
    if not lock_path.is_file():
        return False
    return f'name = "{project_name}"' in lock_path.read_text(encoding="utf-8")


def lockfile_declares_npm_package(package_name: str) -> bool:
    lock_path = REPO_ROOT / "frontend" / "package-lock.json"
    if not lock_path.is_file():
        return False
    text = lock_path.read_text(encoding="utf-8")
    return f'"name": "{package_name}"' in text and '"lockfileVersion"' in text


def npm_executable() -> str:
    """Resolve npm launcher (Windows needs ``npm.cmd`` for subprocess without shell)."""
    if sys.platform == "win32":
        return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return shutil.which("npm") or "npm"


def npm_run_argv(script: str, *extra: str) -> list[str]:
    """Build argv for ``npm run <script>`` cross-platform."""
    return [npm_executable(), "run", script, *extra]
