# ChatOps `/benchmark` + Self-Hosted Runner — Design (SUPERSEDED)

Date: 2026-07-19  
Status: **superseded** — team chose local manual gate instead (see
[`docs/performance/async-hotpath-local-gate.md`](../../performance/async-hotpath-local-gate.md)).

The GitHub Actions workflow and `scripts/parse_benchmark_chatops.py` were removed.
Benchmark / audit / compare scripts remain for local use.

---

## Original goal (archived)

Expose the dual-revision async hot-path benchmark as an opt-in exclusive-machine
gate via PR comment `/benchmark` and `workflow_dispatch` on labels
`self-hosted` + `scholargraph-bench`.

That path is no longer maintained. Prefer:

```bash
uv run python scripts/run_async_hotpath_benchmark_matrix.py --quick
uv run python scripts/audit_async_thread_trail.py \
  --label candidate --expect-commit HEAD \
  --output data/benchmarks/async-hotpath-local/thread-trail-candidate.json
```
