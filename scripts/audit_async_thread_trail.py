# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Dynamic thread/coroutine trail audit for the pipeline finalize hot path.

Instruments ``PipelineCompletionService.finalize`` (GraphStore persist +
``complete_paper_pipeline`` + EventBus publish + Repo writes) and records the
thread identity at each site. Designed to run unmodified in either the baseline
(sync / ``run_async`` / ``publish_sync``) or candidate (await-only / ``to_thread``)
revision.

Verdict rules (candidate)::

- ``complete_paper_pipeline``, Repo writes, and ``EventBus.publish`` stay on the
  registered main event-loop thread (no ``run_async`` bridge hop).
- ``GraphStore.save`` alone leaves that thread (``asyncio.to_thread`` pool).

Verdict rules (baseline)::

- ``run_async`` caller sits on the main loop thread while the bridged coroutine /
  Repo body executes elsewhere (cross-thread travel).
- ``GraphStore.save`` typically stays on the caller thread (sync disk I/O).

Usage (from a worktree root)::

    python scripts/audit_async_thread_trail.py \\
        --label candidate --expect-commit ac286f9 \\
        --output data/benchmarks/async-thread-trail/candidate.json
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
_BENCH_FULL_TEXT = "Thread-trail audit full text. " * 8

# Sites that must stay on the main loop after the async refactor.
LOOP_AFFINITY_SITES = frozenset(
    {
        "finalize.entry",
        "complete_paper_pipeline.entry",
        "repo.PaperRepository.update_classification",
        "repo.PaperRepository.update_paths",
        "repo.PaperRepository.update_graph_version",
        "repo.PipelineRepository.save_status",
        "repo.PipelineRepository.clear_preview_graph",
        "event_bus.publish",
        "graph_persistence.save.entry",
    },
)
DISK_OFFLOAD_SITES = frozenset({"graph.GraphStore.save"})
BRIDGE_SITES = frozenset({"run_async.caller", "run_async.executor", "event_bus.publish_sync"})


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested; no backend imports at module level)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrailEvent:
    seq: int
    site: str
    thread_id: int
    thread_name: str
    is_main_loop_thread: bool
    is_bridge_thread: bool
    is_to_thread_pool: bool


@dataclass
class TrailRecorder:
    """Thread-safe append-only trail of instrumented call sites."""

    main_loop_thread_id: int
    events: list[TrailEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _seq: int = 0

    def record(self, site: str) -> TrailEvent:
        thread = threading.current_thread()
        thread_id = threading.get_ident()
        thread_name = thread.name
        event = TrailEvent(
            seq=0,
            site=site,
            thread_id=thread_id,
            thread_name=thread_name,
            is_main_loop_thread=(thread_id == self.main_loop_thread_id),
            is_bridge_thread=(thread_name == "async-bridge-loop"),
            is_to_thread_pool=_looks_like_to_thread_pool(thread_name),
        )
        with self._lock:
            self._seq += 1
            event = TrailEvent(
                seq=self._seq,
                site=event.site,
                thread_id=event.thread_id,
                thread_name=event.thread_name,
                is_main_loop_thread=event.is_main_loop_thread,
                is_bridge_thread=event.is_bridge_thread,
                is_to_thread_pool=event.is_to_thread_pool,
            )
            self.events.append(event)
        return event

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(event) for event in self.events]


def _looks_like_to_thread_pool(thread_name: str) -> bool:
    lowered = thread_name.lower()
    return lowered.startswith("asyncio") or "threadpoolexecutor" in lowered or lowered.startswith("concurrent.futures")


