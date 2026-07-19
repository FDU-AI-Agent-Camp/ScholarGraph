# 异步热路径基准：本地手工门禁

本仓库**不**把热路径压测挂进默认 CI / ChatOps。合并进主干前，在开发者本机手跑即可。

## 何时跑

动到以下路径时，合入 `main`/`develop` 前建议至少跑一遍 **quick** 矩阵 + 线程轨迹：

- `backend/services/`（尤其 finalize / reextract / delete / pipeline ops）
- `backend/events/`、`backend/repositories/async_bridge.py`
- `backend/graph/workflow.py`、`graph_persistence_service`

未触及异步热路径的纯文档 / 前端改动可跳过。

## 合并前推荐命令（仓库根目录）

```bash
# 1) 烟雾矩阵（双修订 worktree；几分钟级）
uv run python scripts/run_async_hotpath_benchmark_matrix.py \
  --quick \
  --layers finalize,http,diskio \
  --baseline-commit e847cc0 \
  --candidate-commit HEAD \
  --output-dir data/benchmarks/async-hotpath-local \
  --output-md data/benchmarks/async-hotpath-local/comparison.md \
  --no-affinity

# 2) 线程轨迹契约（当前 HEAD；秒～十秒级）
uv run python scripts/audit_async_thread_trail.py \
  --label candidate \
  --expect-commit HEAD \
  --output data/benchmarks/async-hotpath-local/thread-trail-candidate.json \
  --output-md data/benchmarks/async-hotpath-local/thread-trail-candidate.md
```

### 怎么算过关

| 检查 | 过关信号 |
|---|---|
| 线程轨迹 | `passed=True`，`run_async` 为 `0/0`，`GraphStore.save` 离开主 Loop |
| quick 矩阵 | 看 `comparison.md` 的 **loop-lag max 比值**；不要用绝对 QPS/P99 当硬闸 |
| SQLite | 若出现 `sqlite_write_bound` / `database is locked`，以 loop-lag 归因，勿据此否决 async 重构 |

架构级对撞（完整矩阵）仅在大改热路径时本地手跑，去掉 `--quick` 即可（耗时更长）。

## 保留的脚本资产

| 脚本 | 用途 |
|---|---|
| `scripts/benchmark_async_hotpath.py` | 单 cell runner（revision-portable） |
| `scripts/run_async_hotpath_benchmark_matrix.py` | 双修订矩阵编排 |
| `scripts/compare_async_hotpath_benchmarks.py` | 自举对比与 Markdown |
| `scripts/audit_async_thread_trail.py` | 线程/协程轨迹审计 |

历史结论与完整表：[`async-hotpath-benchmark.md`](async-hotpath-benchmark.md)、[`async-thread-trail-audit.md`](async-thread-trail-audit.md)。

## 为何不进 CI

共享云端 runner 有 noisy neighbor、时长与浅克隆问题；绝对数值也不可跨主机移植。本地 file SQLite 的 WAL 行为与开发环境一致，手跑成本最低、归因最清晰。

> 曾评估过 ChatOps `/benchmark` + 自托管机方案，已弃用；规格归档见 `docs/superpowers/specs/2026-07-19-async-hotpath-chatops-design.md`（标注 superseded）。
