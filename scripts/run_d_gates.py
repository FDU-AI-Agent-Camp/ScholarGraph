#!/usr/bin/env python3
"""
V1 DoD §6.4 D — 代码基座规范性门禁（D-01～D-06）。

在仓库根目录执行::

    uv run python scripts/run_d_gates.py
    uv run python scripts/run_d_gates.py --skip-frontend   # 仅 D-01/D-02 + D-05/D-06
    uv run python scripts/run_d_gates.py --lint-only       # D-01 only（跳过 pytest）

覆盖：
- D-01/D-02：check_backend（ruff + pytest -m not red）
- D-03/D-04：frontend ``npm run check``（typecheck + format + lint + knip）
- D-05：最近 commit subject 符合 Conventional Commits
- D-06：当前分支名符合 work-assignment §3

退出码：0 全部通过；1 有失败步骤。
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"


def _load_d_gates_lib():
    spec = importlib.util.spec_from_file_location(
        "d_gates_lib",
        Path(__file__).with_name("d_gates_lib.py"),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_dg = _load_d_gates_lib()
git_current_branch = _dg.git_current_branch
git_recent_commit_subjects = _dg.git_recent_commit_subjects
validate_conventional_commit_subject = _dg.validate_conventional_commit_subject
validate_feature_branch_name = _dg.validate_feature_branch_name


@dataclass
class GateStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class GateReport:
    steps: list[GateStep] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(GateStep(name=name, ok=ok, detail=detail))
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"[{mark}] {name}{suffix}")

    @property
    def passed(self) -> bool:
        return all(step.ok for step in self.steps)


def run_cmd(name: str, cmd: list[str], *, cwd: Path | None = None) -> GateStep:
    print(f">> {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=cwd or REPO_ROOT, check=False)
    return GateStep(name=name, ok=completed.returncode == 0, detail=f"exit {completed.returncode}")


def check_d05_commits(*, sample_size: int) -> GateStep:
    subjects = git_recent_commit_subjects(count=sample_size)
    if not subjects:
        return GateStep("D-05 Conventional Commits", True, "no git history (skipped)")

    bad = [subject for subject in subjects if not validate_conventional_commit_subject(subject)]
    if bad:
        preview = "; ".join(bad[:3])
        return GateStep("D-05 Conventional Commits", False, f"non-conventional: {preview}")
    return GateStep("D-05 Conventional Commits", True, f"{len(subjects)} recent subjects OK")


def check_d06_branch() -> GateStep:
    branch = git_current_branch()
    if not branch:
        return GateStep("D-06 branch naming", True, "detached HEAD (skipped)")
    if validate_feature_branch_name(branch):
        return GateStep("D-06 branch naming", True, branch)
    return GateStep(
        "D-06 branch naming",
        False,
        f"{branch!r} — expect feature/frontend/… or feature/backend/…",
    )


def run_gates(*, skip_frontend: bool = False, lint_only: bool = False, commit_sample: int = 10) -> GateReport:
    report = GateReport()
    py = sys.executable

    check_cmd = [py, str(REPO_ROOT / "scripts" / "check_backend.py")]
    if lint_only:
        check_cmd.append("--lint-only")
    backend = run_cmd("D-01/D-02 check_backend", check_cmd)
    report.steps.append(backend)

    if not skip_frontend:
        fe = run_cmd("D-03/D-04 frontend check", ["npm", "run", "check"], cwd=FRONTEND_DIR)
        report.steps.append(fe)

    report.steps.append(check_d05_commits(sample_size=commit_sample))
    report.steps.append(check_d06_branch())
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph V1 §6.4 D code-base gates")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip npm run check")
    parser.add_argument("--lint-only", action="store_true", help="Run ruff only (D-01)")
    parser.add_argument(
        "--commit-sample",
        type=int,
        default=10,
        help="Number of recent commits to validate for D-05",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("=" * 60)
    print("ScholarGraph V1 §6.4 D Gates")
    print("=" * 60)

    report = run_gates(
        skip_frontend=args.skip_frontend,
        lint_only=args.lint_only,
        commit_sample=args.commit_sample,
    )

    print()
    print("=" * 60)
    passed = sum(1 for step in report.steps if step.ok)
    print(f"结果: {passed}/{len(report.steps)} 通过")
    if not report.passed:
        print("失败步骤:")
        for step in report.steps:
            if not step.ok:
                print(f"  - {step.name}: {step.detail}")
    print("=" * 60)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