def analyze_trail(
    events: list[dict[str, Any]],
    *,
    main_loop_thread_id: int,
    candidate_async: bool,
) -> dict[str, Any]:
    """Derive the pass/fail verdict from a recorded trail."""
    by_site: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_site.setdefault(event["site"], []).append(event)

    loop_site_threads: dict[str, list[int]] = {}
    for site in sorted(LOOP_AFFINITY_SITES):
        hits = by_site.get(site, [])
        if hits:
            loop_site_threads[site] = sorted({int(hit["thread_id"]) for hit in hits})

    disk_hits = by_site.get("graph.GraphStore.save", [])
    disk_thread_ids = sorted({int(hit["thread_id"]) for hit in disk_hits})
    run_async_callers = by_site.get("run_async.caller", [])
    run_async_executors = by_site.get("run_async.executor", [])
    publish_sync_hits = by_site.get("event_bus.publish_sync", [])

    loop_sites_on_main = all(all(tid == main_loop_thread_id for tid in tids) for tids in loop_site_threads.values())
    unique_loop_threads = sorted({tid for tids in loop_site_threads.values() for tid in tids})
    loop_thread_unified = len(unique_loop_threads) <= 1 and (
        not unique_loop_threads or unique_loop_threads == [main_loop_thread_id]
    )

    disk_left_main = bool(disk_hits) and all(tid != main_loop_thread_id for tid in disk_thread_ids)
    disk_on_main = bool(disk_hits) and all(tid == main_loop_thread_id for tid in disk_thread_ids)
    bridge_hop_detected = any(bool(hit["is_main_loop_thread"]) for hit in run_async_callers) and any(
        not bool(hit["is_main_loop_thread"]) for hit in run_async_executors
    )

    if candidate_async:
        passed = (
            loop_sites_on_main
            and loop_thread_unified
            and disk_left_main
            and not run_async_callers
            and not publish_sync_hits
        )
        expected = (
            "loop-affinity sites share the main event-loop thread; "
            "GraphStore.save runs off-loop via to_thread; no run_async / publish_sync"
        )
    else:
        passed = bridge_hop_detected or (bool(run_async_callers) and not loop_sites_on_main)
        # Baseline GraphStore.save is usually sync on the caller thread.
        expected = (
            "run_async (or publish_sync) produces a main-loop → bridge-thread hop; "
            "GraphStore.save typically remains on the caller thread"
        )

    return {
        "passed": passed,
        "expected": expected,
        "candidate_async": candidate_async,
        "main_loop_thread_id": main_loop_thread_id,
        "loop_affinity": {
            "sites_observed": loop_site_threads,
            "all_on_main_loop": loop_sites_on_main,
            "unified_thread_ids": unique_loop_threads,
        },
        "disk_offload": {
            "sites_observed": {"graph.GraphStore.save": disk_thread_ids},
            "left_main_loop": disk_left_main,
            "stayed_on_main_loop": disk_on_main,
            "to_thread_pool_hits": sum(1 for hit in disk_hits if hit.get("is_to_thread_pool")),
        },
        "bridge": {
            "run_async_caller_count": len(run_async_callers),
            "run_async_executor_count": len(run_async_executors),
            "publish_sync_count": len(publish_sync_hits),
            "cross_thread_hop_detected": bridge_hop_detected,
        },
        "event_count": len(events),
        "sites_seen": sorted(by_site),
    }


def render_trail_markdown(document: dict[str, Any]) -> str:
    verdict = document["verdict"]
    lines = [
        "# Async Thread-Trail Audit",
        "",
        f"- label: `{document['label']}`",
        f"- commit: `{document['commit']}`",
        f"- candidate_async: `{verdict['candidate_async']}`",
        f"- passed: **{verdict['passed']}**",
        f"- expected: {verdict['expected']}",
        "",
        "## Thread identity summary",
        "",
        f"- main loop thread id: `{verdict['main_loop_thread_id']}`",
        f"- loop-affinity unified ids: `{verdict['loop_affinity']['unified_thread_ids']}`",
        f"- loop-affinity all on main: `{verdict['loop_affinity']['all_on_main_loop']}`",
        f"- GraphStore.save left main: `{verdict['disk_offload']['left_main_loop']}`",
        f"- run_async callers/executors: "
        f"{verdict['bridge']['run_async_caller_count']}/"
        f"{verdict['bridge']['run_async_executor_count']}",
        f"- publish_sync count: `{verdict['bridge']['publish_sync_count']}`",
        f"- cross-thread hop detected: `{verdict['bridge']['cross_thread_hop_detected']}`",
        "",
        "## Chronological trail",
        "",
        "| seq | site | thread_id | thread_name | main | bridge | to_thread |",
        "|---|---|---|---|---|---|---|",
    ]
    for event in document["trail"]:
        lines.append(
            f"| {event['seq']} | `{event['site']}` | {event['thread_id']} | "
            f"{event['thread_name']} | {event['is_main_loop_thread']} | "
            f"{event['is_bridge_thread']} | {event['is_to_thread_pool']} |",
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Environment / instrumentation (backend imports deferred)
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
    db_path = workdir / "audit.db"
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
        "APP_PROFILE": "ci",
    }
    os.environ.update(env)
    return env


def _wrap_callable(original: Any, site: str, recorder: TrailRecorder) -> Any:
    if inspect.iscoroutinefunction(original):

        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            recorder.record(site)
            return await original(*args, **kwargs)

        return _async_wrapper

    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        recorder.record(site)
        return original(*args, **kwargs)

    return _sync_wrapper


