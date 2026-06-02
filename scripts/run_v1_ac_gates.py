#!/usr/bin/env python3
"""
V1 A～C 自动化门禁（C-09：合 develop / 答辩前复跑）。

在仓库根目录执行::

    uv run python scripts/run_v1_ac_gates.py
    uv run python scripts/run_v1_ac_gates.py --with-cp4-api   # 需后端 :8000

覆盖：
- A/D：check_backend（ruff + pytest）；详见 ``scripts/run_d_gates.py``（D-01～D-10；D-11/D-12 见 pytest）
- B/C-02：frontend npm run check:ci
- C-03/C-04：run_qa --smoke-m2、run_patrol --smoke-patrol
- 可选：run_cp4_rehearsal --api-only（C-05）

退出码：0 全部通过；1 有失败步骤。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"


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


def run_gates(*, with_cp4_api: bool = False, skip_frontend: bool = False) -> GateReport:
    report = GateReport()
    py = sys.executable

    backend = run_cmd("A/D check_backend", [py, str(REPO_ROOT / "scripts" / "check_backend.py")])
    report.steps.append(backend)

    if not skip_frontend:
        fe = run_cmd(
            "B/C-02 frontend check:ci",
            ["npm", "run", "check:ci"],
            cwd=FRONTEND_DIR,
        )
        report.steps.append(fe)

    qa = run_cmd(
        "C-03 run_qa smoke-m2",
        [py, str(REPO_ROOT / "scripts" / "run_qa.py"), "--smoke-m2", "--seed-demo-graph"],
    )
    report.steps.append(qa)

    patrol = run_cmd(
        "C-04 run_patrol smoke",
        [
            py,
            str(REPO_ROOT / "scripts" / "run_patrol.py"),
            "--seed-demo-graphs",
            "--smoke-patrol",
            "--compact",
        ],
    )
    report.steps.append(patrol)

    if with_cp4_api:
        cp4 = run_cmd(
            "C-05 cp4 api-only",
            [py, str(REPO_ROOT / "scripts" / "run_cp4_rehearsal.py"), "--api-only", "--seed"],
        )
        report.steps.append(cp4)

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph V1 A～C 自动化门禁")
    parser.add_argument(
        "--with-cp4-api",
        action="store_true",
        help="额外跑 CP4 后端 API 探针（需 uvicorn :8000）",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="跳过 npm run check:ci",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("=" * 60)
    print("ScholarGraph V1 A～C Gates")
    print("=" * 60)

    report = run_gates(with_cp4_api=args.with_cp4_api, skip_frontend=args.skip_frontend)

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
