# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Orchestrate the dual-revision async hot-path benchmark matrix.

Creates (or reuses) Git worktrees for the baseline and candidate commits, copies
the portable runner into each worktree, and executes cells in alternating
revision order to reduce host-noise bias. Raw JSON is written under
``--output-dir/raw``; aggregation is left to ``compare_async_hotpath_benchmarks``.

Default matrix (matches the approved design for the finalize layer; HTTP is
reduced because residual ``run_async`` + SQLite write locks saturate above ~10)::

    finalize: concurrency 1/10/25/50/100, 500 ops, 50 warmup, 5 reps
    http:     concurrency 1/5/10,        100 ops, 10 warmup, 3 reps
    diskio:   concurrency 1/5/10/25,     200 ops, 20 warmup, 3 reps
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASELINE_COMMIT = "e847cc0"
# Candidate tip is overridden by CLI in CI/ChatOps; keep a documented default for local runs.
CANDIDATE_COMMIT = "HEAD"
RUNNER_NAME = "benchmark_async_hotpath.py"
COMPARE_NAME = "compare_async_hotpath_benchmarks.py"
AUDIT_NAME = "audit_async_thread_trail.py"

DEFAULT_FINALIZE = {
    "concurrency": (1, 10, 25, 50, 100),
    "operations": 500,
    "warmup": 50,
    "repetitions": 5,
}
DEFAULT_HTTP = {
    "concurrency": (1, 5, 10),
    "operations": 100,
    "warmup": 10,
    "repetitions": 3,
}
DEFAULT_DISKIO = {
    "concurrency": (1, 5, 10, 25),
    "operations": 200,
    "warmup": 20,
    "repetitions": 3,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, cwd: Path | None = None, allow_exit_codes: set[int] | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=cwd, check=False)
    allowed = allow_exit_codes or {0}
    if completed.returncode not in allowed:
        raise subprocess.CalledProcessError(completed.returncode, cmd)
    return completed.returncode


def _ensure_worktree(path: Path, commit: str, repo_root: Path) -> None:
    if path.exists():
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            text=True,
        ).strip()
        if head.startswith(commit):
            print(f"reuse worktree {path} @ {head[:12]}")
            return
        raise SystemExit(f"worktree {path} exists but HEAD={head} != {commit}")
    _run(["git", "worktree", "add", "--detach", str(path), commit], cwd=repo_root)


def _install_runner(worktree: Path, repo_root: Path) -> Path:
    scripts_dir = worktree / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    for name in (RUNNER_NAME, COMPARE_NAME):
        shutil.copy2(repo_root / "scripts" / name, scripts_dir / name)
    return scripts_dir / RUNNER_NAME


def _python_for(worktree: Path, repo_root: Path) -> Path:
    # Prefer the root .venv so both revisions share the same interpreter / deps.
    root_py = repo_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if root_py.is_file():
        return root_py
    local_py = worktree / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if local_py.is_file():
        return local_py
    return Path(sys.executable)


def _cell_output(raw_dir: Path, label: str, layer: str, concurrency: int, repetition: int) -> Path:
    return raw_dir / f"{label}-{layer}-c{concurrency}-r{repetition}.json"