def _install_run_async_probe(recorder: TrailRecorder) -> list[str]:
    """Wrap ``run_async`` and rebind every already-imported module alias."""
    import backend.repositories as repositories_pkg
    import backend.repositories.async_bridge as bridge

    original = bridge.run_async

    def audited_run_async(coro: Any) -> Any:
        recorder.record("run_async.caller")

        async def tracked() -> Any:
            recorder.record("run_async.executor")
            return await coro

        return original(tracked())

    bridge.run_async = audited_run_async  # type: ignore[assignment]
    repositories_pkg.run_async = audited_run_async  # type: ignore[assignment]
    rebound = ["backend.repositories.async_bridge", "backend.repositories"]
    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
        if getattr(module, "run_async", None) is original:
            module.run_async = audited_run_async
            rebound.append(module_name)
    return [f"run_async rebound on {name}" for name in sorted(set(rebound))]


def _install_instrumentation(recorder: TrailRecorder) -> list[str]:
    """Monkeypatch call sites present in both revisions; skip missing ones."""
    notes: list[str] = []

    # Force-import modules that bind ``run_async`` at import time before rebinding.
    import backend.events.bus as bus_module
    import backend.graph.store as store_module
    import backend.repositories.paper_repository as paper_repo_module
    import backend.repositories.pipeline_repository as pipeline_repo_module
    import backend.services.graph_persistence_service as persistence_module
    import backend.services.paper_service  # noqa: F401
    import backend.services.pipeline_completion_service as completion_module
    import backend.services.pipeline_status_service  # noqa: F401
    import backend.services.status_snapshot_guard  # noqa: F401

    notes.extend(_install_run_async_probe(recorder))

    targets: list[tuple[Any, str, str]] = [
        (completion_module, "complete_paper_pipeline", "complete_paper_pipeline.entry"),
        (bus_module.EventBus, "publish", "event_bus.publish"),
        (bus_module.EventBus, "publish_sync", "event_bus.publish_sync"),
        (store_module.GraphStore, "save", "graph.GraphStore.save"),
        (persistence_module.GraphPersistenceService, "save", "graph_persistence.save.entry"),
        (paper_repo_module.PaperRepository, "update_classification", "repo.PaperRepository.update_classification"),
        (paper_repo_module.PaperRepository, "update_paths", "repo.PaperRepository.update_paths"),
        (paper_repo_module.PaperRepository, "update_graph_version", "repo.PaperRepository.update_graph_version"),
        (pipeline_repo_module.PipelineRepository, "save_status", "repo.PipelineRepository.save_status"),
        (pipeline_repo_module.PipelineRepository, "clear_preview_graph", "repo.PipelineRepository.clear_preview_graph"),
    ]
    for owner, attr, site in targets:
        original = getattr(owner, attr, None)
        if original is None:
            notes.append(f"skip missing {site}")
            continue
        setattr(owner, attr, _wrap_callable(original, site, recorder))
        notes.append(f"wrapped {site}")

    svc_cls = completion_module.PipelineCompletionService
    original_finalize_method = svc_cls.finalize
    svc_cls.finalize = _wrap_callable(original_finalize_method, "finalize.entry", recorder)
    notes.append("wrapped finalize.entry")
    return notes


def _install_noop_finalized_handler() -> None:
    from backend.events.bus import get_event_bus
    from backend.events.pipeline_finalized_handlers import unregister_pipeline_finalized_handlers
    from backend.events.types import EventType

    unregister_pipeline_finalized_handlers()

    async def _noop(_event: Any) -> None:
        return None

    get_event_bus().subscribe(EventType.PIPELINE_FINALIZED, _noop)


def _build_graph(paper_id: str) -> Any:
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    return UnifiedPaperGraph(
        paper_id=paper_id,
        title="thread-trail audit",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="n1", label="Audit node A", type="Method"),
            GraphNode(id="n2", label="Audit node B", type="Method"),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n2",
                label="supports",
                type="SUPPORTS",
                rationale="Deterministic audit support edge with explicit rationale.",
            ),
        ],
        summary="thread trail audit graph",
    )


def _bench_classification() -> Any:
    from backend.schemas.paradigm import Paradigm, ParadigmClassification

    return ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="audit")


async def _create_schema() -> None:
    import backend.db.models  # noqa: F401
    from backend.db.base import Base, get_async_engine
    from sqlalchemy import text

    engine = get_async_engine()
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_pending_paper(paper_id: str, pdf_path: str) -> None:
    from backend.repositories.paper_repository import get_paper_repository
    from backend.schemas.paper import PaperStatus

    await get_paper_repository().create(paper_id, f"audit {paper_id}", pdf_path, status=PaperStatus.PENDING)


def _is_candidate_async() -> bool:
    from backend.services.pipeline_completion_service import complete_paper_pipeline

    return inspect.iscoroutinefunction(complete_paper_pipeline)


async def _teardown_backend() -> None:
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


