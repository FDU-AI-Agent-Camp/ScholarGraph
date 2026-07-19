# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the async hot-path benchmark statistics, probe, and pool."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.benchmark_async_hotpath import (  # noqa: E402
    LoopLagProbe,
    classify_error,
    percentile,
    run_bounded,
    summarize_latencies,
)
from scripts.compare_async_hotpath_benchmarks import (  # noqa: E402
    assert_fingerprints_compatible,
    hierarchical_latency_bootstrap,
    paired_latency_ratio_ci,
    paired_ratio_ci,
    scalar_bootstrap_ci,
)

_TEST_RESAMPLES = 300


class TestPercentile:
    def test_median_of_even_count_interpolates(self) -> None:
        assert percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)

    def test_extremes_return_min_and_max(self) -> None:
        values = sorted([5.0, 1.0, 9.0, 3.0])
        assert percentile(values, 0) == 1.0
        assert percentile(values, 100) == 9.0

    def test_p99_of_uniform_sequence(self) -> None:
        values = [float(i) for i in range(1, 101)]
        assert percentile(values, 99) == pytest.approx(99.01)

    def test_empty_input_rejected(self) -> None:
        with pytest.raises(ValueError):
            percentile([], 50)

    def test_out_of_range_q_rejected(self) -> None:
        with pytest.raises(ValueError):
            percentile([1.0], 101)

    def test_summary_contains_expected_keys(self) -> None:
        summary = summarize_latencies([3.0, 1.0, 2.0])
        assert set(summary) == {"count", "p50_ms", "p95_ms", "p99_ms", "mean_ms", "min_ms", "max_ms"}
        assert summary["count"] == 3
        assert summary["p50_ms"] == 2.0


class TestClassifyError:
    def test_database_locked_gets_dedicated_bucket(self) -> None:
        error = RuntimeError("(sqlite3.OperationalError) database is locked")
        assert classify_error(error) == "RuntimeError:database_is_locked"

    def test_other_errors_use_type_name(self) -> None:
        assert classify_error(ValueError("boom")) == "ValueError"


@pytest.mark.asyncio
class TestRunBounded:
    async def test_concurrency_bound_is_enforced(self) -> None:
        active = 0
        peak = 0

        def make_op():
            async def op() -> None:
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

            return op

        results = await run_bounded([make_op() for _ in range(20)], concurrency=4)
        assert len(results) == 20
        assert all(result.ok for result in results)
        assert peak <= 4
        assert peak >= 2  # sanity: it actually ran concurrently

    async def test_errors_are_captured_not_raised(self) -> None:
        async def failing() -> None:
            raise ValueError("expected failure")

        results = await run_bounded([failing], concurrency=1)
        assert results[0].ok is False
        assert results[0].error_type == "ValueError"

    async def test_timeout_is_marked(self) -> None:
        async def slow() -> None:
            await asyncio.sleep(1.0)

        results = await run_bounded([slow], concurrency=1, op_timeout_s=0.05)
        assert results[0].ok is False
        assert results[0].error_type == "timeout"


@pytest.mark.asyncio
class TestLoopLagProbe:
    async def test_detects_synchronous_loop_block(self) -> None:
        probe = LoopLagProbe(interval_s=0.005)
        probe.start()
        await asyncio.sleep(0.05)
        time.sleep(0.08)  # deliberate ghost-sync style block on the loop thread
        await asyncio.sleep(0.05)
        samples = await probe.stop()
        assert samples, "probe should record wake-up samples"
        assert max(samples) >= 40.0, f"expected >=40ms lag spike, got max={max(samples):.1f}ms"

    async def test_quiet_loop_has_low_lag(self) -> None:
        probe = LoopLagProbe(interval_s=0.005)
        probe.start()
        await asyncio.sleep(0.2)
        samples = await probe.stop()
        assert samples
        # Windows timer granularity ~15ms; a quiet loop must stay well under the
        # deliberate-block threshold asserted above.
        assert sorted(samples)[len(samples) // 2] < 40.0


class TestBootstrap:
    def test_hierarchical_ci_is_deterministic_for_fixed_seed(self) -> None:
        reps = [[float(v) for v in range(rep, rep + 50)] for rep in (0, 5, 10)]
        first = hierarchical_latency_bootstrap(reps, n_resamples=_TEST_RESAMPLES, seed=7)
        second = hierarchical_latency_bootstrap(reps, n_resamples=_TEST_RESAMPLES, seed=7)
        assert first == second

    def test_hierarchical_ci_brackets_pooled_percentile(self) -> None:
        rng_values = [[float(v % 100) for v in range(rep * 17, rep * 17 + 200)] for rep in range(5)]
        intervals = hierarchical_latency_bootstrap(rng_values, n_resamples=_TEST_RESAMPLES, seed=3)
        pooled = sorted(v for rep in rng_values for v in rep)
        for metric, q in (("p50_ms", 50), ("p95_ms", 95), ("p99_ms", 99)):
            low, high = intervals[metric]
            assert low <= percentile(pooled, q) <= high

    def test_scalar_ci_brackets_mean(self) -> None:
        values = [10.0, 11.0, 9.5, 10.5, 10.2]
        low, high = scalar_bootstrap_ci(values, n_resamples=_TEST_RESAMPLES, seed=11)
        assert low <= sum(values) / len(values) <= high

    def test_paired_ratio_detects_clear_improvement(self) -> None:
        baseline = [10.0, 10.5, 9.8, 10.2, 10.1]
        candidate = [20.0, 21.0, 19.5, 20.4, 20.2]
        low, high = paired_ratio_ci(baseline, candidate, n_resamples=_TEST_RESAMPLES, seed=5)
        assert low > 1.5
        assert high < 2.5

    def test_paired_latency_ratio_detects_halved_p99(self) -> None:
        baseline = [[float(v) for v in range(100, 200)] for _ in range(4)]
        candidate = [[float(v) / 2 for v in range(100, 200)] for _ in range(4)]
        low, high = paired_latency_ratio_ci(
            baseline,
            candidate,
            "p99_ms",
            n_resamples=_TEST_RESAMPLES,
            seed=5,
        )
        assert low == pytest.approx(0.5, abs=0.05)
        assert high == pytest.approx(0.5, abs=0.05)


class TestFingerprintGuard:
    @staticmethod
    def _doc(label: str, operations: int) -> dict:
        return {
            "layer": "finalize",
            "concurrency": 10,
            "label": label,
            "workload_fingerprint": {
                "layer": "finalize",
                "concurrency": 10,
                "operations": operations,
                "warmup": 50,
                "seed": 1,
                "op_timeout_s": 120.0,
                "busy_timeout_s": 5,
                "heartbeat_interval_s": 0.005,
            },
            "env_fingerprint": {"python": "3.12", "platform": "test", "cpu_count": 8, "affinity": "core0"},
        }

    def test_mismatched_workload_is_refused(self) -> None:
        docs = [self._doc("baseline", 500), self._doc("candidate", 400)]
        with pytest.raises(SystemExit, match="fingerprint mismatch"):
            assert_fingerprints_compatible(docs, allow_mismatch=False)

    def test_allow_mismatch_downgrades_to_warning(self) -> None:
        docs = [self._doc("baseline", 500), self._doc("candidate", 400)]
        warnings = assert_fingerprints_compatible(docs, allow_mismatch=True)
        assert any("fingerprint mismatch" in warning for warning in warnings)

    def test_matching_workloads_pass(self) -> None:
        docs = [self._doc("baseline", 500), self._doc("candidate", 500)]
        assert assert_fingerprints_compatible(docs, allow_mismatch=False) == []