def _run_cell(
    *,
    python: Path,
    runner: Path,
    worktree: Path,
    label: str,
    commit: str,
    layer: str,
    concurrency: int,
    operations: int,
    warmup: int,
    repetition: int,
    output: Path,
    busy_timeout_s: int,
    affinity_core: int | None,
) -> None:
    if output.is_file():
        print(f"skip existing {output.name}")
        return
    cmd = [
        str(python),
        str(runner),
        "--layer",
        layer,
        "--concurrency",
        str(concurrency),
        "--operations",
        str(operations),
        "--warmup",
        str(warmup),
        "--repetition",
        str(repetition),
        "--label",
        label,
        "--expect-commit",
        commit,
        "--output",
        str(output),
        "--busy-timeout-s",
        str(busy_timeout_s),
        "--hang-dump-s",
        "0",
    ]
    if affinity_core is None:
        cmd.append("--no-affinity")
    else:
        cmd.extend(["--affinity-core", str(affinity_core)])
    # Exit 2 = measured ops had errors but raw JSON was still written (expected under
    # SQLite write-lock saturation at high concurrency). Continue the matrix.
    _run(cmd, cwd=worktree, allow_exit_codes={0, 2})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--worktree-root",
        default="",
        help="directory that will hold bench-baseline / bench-candidate worktrees",
    )
    parser.add_argument(
        "--output-dir",
        default="data/benchmarks/async-hotpath",
        help="raw + aggregated outputs (relative to repo root unless absolute)",
    )
    parser.add_argument("--busy-timeout-s", type=int, default=5)
    parser.add_argument("--affinity-core", type=int, default=0)
    parser.add_argument("--no-affinity", action="store_true")
    parser.add_argument("--layers", default="finalize,http", help="comma list")
    parser.add_argument("--quick", action="store_true", help="tiny matrix for smoke")
    parser.add_argument("--skip-aggregate", action="store_true")
    parser.add_argument(
        "--candidate-working-tree",
        action="store_true",
        help="run candidate cells from the repo working tree (includes uncommitted fixes)",
    )
    parser.add_argument(
        "--baseline-commit",
        default=BASELINE_COMMIT,
        help=f"baseline git commit / ref (default {BASELINE_COMMIT})",
    )
    parser.add_argument(
        "--candidate-commit",
        default=CANDIDATE_COMMIT,
        help="candidate git commit / ref when not using --candidate-working-tree (default HEAD)",
    )
    parser.add_argument(
        "--output-md",
        default="",
        help="comparison markdown path (default: docs/performance/async-hotpath-benchmark.md)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = _repo_root()
    worktree_root = Path(args.worktree_root) if args.worktree_root else Path(tempfile.gettempdir()) / "sg-hotpath-wt"
    worktree_root.mkdir(parents=True, exist_ok=True)

    baseline_commit = _resolve_commit(args.baseline_commit, repo_root)
    baseline_wt = worktree_root / "bench-baseline"
    _ensure_worktree(baseline_wt, baseline_commit, repo_root)
    baseline_runner = _install_runner(baseline_wt, repo_root)

    if args.candidate_working_tree:
        candidate_wt = repo_root
        candidate_runner = repo_root / "scripts" / RUNNER_NAME
        candidate_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
        ).strip()
        print(f"candidate = working tree @ {candidate_commit[:12]} ({repo_root})")
    else:
        candidate_commit = _resolve_commit(args.candidate_commit, repo_root)
        candidate_wt = worktree_root / "bench-candidate"
        _ensure_worktree(candidate_wt, candidate_commit, repo_root)
        candidate_runner = _install_runner(candidate_wt, repo_root)
        print(f"candidate = worktree @ {candidate_commit[:12]} ({candidate_wt})")

    python = _python_for(candidate_wt, repo_root)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    matrices = {
        "finalize": dict(DEFAULT_FINALIZE),
        "http": dict(DEFAULT_HTTP),
        "diskio": dict(DEFAULT_DISKIO),
    }
    if args.quick:
        matrices = {
            "finalize": {"concurrency": (1, 10), "operations": 30, "warmup": 5, "repetitions": 2},
            "http": {"concurrency": (1, 5), "operations": 20, "warmup": 3, "repetitions": 2},
            "diskio": {"concurrency": (1, 5, 10), "operations": 40, "warmup": 6, "repetitions": 2},
        }

    layers = [layer.strip() for layer in args.layers.split(",") if layer.strip()]
    unknown = [layer for layer in layers if layer not in matrices]
    if unknown:
        raise SystemExit(f"unknown layers: {unknown}; expected one of {sorted(matrices)}")
    affinity = None if args.no_affinity else args.affinity_core

    revisions = (
        ("baseline", baseline_commit, baseline_wt, baseline_runner),
        ("candidate", candidate_commit, candidate_wt, candidate_runner),
    )

    for layer in layers:
        matrix = matrices[layer]
        for concurrency in matrix["concurrency"]:
            # Alternate revision order per repetition to reduce host-noise bias.
            for repetition in range(matrix["repetitions"]):
                ordered = revisions if repetition % 2 == 0 else tuple(reversed(revisions))
                for label, commit, worktree, runner in ordered:
                    _run_cell(
                        python=python,
                        runner=runner,
                        worktree=worktree,
                        label=label,
                        commit=commit,
                        layer=layer,
                        concurrency=concurrency,
                        operations=matrix["operations"],
                        warmup=matrix["warmup"],
                        repetition=repetition,
                        output=_cell_output(raw_dir, label, layer, concurrency, repetition),
                        busy_timeout_s=args.busy_timeout_s,
                        affinity_core=affinity,
                    )

    if not args.skip_aggregate:
        compare = repo_root / "scripts" / COMPARE_NAME
        output_md = Path(args.output_md) if args.output_md else (output_dir / "comparison.md")
        if not output_md.is_absolute():
            output_md = repo_root / output_md
        _run(
            [
                str(python),
                str(compare),
                "--input-dir",
                str(raw_dir),
                "--output-json",
                str(output_dir / "comparison.json"),
                "--output-md",
                str(output_md),
            ],
            cwd=repo_root,
        )
    print(f"raw outputs: {raw_dir}")
    return 0


def _resolve_commit(ref: str, repo_root: Path) -> str:
    """Resolve a ref to a full commit hash (supports HEAD / short / tag)."""
    return subprocess.check_output(
        ["git", "rev-parse", ref],
        cwd=repo_root,
        text=True,
    ).strip()


if __name__ == "__main__":
    raise SystemExit(main())