async def _run_audit(recorder: TrailRecorder) -> dict[str, Any]:
    from backend.repositories.async_bridge import register_main_event_loop
    from backend.services.pipeline_completion_service import get_pipeline_completion_service

    register_main_event_loop(asyncio.get_running_loop())
    # Re-bind main loop thread id after registration (same thread as asyncio.run).
    recorder.main_loop_thread_id = threading.get_ident()

    await _create_schema()
    notes = _install_instrumentation(recorder)
    _install_noop_finalized_handler()

    upload_dir = Path(os.environ["UPLOAD_DIR"])
    pdf_path = upload_dir / "audit.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF_BYTES)
    paper_id = "audit-thread-trail-001"
    await _seed_pending_paper(paper_id, str(pdf_path))

    graph = _build_graph(paper_id)
    classification = _bench_classification()
    service = get_pipeline_completion_service()
    result = service.finalize(
        paper_id,
        graph_data=graph.model_dump(mode="json"),
        classification_data=classification.model_dump(mode="json"),
        extract_warnings=[],
        full_text=_BENCH_FULL_TEXT,
        page_break_offsets=None,
        pipeline_generation_id=None,
    )
    if inspect.isawaitable(result):
        await result

    # Give EventBus a tick so publish handlers (noop) drain without affecting trail.
    if _is_candidate_async():
        from backend.events.bus import get_event_bus

        await get_event_bus().drain()
    else:
        from backend.events.bus import get_event_bus
        from backend.repositories.async_bridge import register_main_event_loop

        bus = get_event_bus()
        loop = asyncio.get_running_loop()
        register_main_event_loop(None)
        try:
            await asyncio.to_thread(bus.drain_sync)
        finally:
            register_main_event_loop(loop)

    return {
        "instrumentation_notes": notes,
        "paper_id": paper_id,
        "candidate_async": _is_candidate_async(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="e.g. baseline / candidate")
    parser.add_argument("--expect-commit", required=True)
    parser.add_argument("--output", required=True, help="JSON output path")
    parser.add_argument("--output-md", default="", help="optional Markdown trail report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = _resolve_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    commit = _verify_commit(args.expect_commit, repo_root)
    main_loop_thread_id = threading.get_ident()
    recorder = TrailRecorder(main_loop_thread_id=main_loop_thread_id)

    with tempfile.TemporaryDirectory(prefix="sg-thread-trail-") as tmp:
        workdir = Path(tmp)
        _bootstrap_environment(workdir)

        async def _run() -> dict[str, Any]:
            try:
                return await _run_audit(recorder)
            finally:
                await _teardown_backend()

        started = time.time()
        meta = asyncio.run(_run())
        time.sleep(0.2)

    trail = recorder.snapshot()
    verdict = analyze_trail(
        trail,
        main_loop_thread_id=recorder.main_loop_thread_id,
        candidate_async=bool(meta["candidate_async"]),
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "label": args.label,
        "commit": commit,
        "started_at_epoch": started,
        "env_fingerprint": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "meta": meta,
        "trail": trail,
        "verdict": verdict,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = Path(args.output_md) if args.output_md else output_path.with_suffix(".md")
    md_path.write_text(render_trail_markdown(document), encoding="utf-8")

    print(
        f"[{args.label}] passed={verdict['passed']} "
        f"events={verdict['event_count']} "
        f"run_async={verdict['bridge']['run_async_caller_count']}/"
        f"{verdict['bridge']['run_async_executor_count']} "
        f"disk_left_main={verdict['disk_offload']['left_main_loop']} "
        f"loop_on_main={verdict['loop_affinity']['all_on_main_loop']}",
    )
    print(f"wrote {output_path} and {md_path}")
    sys.stdout.flush()
    sys.stderr.flush()
    # Avoid Windows hangs from residual bridge/worker threads.
    os._exit(0 if verdict["passed"] else 2)


def compare_documents(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Build a dual-revision comparison payload (pure; unit-tested)."""
    return {
        "baseline_passed": baseline["verdict"]["passed"],
        "candidate_passed": candidate["verdict"]["passed"],
        "baseline_bridge_hop": baseline["verdict"]["bridge"]["cross_thread_hop_detected"],
        "candidate_bridge_hop": candidate["verdict"]["bridge"]["cross_thread_hop_detected"],
        "candidate_disk_offload": candidate["verdict"]["disk_offload"]["left_main_loop"],
        "baseline_disk_on_main": baseline["verdict"]["disk_offload"]["stayed_on_main_loop"],
        "story_matches_design": (
            baseline["verdict"]["passed"]
            and candidate["verdict"]["passed"]
            and baseline["verdict"]["bridge"]["cross_thread_hop_detected"]
            and not candidate["verdict"]["bridge"]["cross_thread_hop_detected"]
            and candidate["verdict"]["disk_offload"]["left_main_loop"]
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
