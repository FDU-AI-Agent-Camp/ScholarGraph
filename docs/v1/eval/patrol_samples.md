# Patrol 评测样例（四模式 · V1 + V2）

> 供 `scripts/run_patrol.py` 本地冒烟与 `tests/patrol/test_patrol_corpus_smoke.py` 金标。  
> **四模式**：`lens_clash` / `contradiction`（V1 · HSS）+ `method_overlap` / `claim_evolution`（V2 · STEM）。  
> V2 完整契约见 [`docs/v2/rag-requirements.md` §5](../../v2/rag-requirements.md)。

| 模式 | 适用语料 | 典型 paper_ids | 主要节点 |
|------|----------|----------------|----------|
| `lens_clash` | HSS | `hss-001`,`hss-002` | `AnalyticalLens` |
| `contradiction` | HSS（亦可 STEM） | `hss-001`,`hss-002` | `Thesis` + `SubArgument` |
| `method_overlap` | STEM | `stem-001`,`stem-002` | `Method` / `Dataset` |
| `claim_evolution` | STEM（亦可跨范式） | `stem-001`,`stem-002` | `ResearchQuestion` / `Thesis` + `Claim` |

CLI 默认仍为 **V1**：`--mode lens_clash` + `hss-001,hss-002`（兼容原冒烟路径）。跑 V2 时请显式传 STEM ids 与 mode。

## V1 — Lens Clash（默认双文对）

| paper_id | 语料标题（corpus） | 图谱 `AnalyticalLens` 标签（评测用） |
|----------|-------------------|--------------------------------------|
| `hss-001` | 再探夏尔巴人父系历史 | 分子考古与民族史视角 |
| `hss-002` | 当代中国电影的政治传播变迁研究 | 政治传播与电影叙事 |

两篇均为 **HSS** 范式；Lens Clash 应检出 **≥1 条** insight（视角标签不同）。

```bash
uv run python scripts/run_patrol.py --seed-demo-graphs
# 等价于默认 mode=lens_clash + hss-001,hss-002
```

## V1 — Contradiction（Thesis / SubArgument）

| paper_id | 评测用 `Thesis` 标签 |
|----------|---------------------|
| `hss-001` | 夏尔巴父系源流具有多元融合特征 |
| `hss-002` | 电影政治传播强化主流意识形态建构 |

```bash
uv run python scripts/run_patrol.py --paper-ids hss-001,hss-002 --mode contradiction --seed-demo-graphs
```

摘要优先由 **LLM 结构化输出**（`PatrolSummaryOutput` JSON Schema）生成；无 Key 或调用失败时回退规则模板（见 `backend/patrol/llm_summary.py`）。

## V2 — method_overlap / claim_evolution

STEM 演示语料 `stem-001` / `stem-002`（PCA 同义词对 + 对齐 RQ）已包含在 `--seed-demo-graphs` 中；亦可单独写入：

```bash
uv run python scripts/run_patrol.py --seed-stem-demo
uv run python scripts/run_patrol.py --paper-ids stem-001,stem-002 --mode method_overlap
uv run python scripts/run_patrol.py --paper-ids stem-001,stem-002 --mode claim_evolution
```

`claim_evolution` live 演示需 `RERANKER_ENABLED=true` 与 `RERANKER_MODEL`；见 `GET /api/v1/health` 的 `patrol_claim_rq_funnel_enabled`。  
模式语义、`structured_points` 字段与验收条目见 [rag-requirements.md §5 Phase 3](../../v2/rag-requirements.md)。

API fixture：[`patrol-method-overlap.json`](../../api/fixtures/patrol-method-overlap.json)、[`patrol-claim-evolution.json`](../../api/fixtures/patrol-claim-evolution.json)、[`patrol-method-overlap-insufficient.json`](../../api/fixtures/patrol-method-overlap-insufficient.json)（通道 B `insufficient_data`）。

## 本地冒烟汇总

在仓库根目录（需 `uv sync`）：

```bash
# HSS + STEM 评测图谱 + 默认 lens_clash
uv run python scripts/run_patrol.py --seed-demo-graphs

# 仅 seed HSS / STEM
uv run python scripts/run_patrol.py --seed-hss-demo
uv run python scripts/run_patrol.py --seed-stem-demo

# 指定 paper_id 与模式
uv run python scripts/run_patrol.py --paper-ids hss-001,hss-002 --mode lens_clash --seed-demo-graphs
uv run python scripts/run_patrol.py --paper-ids stem-001,stem-002 --mode method_overlap --seed-stem-demo
```

成功时 stdout 打印与 OpenAPI `PatrolReport` 同结构的 JSON（`mode` / `paper_ids` / `insights[]` / `generated_at`）。  
V1 Lens Clash 形态参考 [`patrol-lens-clash.json`](../../api/fixtures/patrol-lens-clash.json)。

## 自动化验收

```bash
uv run pytest tests/patrol/test_patrol_corpus_smoke.py -q
uv run pytest tests/patrol/ -q
uv run pytest tests/test_run_patrol_script.py -q
```

## handoff §5 完成定义（PR 勾选）

- [x] 2 篇 HSS 语料可产出 ≥1 条 Lens Clash insight（`test_patrol_corpus_smoke` + 上表 lens）
- [x] `run_patrol(paper_ids, mode)` 与 [collaboration.md §4.4](../collaboration.md#44-be-4--patrol) 一致（`test_handoff_contract`）
- [x] 四模式 CLI / 文档对齐（`--help` 列出全部 mode；本文含 V2 与 §5 链接）
- [ ] PR 描述请 BE-L 确认：**`POST /api/v1/patrol` → `PatrolService.run_patrol` → `backend.patrol.run_patrol`**（路由壳已存在，真逻辑已接入）

### BE-L 接线备忘

| HTTP | 调用链 |
|------|--------|
| `POST /api/v1/patrol` | `PatrolService.run_patrol(paper_ids, mode)` → `backend.patrol.run_patrol` → `GraphStore.load` |

图谱须已落盘至 `GRAPH_DATA_DIR`（`{paper_id}.json`）。开发态可用 `run_patrol.py --seed-demo-graphs` 写入评测图；生产路径由 BE-3 `GraphStore.save` 负责。
