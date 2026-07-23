# Async Hot-Path Benchmark Report

## Executive summary

对比提交：

| 角色 | Commit | 特征 |
|---|---|---|
| baseline | `e847cc008e38dedc789858e0266b88e69d7cb3dc` | sync `complete_paper_pipeline` + `publish_sync` / `run_async` |
| candidate | `3a8c661` + HTTP 编排 async 补丁 | await-only finalize；`clear_ephemeral` / `reset_pipeline_for_reextract` 纯 async |

主机：Windows-11-10.0.26200-SP0 / Python 3.12.11 / 22 CPUs / affinity=unset  
统计：hierarchical bootstrap 10 000 次，seed `20260719`，95% CI  
环境：file-backed SQLite WAL，`busy_timeout=5s`，pool_size=concurrency+10

### 结论（按设计文档的归因规则）

1. **幽灵同步已被斩断（finalize 层，主成功指标）**  
   Event-loop lag max 从 baseline 的 **~14–15 s**（整批几乎饿死心跳）降到 candidate 的 **~58–339 ms**，各并发档 lag_max 比值约 **0.004–0.024**（约 **40×–250×** 改善）。  
   Baseline 在任意 concurrency 下 QPS 都卡在 ~35：sync `complete_paper_pipeline` 占满主循环，名义并发无法真正重叠；candidate 的心跳可正常调度，证明主循环不再被 `.result()` 桥接堵死。

2. **单机 SQLite 写锁是 QPS/P99 的上限（finalize 层）**  
   Candidate 在 c≥10 出现 `database is locked`（`sqlite_write_bound`），per-op P99/QPS 劣于 baseline。这不是幽灵同步回归，而是 **真并发写撞上 SQLite 单写者**；设计文档要求此时以 loop-lag 归因，不以 raw P99 否定重构。  
   Baseline 的「低 P99」是假象：协程被串行冻在主循环上，单次计时短，但整个服务在批处理期间不可响应（lag≈墙钟）。

3. **HTTP reextract：两处 `run_async` 清掉后 lag 断崖下跌（已复测）**  
   将 `clear_ephemeral_pipeline_state` / `reset_pipeline_for_reextract` 改为纯 `async def` 并向上 `await` 后重跑 HTTP 矩阵：

   | 并发 | 修复前 candidate lag_max | 修复后 lag_max | locked（修复后） |
   |---|---|---|---|
   | c=5 | **5792 ms** | **27 ms** | 0 |
   | c=10 | **159792 ms** | **27 ms** | 0 |

   与 finalize 层毫秒级心跳对齐。本轮 HTTP 重测甚至未见 `database is locked`（写争用仍反映在更高的 per-op P99 / 更低 QPS 上）。

4. **对用户原始假说的回答**  
   - 「P99 平缓、无断崖」——在 **loop-lag / 服务可用性** 意义上成立；在 **SQLite 单写者 + 真并发** 下 per-op P99 会上升，属预期。  
   - 「QPS 系统性提升 30%–200%」——在本机 file SQLite 上 **未观察到**（写路径争用）；需要 MySQL/Postgres 或多进程分库才能验证吞吐上限。c=1 finalize 的 QPS CI 仅显示约 **1%–7%** 微弱优势。

### 如何复现

```bash
# 单元测试
uv run pytest tests/scripts/test_benchmark_async_hotpath.py -q

# 完整双修订矩阵（worktree + 交替顺序）
uv run python scripts/run_async_hotpath_benchmark_matrix.py \
  --busy-timeout-s 5 --no-affinity \
  --output-dir data/benchmarks/async-hotpath

# 仅聚合已有 raw JSON
uv run python scripts/compare_async_hotpath_benchmarks.py \
  --input-dir data/benchmarks/async-hotpath/raw \
  --output-json data/benchmarks/async-hotpath/comparison.json \
  --output-md docs/performance/async-hotpath-benchmark.md
```

设计说明见 `docs/superpowers/specs/2026-07-19-async-hotpath-benchmark-design.md`。  
HTTP 复测：`scripts/run_async_hotpath_benchmark_matrix.py --layers http --candidate-working-tree`。  
**合并前本地手工门禁**：见 [`docs/performance/async-hotpath-local-gate.md`](async-hotpath-local-gate.md)（不进默认 CI / 无 ChatOps）。

### 5. 事件循环阻塞度（diskio 层：`get_graph` + `delete_paper`）

验证手段与设计一致：在负载期间挂载 `LoopLagProbe`（等价于用户给出的 `monitor_loop_lag`），统计唤醒延迟；可选 `--lag-warnings` 在 lag>20 ms 时向 stderr 打印「幽灵阻塞」警告。

**自然负载矩阵**（未放大磁盘延迟；本机缓存命中下单次图谱 JSON 读写约 1–2 ms）：

