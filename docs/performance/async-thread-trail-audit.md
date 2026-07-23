# Async Thread-Trail Audit Report

## Executive summary

对比提交：

| 角色 | Commit | 特征 |
|---|---|---|
| baseline | `e847cc0` | sync `complete_paper_pipeline` + `run_async` / `publish_sync` + 同步 `GraphStore.save` |
| candidate | `ac286f9` + generation-guard async 补丁 | await-only finalize；Repo / publish 留在主 Loop；`GraphStore.save` 走 `to_thread` |

验证手段：`scripts/audit_async_thread_trail.py` 在不改生产热路径语义的前提下，对下列站点动态插桩并记录 `threading.get_ident()` / 线程名：

- `finalize.entry` / `complete_paper_pipeline.entry`
- `repo.PaperRepository.update_*` / `repo.PipelineRepository.save_status`
- `event_bus.publish` / `event_bus.publish_sync`
- `run_async.caller` / `run_async.executor`
- `graph_persistence.save.entry` / `graph.GraphStore.save`

### 判定结果

| 指标 | baseline | candidate |
|---|---|---|
| 审计 verdict | **passed**（符合“重构前”画像） | **passed**（符合“重构后”画像） |
| loop-affinity 全在主 Loop | False（Repo 跑在 `async-bridge-loop`） | **True**（统一线程 id） |
| `run_async` caller/executor | **16 / 16** | **0 / 0** |
| `publish_sync` | 1 | 0 |
| `GraphStore.save` 离开主 Loop | False（与 caller 同线程同步写盘） | **True**（`asyncio_0` 线程池） |

### 结论

1. **重构前**：请求在 `finalize.entry` 进入主 Loop 线程后，每碰到一次 `run_async` 就跳到 `async-bridge-loop` 执行 Repo，再阻塞等回；`GraphStore.save` 仍钉在主线程上同步写盘。轨迹凌乱，跨线程往返清晰可见。  
2. **重构后**：`finalize → GraphPersistence.save.entry → complete_paper_pipeline → Repo 写入 → EventBus.publish` 的线程 ID **始终等于主事件循环线程**；**只有** `GraphStore.save` 平滑切换到 `asyncio.to_thread` 线程池（`asyncio_0`）。  
3. 审计过程中还揪出并清除了 finalize 热路径上最后的 generation-guard 幽灵桥接：`get_pipeline_generation_id` / `begin_pipeline_generation` / `invalidate_pipeline_generation` 与 `assert_pipeline_generation_writable` 已改为纯 `async def` 并向上 `await`。

### 如何复现

```bash
# 单元测试（判定器）
uv run pytest tests/scripts/test_audit_async_thread_trail.py -q

# candidate（当前工作树）
uv run python scripts/audit_async_thread_trail.py \
  --label candidate --expect-commit HEAD \
  --output data/benchmarks/async-thread-trail/candidate.json

# baseline（worktree @ e847cc0；先把脚本拷进 worktree）
python scripts/audit_async_thread_trail.py \
  --label baseline --expect-commit e847cc0 \
  --output data/benchmarks/async-thread-trail/baseline.json
```

完整时间序列见同目录：

- [candidate 轨迹](async-thread-trail-candidate.md)
- [baseline 轨迹](async-thread-trail-baseline.md)

---

## Candidate chronological trail (excerpt)

| seq | site | thread | main | to_thread |
|---|---|---|---|---|
| 1 | finalize.entry | MainThread | yes | no |
| 2 | graph_persistence.save.entry | MainThread | yes | no |
| 3 | graph.GraphStore.save | asyncio_0 | **no** | **yes** |
| 4 | complete_paper_pipeline.entry | MainThread | yes | no |
| 5–8 | Repo update_* / save_status | MainThread | yes | no |
| 9 | event_bus.publish | MainThread | yes | no |
| 10 | clear_preview_graph | MainThread | yes | no |

## Baseline chronological trail (excerpt)

| seq | site | thread | main | bridge |
|---|---|---|---|---|
| 1 | finalize.entry | MainThread | yes | no |
| 2–3 | run_async.caller → executor | Main → async-bridge-loop | hop | yes |
| 4–5 | GraphStore.save | MainThread（同步写盘） | yes | no |
| 6+ | complete_paper_pipeline + 反复 run_async | Main ↔ bridge | hop | yes |
| … | Repo update_* | async-bridge-loop | no | yes |
| … | publish_sync | MainThread | yes | no |
