# Patrol 评测样例（BE-4 · P5）

> 与微语料 `hss-001` / `hss-002` 对齐；供 `scripts/run_patrol.py` 本地冒烟与 `tests/patrol/test_patrol_corpus_smoke.py` 金标。

## 默认双文对（Lens Clash）

| paper_id | 语料标题（corpus） | 图谱 `AnalyticalLens` 标签（评测用） |
|----------|-------------------|--------------------------------------|
| `hss-001` | 再探夏尔巴人父系历史 | 分子考古与民族史视角 |
| `hss-002` | 当代中国电影的政治传播变迁研究 | 政治传播与电影叙事 |

两篇均为 **HSS** 范式；Lens Clash 应检出 **≥1 条** insight（视角标签不同）。

## 本地冒烟

在仓库根目录（需 `uv sync`）：

```bash
# 向 GRAPH_DATA_DIR 写入评测用图谱并运行 lens_clash
uv run python scripts/run_patrol.py --seed-demo-graphs

# 指定 paper_id 与输出
uv run python scripts/run_patrol.py --paper-ids hss-001,hss-002 --mode lens_clash --seed-demo-graphs
```

成功时 stdout 打印与 [`patrol-lens-clash.json`](../../api/fixtures/patrol-lens-clash.json) 同结构的 `PatrolReport` JSON（`mode` / `paper_ids` / `insights[]` / `generated_at`）。

## 自动化验收

```bash
uv run pytest tests/patrol/test_patrol_corpus_smoke.py -q
uv run pytest tests/patrol/ -q
```

## handoff §5 完成定义（PR 勾选）

- [x] 2 篇 HSS 语料可产出 ≥1 条 Lens Clash insight（`test_patrol_corpus_smoke` + 上表 lens）
- [x] `run_patrol(paper_ids, mode)` 与 [collaboration.md §4.4](../collaboration.md#44-be-4--patrol) 一致（`test_handoff_contract`）
- [ ] PR 描述请 BE-L 确认：**`POST /api/v1/patrol` → `PatrolService.run_patrol` → `backend.patrol.run_patrol`**（路由壳已存在，真逻辑已接入）

### BE-L 接线备忘

| HTTP | 调用链 |
|------|--------|
| `POST /api/v1/patrol` | `PatrolService.run_patrol(paper_ids, mode)` → `backend.patrol.run_patrol` → `GraphStore.load` |

图谱须已落盘至 `GRAPH_DATA_DIR`（`{paper_id}.json`）。开发态可用 `run_patrol.py --seed-demo-graphs` 写入评测图；生产路径由 BE-3 `GraphStore.save` 负责。