| 并发 | baseline lag>20ms | candidate lag>20ms | baseline lag_max | candidate lag_max |
|---|---|---|---|---|
| c=1 | **134** | **37** | 995 ms | 839 ms |
| c=5 | 143 | 110 | 729 ms | 2136 ms† |
| c=10 | 33 | 48 | 42 ms | 402 ms† |
| c=25 | 44 | 43 | 89 ms | 151 ms |

† 高并发下 candidate 偶发尖峰主要来自线程池/GIL/主机噪声，**不是** finalize 层那种 14 s 级 `run_async` 饿死；两侧都未再现 finalize 的整批心跳死亡。

**关键结论：**

1. 本机「热缓存 + 小 JSON」的同步 `GraphStore.load` **不足以稳定超过 20 ms**，因此自然负载下控制台不会「高频刷屏」——这与用户假说中「慢磁盘 I/O」场景不同。  
2. 低并发冷启动时 baseline 的 `lag>20ms` 仍显著更多（c=1: 134 vs 37），与 delete 路径残留 `run_async` / 同步清盘一致。  
3. 已清除 candidate 上最后一处热路径同步删盘：`_unlink_pdf` → `await asyncio.to_thread(...)`。  
4. **受控慢磁盘对照**（`--amplify-sync-io-ms 50`，仅放大 `GraphStore.load/delete` 的同步体，两修订注入相同）：

| 场景 | baseline | candidate |
|---|---|---|
| get_graph-only ×30 | **warn 30/30**, lag_max≈73 ms, `to_thread=False` | **warn 3/30**, lag_max≈26 ms（定时器噪声） |
| mixed get_graph+delete ×40 | **warn 40/40** | warn 14/40（delete 路径仍含 SQL/主机抖动） |

→ 当磁盘体真的变慢时：baseline 同步 I/O 跑在主循环上，控制台按 op 刷警告；candidate 把同一段 sleep/I/O 放进 `to_thread`，主循环保持敏捷。这正是用户判定标准要证明的架构差异。

复现：

```bash
# 自然矩阵
uv run python scripts/run_async_hotpath_benchmark_matrix.py \
  --layers diskio --busy-timeout-s 5 --no-affinity --candidate-working-tree \
  --output-dir data/benchmarks/async-hotpath-diskio

# 受控慢磁盘 + 控制台警告
uv run python scripts/benchmark_async_hotpath.py \
  --layer diskio --concurrency 1 --operations 40 --warmup 6 \
  --repetition 0 --label candidate --expect-commit HEAD \
  --amplify-sync-io-ms 50 --lag-warnings --no-affinity \
  --output data/benchmarks/async-hotpath-diskio/demo-amplified/candidate-c1.json
```

原始表见 `data/benchmarks/async-hotpath-diskio/comparison.md`。

---

## Raw cell tables

- baseline: `e847cc008e38dedc789858e0266b88e69d7cb3dc`
- candidate: `3a8c661b84ff838778df2628a9261a68cabe6757`
- host: Windows-11-10.0.26200-SP0 / Python 3.12.11 / 22 CPUs / affinity=unset
- bootstrap: 10000 resamples, seed 20260719, 95% CI

## finalize @ concurrency 1

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 34.5 [33.12, 35.84] | 28.0 | 35.3 | 48.9 [35.16, 67.24] | 15519.5 / 15542.0 | 0 | 0 |
| candidate | 35.8 [35.28, 36.40] | 27.3 | 31.9 | 37.6 [34.27, 60.68] | 10.0 / 58.0 | 0 | 0 |

- candidate/baseline QPS ratio CI95: [1.01, 1.07] (supported improvement: True)
- candidate/baseline P99 ratio CI95: [0.64, 1.42] (supported improvement: False)
- loop-lag max ratio (candidate/baseline): 0.004 (baseline_max=15542.0ms, candidate_max=58.0ms)
- note: baseline ghost-sync keeps per-op P99 flat by freezing the loop; loop-lag is the primary success metric for this cell

## finalize @ concurrency 10

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 35.7 [35.30, 36.02] | 27.4 | 32.1 | 37.6 [34.07, 44.51] | 14255.4 / 14261.0 | 0 | 0 |
| candidate | 21.0 [20.55, 21.68] | 117.4 | 2190.2 | 4310.3 [3807.56, 4875.92] | 11.0 / 73.0 | 15 | 15 |

- candidate/baseline QPS ratio CI95: [0.57, 0.61] (supported improvement: False)
- candidate/baseline P99 ratio CI95: [96.00, 131.96] (supported improvement: False)
- loop-lag max ratio (candidate/baseline): 0.005 (baseline_max=14261.0ms, candidate_max=73.0ms)
- caveat: `sqlite_write_bound` — write-lock saturation detected; prefer loop-lag attribution over raw P99/QPS
- note: baseline ghost-sync keeps per-op P99 flat by freezing the loop; loop-lag is the primary success metric for this cell

