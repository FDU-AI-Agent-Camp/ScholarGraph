# M2 多尺度问答评测样本（A-09）

> 与 `docs/api/fixtures/graph-hss.json` 对齐；供 `scripts/run_qa.py --smoke-m2` 与 `tests/eval/test_m2_qa_multiscale.py` 使用。

## 前提

- `LLM_MODE=mock`（默认）：无需 API Key，MockChat 按问题尺度选择可复核 citation。
- 图谱须已写入 `GRAPH_DATA_DIR`（`--seed-demo-graph` 或 API seed）。

## Canonical 三类问题（hss-001 / HSS）

| 尺度 | 问题 | 期望 citation 节点类型 |
|------|------|------------------------|
| 摘要 | 这篇论文做了什么？请给出核心论点总览。 | `Thesis` |
| 细节 | 分论点如何支撑核心论点？ | `SubArgument`（或 `Thesis`） |
| 验证 | 核心论点通过哪些材料、经何种理论视角被论证？ | `AnalyticalLens` / `ObjectOrData` |

## CLI 冒烟

```bash
# 仓库根目录
uv run python scripts/run_qa.py --smoke-m2 --seed-demo-graph
```

退出码 `0` 表示三类问题均产生可复核 citation（`node_id` 存在于图谱且 `label` 一致）。

## pytest

```bash
uv run pytest tests/eval/test_m2_qa_multiscale.py -q
```

## Live 模式

接华为云 ModelArts MaaS 时将 `LLM_MODE=live` 并配置 Key；人工按上表抽检 citation 是否与图谱节点一致。  
异常路径（无效 Key、超时）见 `tests/integration/test_dod_e10_live_exceptions.py` 与 `scripts/probe_e10_live_exceptions.py`。
