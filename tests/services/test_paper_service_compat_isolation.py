"""D8 architecture guard: compat shims must not live in production PaperService."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
PAPER_SERVICE_PATH = BACKEND_ROOT / "services" / "paper_service.py"

# Attribute / property access or legacy compat module references — not public APIs like
# ``list_papers``, ``save_status``, or ``seed_demo_papers``.
FORBIDDEN_COMPAT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\._papers\b",
        r"\._status\b",
        r"\._pdf_paths\b",
        r"def _papers\b",
        r"def _status\b",
        r"def _pdf_paths\b",
        r"_upsert_compat_paper_detail",
        r"paper_service_compat",
    )
)


def _scan_backend_python_sources() -> list[tuple[Path, int, str]]:
    violations: list[tuple[Path, int, str]] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern in FORBIDDEN_COMPAT_PATTERNS:
                if pattern.search(line):
                    violations.append((path, line_no, line.strip()))
                    break
    return violations


def test_paper_service_has_no_compat_dict_properties() -> None:
    source = PAPER_SERVICE_PATH.read_text(encoding="utf-8")
    assert "paper_service_compat" not in source
    assert "def _papers" not in source
    assert "def _status" not in source
    assert "def _pdf_paths" not in source
    assert "_upsert_compat_paper_detail" not in source


def test_backend_has_no_compat_dict_reads_or_writes() -> None:
    """Production ``backend/`` must never touch legacy ``_papers`` / ``_status`` / ``_pdf_paths``."""
    violations = _scan_backend_python_sources()
    if violations:
        details = "\n".join(f"  {path.relative_to(REPO_ROOT)}:{line_no}: {text}" for path, line_no, text in violations)
        raise AssertionError(
            "Forbidden compat dict references found in backend/:\n" + details,
        )


def test_compat_shims_live_under_tests_helpers() -> None:
    assert (REPO_ROOT / "tests" / "helpers" / "compat_shims.py").is_file()
    assert not (REPO_ROOT / "backend" / "services" / "paper_service_compat.py").exists()