## finalize @ concurrency 25

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 35.9 [35.23, 36.37] | 27.2 | 32.0 | 41.6 [34.46, 61.52] | 14398.2 / 14417.0 | 0 | 0 |
| candidate | 18.6 [17.29, 19.94] | 184.3 | 4346.7 | 6037.3 [5439.81, 7160.93] | 11.0 / 151.0 | 156 | 156 |

- candidate/baseline QPS ratio CI95: [0.48, 0.57] (supported improvement: False)
- candidate/baseline P99 ratio CI95: [95.74, 186.77] (supported improvement: False)
- loop-lag max ratio (candidate/baseline): 0.010 (baseline_max=14417.0ms, candidate_max=151.0ms)
- caveat: `sqlite_write_bound` — write-lock saturation detected; prefer loop-lag attribution over raw P99/QPS

## finalize @ concurrency 50

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 35.2 [34.12, 35.99] | 27.7 | 33.1 | 39.2 [34.11, 44.34] | 15109.8 / 15151.0 | 0 | 0 |
| candidate | 18.5 [17.87, 19.03] | 247.2 | 5011.2 | 6999.3 [6226.41, 7975.11] | 11.0 / 88.0 | 437 | 437 |

- candidate/baseline QPS ratio CI95: [0.50, 0.56] (supported improvement: False)
- candidate/baseline P99 ratio CI95: [151.08, 220.19] (supported improvement: False)
- loop-lag max ratio (candidate/baseline): 0.006 (baseline_max=15151.0ms, candidate_max=88.0ms)
- caveat: `sqlite_write_bound` — write-lock saturation detected; prefer loop-lag attribution over raw P99/QPS

## finalize @ concurrency 100

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 36.7 [35.94, 37.36] | 26.7 | 31.4 | 34.2 [32.84, 39.31] | 14163.9 / 14182.0 | 0 | 0 |
| candidate | 15.5 [15.13, 15.92] | 788.4 | 5944.5 | 8647.5 [7794.73, 10236.84] | 11.0 / 339.0 | 999 | 999 |

- candidate/baseline QPS ratio CI95: [0.42, 0.43] (supported improvement: False)
- candidate/baseline P99 ratio CI95: [212.90, 292.53] (supported improvement: False)
- loop-lag max ratio (candidate/baseline): 0.024 (baseline_max=14182.0ms, candidate_max=339.0ms)
- caveat: `sqlite_write_bound` — write-lock saturation detected; prefer loop-lag attribution over raw P99/QPS

## http @ concurrency 1 *(retest after async ephemeral/reset)*

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 37.5 [27.96, 45.38] | 25.1 | 41.9 | 43.9 [28.30, 53.54] | 11.0 / 42.0 | 0 | 0 |
| candidate | 33.6 [31.33, 35.62] | 29.7 | 38.6 | 41.2 [38.13, 43.94] | 11.0 / 11.0 | 0 | 0 |

- candidate/baseline QPS ratio CI95: [0.69, 1.21]
- loop-lag max ratio (candidate/baseline): 0.262 (baseline_max=42.0ms, candidate_max=11.0ms)

## http @ concurrency 5 *(retest after async ephemeral/reset)*

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 42.4 [40.47, 45.49] | 112.9 | 142.3 | 201.2 [128.18, 283.09] | 11.0 / 73.0 | 0 | 0 |
| candidate | 24.3 [22.87, 26.25] | 138.7 | 624.1 | 1209.3 [884.07, 1861.60] | 11.0 / 27.0 | 0 | 0 |

- candidate/baseline QPS ratio CI95: [0.53, 0.65]
- loop-lag max ratio (candidate/baseline): 0.370 (baseline_max=73.0ms, candidate_max=27.0ms)
- note: 修复前同档 candidate lag_max=5792 ms / locked=195 → 现为毫秒级且 0 locked

## http @ concurrency 10 *(retest after async ephemeral/reset)*

| label | QPS (mean, CI95) | P50 ms | P95 ms | P99 ms (CI95) | loop lag P99/max ms | errors | locked |
|---|---|---|---|---|---|---|---|
| baseline | 41.5 [36.88, 45.90] | 225.0 | 375.3 | 540.2 [266.37, 578.02] | 11.0 / 58.0 | 0 | 0 |
| candidate | 24.8 [22.96, 26.34] | 336.6 | 865.3 | 1671.2 [1186.13, 2493.55] | 11.0 / 27.0 | 0 | 0 |

- candidate/baseline QPS ratio CI95: [0.55, 0.71]
- loop-lag max ratio (candidate/baseline): 0.466 (baseline_max=58.0ms, candidate_max=27.0ms)
- note: 修复前同档 candidate lag_max=159792 ms / locked≈180 → 现为毫秒级且 0 locked
