# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the async thread-trail audit analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.audit_async_thread_trail import (  # noqa: E402
    TrailRecorder,
    analyze_trail,
    compare_documents,
    render_trail_markdown,
)


def _event(
    seq: int,
    site: str,
    *,
    thread_id: int,
    main_id: int,
    name: str = "MainThread",
    bridge: bool = False,
    to_thread: bool = False,
) -> dict:
    return {
        "seq": seq,
        "site": site,
        "thread_id": thread_id,
        "thread_name": name,
        "is_main_loop_thread": thread_id == main_id,
        "is_bridge_thread": bridge,
        "is_to_thread_pool": to_thread,
    }


class TestAnalyzeTrail:
    def test_candidate_pass_when_loop_unified_and_disk_offloaded(self) -> None:
        main = 100
        pool = 200
        events = [
            _event(1, "finalize.entry", thread_id=main, main_id=main),
            _event(2, "graph_persistence.save.entry", thread_id=main, main_id=main),
            _event(
                3,
                "graph.GraphStore.save",
                thread_id=pool,
                main_id=main,
                name="asyncio_0",
                to_thread=True,
            ),
            _event(4, "complete_paper_pipeline.entry", thread_id=main, main_id=main),
            _event(5, "repo.PaperRepository.update_classification", thread_id=main, main_id=main),
            _event(6, "repo.PaperRepository.update_paths", thread_id=main, main_id=main),
            _event(7, "repo.PaperRepository.update_graph_version", thread_id=main, main_id=main),
            _event(8, "repo.PipelineRepository.save_status", thread_id=main, main_id=main),
            _event(9, "event_bus.publish", thread_id=main, main_id=main),
            _event(10, "repo.PipelineRepository.clear_preview_graph", thread_id=main, main_id=main),
        ]
        verdict = analyze_trail(events, main_loop_thread_id=main, candidate_async=True)
        assert verdict["passed"] is True
        assert verdict["disk_offload"]["left_main_loop"] is True
        assert verdict["bridge"]["run_async_caller_count"] == 0

    def test_candidate_fails_when_run_async_still_present(self) -> None:
        main = 1
        bridge = 2
        events = [
            _event(1, "complete_paper_pipeline.entry", thread_id=main, main_id=main),
            _event(2, "run_async.caller", thread_id=main, main_id=main),
            _event(
                3,
                "run_async.executor",
                thread_id=bridge,
                main_id=main,
                name="async-bridge-loop",
                bridge=True,
            ),
            _event(4, "graph.GraphStore.save", thread_id=3, main_id=main, name="asyncio_0", to_thread=True),
        ]
        verdict = analyze_trail(events, main_loop_thread_id=main, candidate_async=True)
        assert verdict["passed"] is False

    def test_baseline_pass_on_cross_thread_hop(self) -> None:
        main = 10
        bridge = 20
        events = [
            _event(1, "finalize.entry", thread_id=main, main_id=main),
            _event(2, "graph.GraphStore.save", thread_id=main, main_id=main),
            _event(3, "complete_paper_pipeline.entry", thread_id=main, main_id=main),
            _event(4, "run_async.caller", thread_id=main, main_id=main),
            _event(
                5,
                "run_async.executor",
                thread_id=bridge,
                main_id=main,
                name="async-bridge-loop",
                bridge=True,
            ),
            _event(
                6,
                "repo.PaperRepository.update_classification",
                thread_id=bridge,
                main_id=main,
                name="async-bridge-loop",
                bridge=True,
            ),
            _event(7, "event_bus.publish_sync", thread_id=main, main_id=main),
        ]
        verdict = analyze_trail(events, main_loop_thread_id=main, candidate_async=False)
        assert verdict["passed"] is True
        assert verdict["bridge"]["cross_thread_hop_detected"] is True
        assert verdict["disk_offload"]["stayed_on_main_loop"] is True


class TestTrailRecorder:
    def test_records_monotonic_seq_and_main_flag(self) -> None:
        recorder = TrailRecorder(main_loop_thread_id=threading_get_ident_safe())
        first = recorder.record("a")
        second = recorder.record("b")
        assert first.seq == 1
        assert second.seq == 2
        assert first.is_main_loop_thread is True


def threading_get_ident_safe() -> int:
    import threading

    return threading.get_ident()


class TestCompareAndRender:
    def test_compare_documents_story(self) -> None:
        main = 1
        baseline = {
            "verdict": analyze_trail(
                [
                    _event(1, "run_async.caller", thread_id=main, main_id=main),
                    _event(2, "run_async.executor", thread_id=9, main_id=main, name="async-bridge-loop", bridge=True),
                    _event(3, "graph.GraphStore.save", thread_id=main, main_id=main),
                ],
                main_loop_thread_id=main,
                candidate_async=False,
            ),
        }
        candidate = {
            "verdict": analyze_trail(
                [
                    _event(1, "complete_paper_pipeline.entry", thread_id=main, main_id=main),
                    _event(2, "repo.PaperRepository.update_classification", thread_id=main, main_id=main),
                    _event(3, "event_bus.publish", thread_id=main, main_id=main),
                    _event(4, "graph.GraphStore.save", thread_id=8, main_id=main, name="asyncio_0", to_thread=True),
                    _event(5, "finalize.entry", thread_id=main, main_id=main),
                    _event(6, "graph_persistence.save.entry", thread_id=main, main_id=main),
                    _event(7, "repo.PaperRepository.update_paths", thread_id=main, main_id=main),
                    _event(8, "repo.PaperRepository.update_graph_version", thread_id=main, main_id=main),
                    _event(9, "repo.PipelineRepository.save_status", thread_id=main, main_id=main),
                    _event(10, "repo.PipelineRepository.clear_preview_graph", thread_id=main, main_id=main),
                ],
                main_loop_thread_id=main,
                candidate_async=True,
            ),
        }
        comparison = compare_documents(baseline, candidate)
        assert comparison["story_matches_design"] is True

    def test_render_markdown_contains_trail_table(self) -> None:
        doc = {
            "label": "candidate",
            "commit": "abc",
            "verdict": analyze_trail(
                [_event(1, "finalize.entry", thread_id=1, main_id=1)],
                main_loop_thread_id=1,
                candidate_async=True,
            ),
            "trail": [_event(1, "finalize.entry", thread_id=1, main_id=1)],
        }
        md = render_trail_markdown(doc)
        assert "| seq | site |" in md
        assert "finalize.entry" in md
