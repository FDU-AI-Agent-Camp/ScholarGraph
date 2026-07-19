# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Revision-portable async hot-path benchmark runner.

Runs ONE (layer, concurrency, repetition) cell and writes one raw JSON file.
Designed to execute unmodified inside a Git worktree checked out at either the
baseline (sync ``complete_paper_pipeline`` / ``publish_sync``) or the candidate
(await-only) revision: it only touches APIs that exist identically in both.

Layers:
- ``finalize``: concurrent ``complete_paper_pipeline`` calls for independent,
  pre-seeded papers with the official RAG handler replaced by an async no-op.
- ``http``: concurrent ``POST /api/v1/papers/{id}/reextract`` via httpx ASGI
  transport with abort / vector purge / pipeline scheduling stubbed.

Usage (from the worktree root)::

    python scripts/benchmark_async_hotpath.py \
        --layer finalize --concurrency 50 --operations 500 --warmup 50 \
        --repetition 0 --label candidate --expect-commit 3a8c661 \
        --output data/benchmarks/async-hotpath/raw/candidate-finalize-c50-r0.json
"""

from __future__ import annotations

import argparse
import asyncio
import faulthandler
import inspect
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
HEARTBEAT_INTERVAL_S = 0.005
DEFAULT_OP_TIMEOUT_S = 120.0
DEFAULT_AFFINITY_CORE = 0
_MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
_BENCH_FULL_TEXT = "Benchmark full text body. " * 8

# ---------------------------------------------------------------------------
# Pure helpers (unit-tested; no backend imports at module level)
# ---------------------------------------------------------------------------


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile over an ascending-sorted list; q in [0, 100]."""
    if not sorted_values:
        raise ValueError("percentile of empty list")
    if not 0.0 <= q <= 100.0:
        raise ValueError(f"q must be within [0, 100], got {q}")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (q / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = rank - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * fraction


def summarize_latencies(latencies_ms: list[float]) -> dict[str, float]:
    ordered = sorted(latencies_ms)
    return {
        "count": len(ordered),
        "p50_ms": percentile(ordered, 50),
        "p95_ms": percentile(ordered, 95),
        "p99_ms": percentile(ordered, 99),
        "mean_ms": sum(ordered) / len(ordered),
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
    }


class LoopLagProbe:
    """Heartbeat coroutine measuring event-loop wake-up lag on a fixed interval.

    Each cycle sleeps ``interval_s`` and records how far past the requested
    deadline the loop actually woke up. The next deadline starts from the
    actual wake-up, so a single long stall contributes one large sample
    instead of contaminating every following sample.
    """

    def __init__(self, interval_s: float = HEARTBEAT_INTERVAL_S) -> None:
        self._interval_s = interval_s
        self._samples_ms: list[float] = []
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    @property
    def samples_ms(self) -> list[float]:
        return list(self._samples_ms)

    def start(self) -> None:
        self._stopped = False
        self._samples_ms = []
        self._task = asyncio.get_running_loop().create_task(self._run(), name="loop-lag-probe")

    async def stop(self) -> list[float]:
        self._stopped = True
        if self._task is not None:
            await self._task
            self._task = None
        return self.samples_ms

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stopped:
            before = loop.time()
            await asyncio.sleep(self._interval_s)
            lag_s = (loop.time() - before) - self._interval_s
            self._samples_ms.append(max(0.0, lag_s) * 1000.0)


@dataclass
class OpResult:
    ok: bool
    latency_ms: float
    error_type: str | None = None


def classify_error(exc: BaseException) -> str:
    text = str(exc).lower()
    if "database is locked" in text:
        return f"{type(exc).__name__}:database_is_locked"
    return type(exc).__name__


async def run_bounded(
    ops: list[Callable[[], Awaitable[None]]],
    concurrency: int,
    *,
    op_timeout_s: float = DEFAULT_OP_TIMEOUT_S,
) -> list[OpResult]:
    """Execute *ops* with at most *concurrency* in flight; preserve per-op results.

    ``concurrency`` bounds in-flight operations (worker pool), it is not a
    single burst that schedules every coroutine at once.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    results: list[OpResult | None] = [None] * len(ops)
    index_queue: asyncio.Queue[int] = asyncio.Queue()
    for index in range(len(ops)):
        index_queue.put_nowait(index)

    async def worker() -> None:
        while True:
            try:
                index = index_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            started = time.perf_counter_ns()
            try:
                await asyncio.wait_for(ops[index](), timeout=op_timeout_s)
            except TimeoutError:
                latency_ms = (time.perf_counter_ns() - started) / 1e6
                results[index] = OpResult(ok=False, latency_ms=latency_ms, error_type="timeout")
            except Exception as exc:
                latency_ms = (time.perf_counter_ns() - started) / 1e6
                results[index] = OpResult(ok=False, latency_ms=latency_ms, error_type=classify_error(exc))
            else:
                latency_ms = (time.perf_counter_ns() - started) / 1e6
                results[index] = OpResult(ok=True, latency_ms=latency_ms)

    workers = [asyncio.get_running_loop().create_task(worker()) for _ in range(min(concurrency, len(ops)))]
    await asyncio.gather(*workers)
    final = [result for result in results if result is not None]
    if len(final) != len(ops):
        raise RuntimeError("bounded pool lost operation results")
    return final


def apply_cpu_affinity(core_index: int) -> str:
    """Pin the current process to one core. Returns 'coreN' on success, 'unset' otherwise."""
    try:
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, {core_index})  # type: ignore[attr-defined]  # Linux-only API
            return f"core{core_index}"
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]  # Windows-only API
            handle = kernel32.GetCurrentProcess()
            if kernel32.SetProcessAffinityMask(handle, 1 << core_index):
                return f"core{core_index}"
        return "unset"
    except Exception:
        return "unset"


class IncompatibleRevisionError(RuntimeError):
    """Raised when a required stub/API is missing in the checked-out revision."""


# ---------------------------------------------------------------------------
# Environment bootstrap (must run before any backend import)
# ---------------------------------------------------------------------------


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _verify_commit(expected_prefix: str, repo_root: Path) -> str:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()
    if not head.startswith(expected_prefix):
        raise SystemExit(f"HEAD {head} does not match --expect-commit {expected_prefix}")
    return head


def _bootstrap_environment(workdir: Path) -> dict[str, str]:
    db_path = workdir / "bench.db"
    graph_dir = workdir / "graphs"
    upload_dir = workdir / "uploads"
    graph_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    env = {
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "GRAPH_DATA_DIR": str(graph_dir),
        "UPLOAD_DIR": str(upload_dir),
        "SEED_DEMO_PAPERS": "false",
        "LLM_MODE": "mock",
        # Worktrees may lack a local .env; CI profile is the documented local/test default.
        "APP_PROFILE": "ci",
    }
    os.environ.update(env)
    return env


# ---------------------------------------------------------------------------
# Backend-facing workload (imports deferred so env vars apply first)
# ---------------------------------------------------------------------------


def _tune_engine_defaults(concurrency: int, busy_timeout_s: int) -> dict[str, int]:
    """Apply identical-for-both-revisions engine tuning BEFORE first engine build.

    - Pool must exceed worker concurrency: residual ``run_async`` ghost-sync
      blocks the main loop while other coroutines hold pooled connections; with
      the default pool (5+10) the bridge loop starves and the process deadlocks
      at concurrency > 15. This is an environment control, not a code change.
    - Busy timeout stays at the production default unless overridden via CLI.
    """
    import backend.db.base as db_base

    if db_base.get_async_engine.cache_info().currsize:
        raise RuntimeError("engine already built; tuning must happen first")
    pool_size = concurrency + 10
    max_overflow = concurrency + 10
    db_base.SQLITE_BUSY_TIMEOUT_SECONDS = busy_timeout_s  # type: ignore[attr-defined]  # module constant tune
    original_factory = db_base.create_async_engine

    def _tuned_factory(url: Any, **kwargs: Any) -> Any:
        if str(url).startswith("sqlite+aiosqlite:"):
            kwargs.setdefault("pool_size", pool_size)
            kwargs.setdefault("max_overflow", max_overflow)
        return original_factory(url, **kwargs)

    db_base.create_async_engine = _tuned_factory
    return {"pool_size": pool_size, "max_overflow": max_overflow, "busy_timeout_s": busy_timeout_s}


async def _create_schema_and_assert_wal() -> dict[str, Any]:
    import backend.db.models  # noqa: F401  (populate Base.metadata)
    from backend.db.base import Base, get_async_engine
    from sqlalchemy import text

    engine = get_async_engine()
    async with engine.connect() as conn:
        # WAL is a property of the DB file, so this single statement covers all
        # later connections in both revisions.
        await conn.execute(text("PRAGMA journal_mode=WAL"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
        busy_timeout_ms = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
        foreign_keys = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
    if str(journal_mode).lower() != "wal":
        raise SystemExit(f"journal_mode={journal_mode!r}, expected WAL (is the DB file-backed?)")
    if not busy_timeout_ms:
        raise SystemExit("PRAGMA busy_timeout is zero; refusing to benchmark without it")
    return {
        "journal_mode": str(journal_mode).lower(),
        "busy_timeout_ms": int(busy_timeout_ms),
        "foreign_keys": int(foreign_keys or 0),
    }


def _build_bench_graph(paper_id: str) -> Any:
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    return UnifiedPaperGraph(
        paper_id=paper_id,
        title="async hot-path benchmark",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="n1", label="Benchmark node A", type="Method"),
            GraphNode(id="n2", label="Benchmark node B", type="Method"),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n2",
                label="supports",
                type="SUPPORTS",
                rationale="Deterministic benchmark support edge with explicit rationale.",
            ),
        ],
        summary="benchmark graph",
    )


def _bench_classification() -> Any:
    from backend.schemas.paradigm import Paradigm, ParadigmClassification

    return ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="benchmark")


async def _seed_papers(
    paper_ids: list[str],
    *,
    status_name: str,
    pdf_path: str,
) -> None:
    from datetime import UTC, datetime

    from backend.repositories.paper_repository import get_paper_repository
    from backend.repositories.pipeline_repository import get_pipeline_repository
    from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage

    status = PaperStatus(status_name)
    paper_repo = get_paper_repository()
    pipeline_repo = get_pipeline_repository()
    now = datetime.now(UTC)
    for paper_id in paper_ids:
        await paper_repo.create(paper_id, f"bench {paper_id}", pdf_path, status=status)
        if status is PaperStatus.READY:
            snapshot = PaperStatusData(
                paper_id=paper_id,
                status=status,
                percent=100,
                stage=PipelineStage.READY,
                message="benchmark ready fixture",
                updated_at=now,
            )
        else:
            snapshot = PaperStatusData(
                paper_id=paper_id,
                status=status,
                percent=0,
                stage=None,
                message="benchmark pending fixture",
                updated_at=now,
            )
        await pipeline_repo.save_status(paper_id, snapshot)


def _is_candidate_async() -> bool:
    from backend.services.pipeline_completion_service import complete_paper_pipeline

    return inspect.iscoroutinefunction(complete_paper_pipeline)


async def _drain_event_bus_revision_aware() -> float:
    """Drain queued events on the loop that owns the bus queue; return seconds."""
    from backend.events.bus import get_event_bus
    from backend.repositories.async_bridge import register_main_event_loop

    bus = get_event_bus()
    started = time.perf_counter()
    if _is_candidate_async():
        await bus.drain()
    else:
        # Baseline publish_sync parked the queue on the bridge loop. drain_sync
        # must resolve to that same loop, so temporarily drop the main-loop
        # registration (otherwise run_async would target the wrong loop).
        loop = asyncio.get_running_loop()
        register_main_event_loop(None)
        try:
            await asyncio.to_thread(bus.drain_sync)
        finally:
            register_main_event_loop(loop)
    return time.perf_counter() - started


def _install_noop_finalized_handler() -> None:
    from backend.events.bus import get_event_bus
    from backend.events.pipeline_finalized_handlers import unregister_pipeline_finalized_handlers
    from backend.events.types import EventType

    unregister_pipeline_finalized_handlers()

    async def _noop_handler(_event: Any) -> None:
        return None

    get_event_bus().subscribe(EventType.PIPELINE_FINALIZED, _noop_handler)


def _make_matching_stub(original: Any) -> Any:
    if inspect.iscoroutinefunction(original):

        async def _async_stub(*_args: Any, **_kwargs: Any) -> None:
            return None

        return _async_stub

    def _sync_stub(*_args: Any, **_kwargs: Any) -> None:
        return None

    return _sync_stub


def _install_reextract_stubs() -> list[str]:
    """Stub abort / vector purge / scheduling by name; fail loudly if absent."""
    import backend.services.reextract_service as reextract_module

    required = ["abort_in_flight_pipeline", "_purge_vector_index", "schedule_paper_pipeline"]
    for name in required:
        original = getattr(reextract_module, name, None)
        if original is None:
            raise IncompatibleRevisionError(
                f"backend.services.reextract_service.{name} missing in this revision; "
                "HTTP layer cannot be stubbed without changing the measured boundary",
            )
        setattr(reextract_module, name, _make_matching_stub(original))

    optional_skipped: list[str] = []
    try:
        import backend.rag.wipe_vector_sweep as sweep_module
    except Exception:
        return ["backend.rag.wipe_vector_sweep (module missing)"]
    optional = {
        "snapshot_wipe_target_run_ids": lambda _paper_id: [],
        "extend_wipe_targets_after_abort": lambda _paper_id, targets: targets,
        "schedule_wipe_wave2_sweep": lambda _paper_id, _targets: None,
    }
    for name, replacement in optional.items():
        if hasattr(sweep_module, name):
            setattr(sweep_module, name, replacement)
        else:
            optional_skipped.append(f"backend.rag.wipe_vector_sweep.{name}")
    return optional_skipped


async def _run_finalize_layer(args: argparse.Namespace, workdir: Path) -> dict[str, Any]:
    from backend.repositories.async_bridge import register_main_event_loop
    from backend.services.paper_service import get_paper_service
    from backend.services.pipeline_completion_service import complete_paper_pipeline

    register_main_event_loop(asyncio.get_running_loop())
    pool_info = _tune_engine_defaults(args.concurrency, args.busy_timeout_s)
    wal_info = await _create_schema_and_assert_wal()
    wal_info.update(pool_info)
    _install_noop_finalized_handler()

    prefix = f"bench-fin-c{args.concurrency}-r{args.repetition}"
    warmup_ids = [f"{prefix}-w{i:04d}" for i in range(args.warmup)]
    measured_ids = [f"{prefix}-m{i:04d}" for i in range(args.operations)]
    await _seed_papers(warmup_ids + measured_ids, status_name="pending", pdf_path="./uploads/bench.pdf")

    paper_service = get_paper_service()
    classification = _bench_classification()
    graph_dir = Path(os.environ["GRAPH_DATA_DIR"])
    graphs = {paper_id: _build_bench_graph(paper_id) for paper_id in warmup_ids + measured_ids}

    def make_op(paper_id: str) -> Callable[[], Awaitable[None]]:
        async def op() -> None:
            result = complete_paper_pipeline(
                paper_service,
                paper_id,
                classification=classification,
                graph=graphs[paper_id],
                graph_path=str(graph_dir / f"{paper_id}.json"),
                full_text=_BENCH_FULL_TEXT,
                pipeline_generation_id=None,
            )
            if inspect.isawaitable(result):
                await result

        return op

    # Warm-up (untimed).
    await run_bounded([make_op(pid) for pid in warmup_ids], args.concurrency, op_timeout_s=args.op_timeout)
    await _drain_event_bus_revision_aware()

    probe = LoopLagProbe()
    probe.start()
    batch_started = time.perf_counter()
    results = await run_bounded(
        [make_op(pid) for pid in measured_ids],
        args.concurrency,
        op_timeout_s=args.op_timeout,
    )
    elapsed_s = time.perf_counter() - batch_started
    lag_samples_ms = await probe.stop()
    drain_s = await _drain_event_bus_revision_aware()

    return _build_results_payload(results, elapsed_s, drain_s, lag_samples_ms, wal_info, stub_notes=[])


async def _run_http_layer(args: argparse.Namespace, workdir: Path) -> dict[str, Any]:
    from backend.repositories.async_bridge import register_main_event_loop

    register_main_event_loop(asyncio.get_running_loop())
    pool_info = _tune_engine_defaults(args.concurrency, args.busy_timeout_s)
    wal_info = await _create_schema_and_assert_wal()
    wal_info.update(pool_info)
    _install_noop_finalized_handler()
    stub_notes = _install_reextract_stubs()

    upload_dir = Path(os.environ["UPLOAD_DIR"])
    shared_pdf = upload_dir / "bench-shared.pdf"
    shared_pdf.write_bytes(_MINIMAL_PDF_BYTES)

    prefix = f"bench-http-c{args.concurrency}-r{args.repetition}"
    warmup_ids = [f"{prefix}-w{i:04d}" for i in range(args.warmup)]
    measured_ids = [f"{prefix}-m{i:04d}" for i in range(args.operations)]
    await _seed_papers(warmup_ids + measured_ids, status_name="ready", pdf_path=str(shared_pdf))

    from backend.main import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://bench") as client:

        def make_op(paper_id: str) -> Callable[[], Awaitable[None]]:
            async def op() -> None:
                response = await client.post(f"/api/v1/papers/{paper_id}/reextract")
                if response.status_code != 200:
                    raise RuntimeError(f"http_{response.status_code}")

            return op

        await run_bounded([make_op(pid) for pid in warmup_ids], args.concurrency, op_timeout_s=args.op_timeout)
        await _drain_event_bus_revision_aware()

        probe = LoopLagProbe()
        probe.start()
        batch_started = time.perf_counter()
        results = await run_bounded(
            [make_op(pid) for pid in measured_ids],
            args.concurrency,
            op_timeout_s=args.op_timeout,
        )
        elapsed_s = time.perf_counter() - batch_started
        lag_samples_ms = await probe.stop()
        drain_s = await _drain_event_bus_revision_aware()

    return _build_results_payload(results, elapsed_s, drain_s, lag_samples_ms, wal_info, stub_notes=stub_notes)


def _build_results_payload(
    results: list[OpResult],
    elapsed_s: float,
    drain_s: float,
    lag_samples_ms: list[float],
    wal_info: dict[str, Any],
    *,
    stub_notes: list[str],
) -> dict[str, Any]:
    successes = [result for result in results if result.ok]
    errors: dict[str, int] = {}
    for result in results:
        if not result.ok and result.error_type is not None:
            errors[result.error_type] = errors.get(result.error_type, 0) + 1
    sorted_lags = sorted(lag_samples_ms)
    payload: dict[str, Any] = {
        "wal": wal_info,
        "stub_notes": stub_notes,
        "elapsed_s": elapsed_s,
        "drain_s": drain_s,
        "success_count": len(successes),
        "error_count": len(results) - len(successes),
        "errors": errors,
        "qps": (len(successes) / elapsed_s) if elapsed_s > 0 else 0.0,
        "latencies_ms": [result.latency_ms for result in successes],
        "loop_lag_ms": {
            "samples": lag_samples_ms,
            "count": len(sorted_lags),
            "p99": percentile(sorted_lags, 99) if sorted_lags else 0.0,
            "max": sorted_lags[-1] if sorted_lags else 0.0,
            "mean": (sum(sorted_lags) / len(sorted_lags)) if sorted_lags else 0.0,
        },
    }
    if successes:
        payload["latency_summary"] = summarize_latencies(payload["latencies_ms"])
    return payload


async def _teardown_backend() -> None:
    """Stop EventBus workers and dispose engines so temp files can be removed."""
    try:
        from backend.events.bus import stop_all_event_bus_workers

        stop_all_event_bus_workers()
    except Exception:
        pass
    try:
        from backend.db.base import get_async_engine

        if get_async_engine.cache_info().currsize:
            await get_async_engine().dispose()
    except Exception:
        pass
    try:
        from backend.repositories.async_bridge import register_main_event_loop

        register_main_event_loop(None)
    except Exception:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", choices=["finalize", "http"], required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--operations", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--label", required=True, help="e.g. baseline / candidate")
    parser.add_argument("--expect-commit", required=True, help="commit hash prefix HEAD must match")
    parser.add_argument("--output", required=True, help="raw JSON output path")
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--op-timeout", type=float, default=DEFAULT_OP_TIMEOUT_S)
    parser.add_argument("--affinity-core", type=int, default=DEFAULT_AFFINITY_CORE)
    parser.add_argument("--no-affinity", action="store_true")
    parser.add_argument(
        "--busy-timeout-s",
        type=int,
        default=30,
        help="SQLite busy timeout in seconds (default matches production)",
    )
    parser.add_argument(
        "--hang-dump-s",
        type=float,
        default=180.0,
        help="dump all thread stacks to stderr every N seconds (hang diagnosis); 0 disables",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = _resolve_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    commit = _verify_commit(args.expect_commit, repo_root)
    affinity = "unset" if args.no_affinity else apply_cpu_affinity(args.affinity_core)
    faulthandler.enable()
    if args.hang_dump_s > 0:
        faulthandler.dump_traceback_later(args.hang_dump_s, repeat=True)

    with tempfile.TemporaryDirectory(prefix="sg-hotpath-bench-") as tmp:
        workdir = Path(tmp)
        _bootstrap_environment(workdir)

        run_layer = _run_finalize_layer if args.layer == "finalize" else _run_http_layer

        async def _run() -> dict[str, Any]:
            try:
                return await run_layer(args, workdir)
            finally:
                await _teardown_backend()

        started_at = time.time()
        results = asyncio.run(_run())
        # Windows: give bridge/worker threads a beat to release the SQLite file.
        time.sleep(0.2)

    document = {
        "schema_version": SCHEMA_VERSION,
        "label": args.label,
        "commit": commit,
        "layer": args.layer,
        "concurrency": args.concurrency,
        "repetition": args.repetition,
        "started_at_epoch": started_at,
        "workload_fingerprint": {
            "layer": args.layer,
            "concurrency": args.concurrency,
            "operations": args.operations,
            "warmup": args.warmup,
            "seed": args.seed,
            "op_timeout_s": args.op_timeout,
            "busy_timeout_s": args.busy_timeout_s,
            "heartbeat_interval_s": HEARTBEAT_INTERVAL_S,
        },
        "env_fingerprint": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "affinity": affinity,
            "candidate_async": None,  # filled below without re-importing backend
        },
        "results": results,
    }
    document["env_fingerprint"]["candidate_async"] = _is_candidate_async()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    summary = results.get("latency_summary", {})
    print(
        f"[{args.label}/{args.layer}] c={args.concurrency} rep={args.repetition} "
        f"ok={results['success_count']} err={results['error_count']} "
        f"qps={results['qps']:.1f} p99={summary.get('p99_ms', float('nan')):.1f}ms "
        f"lag_max={results['loop_lag_ms']['max']:.1f}ms drain={results['drain_s'] * 1000:.0f}ms",
    )
    return 0 if results["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
