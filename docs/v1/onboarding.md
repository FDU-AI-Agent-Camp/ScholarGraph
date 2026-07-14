# V1 新成员上手指南

> 第一天按本页操作；分工见 [work-assignment.md](./work-assignment.md)，对接见 [api-contract.md](./api-contract.md)。  
> **阻塞问题**：群内 @BE-L（负责人）。

---

## 1. 克隆与分支

```bash
git clone git@github.com:FDU-AI-Agent-Camp/ScholarGraph.git
cd ScholarGraph
git checkout develop
# 若无 develop，从 main 拉取最新后：git checkout -b develop
```

个人分支命名见 [任务分工 §3.2](./work-assignment.md#32-命名格式统一)：

```text
feature/frontend/{简述}
feature/backend/{工作类型}/{简述}
```

---

## 2. 环境要求

| 工具 | 版本建议 | 谁需要 |
|------|----------|--------|
| Git | 2.40+ | 全员 |
| Python | 3.11+ | 后端全员 |
| [uv](https://docs.astral.sh/uv/) | 最新稳定版 | 后端全员 |
| Node.js | 20 LTS+ | FE |
| npm | 10+ | FE |

---

## 3. 后端（BE-L、BE-1～4）

在**仓库根目录**执行：

```bash
# 安装 uv 后
uv --version

# 同步依赖（含开发组 pytest / ruff）
uv sync

# 环境变量
cp .env.example .env
# 默认 APP_PROFILE=ci + LLM_MODE=mock，无需 Key 即可联调
# 验收演示：export APP_PROFILE=demo（叠加 .env.demo，RERANKER 硬性开启）
# 生产部署：export APP_PROFILE=prod（叠加 .env.prod）
# 接华为云 ModelArts MaaS：LLM_MODE=live，填 SCHOLARGRAPH_API_KEY + LLM_API_BASE_URL
# 模型名见 .env.example（默认 DeepSeek-V3-64K / Qwen3-32B-64K，与 backend/config.py 一致）

**LLM 能力点开关**（live 模式下独立生效；`LLM_MODE=mock` 时不调云端）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `CLASSIFIER_LLM_ENABLED` | `true` | 范式分类 LLM；`false` → 启发式 + `classifier_heuristic_fallback` |
| `CLASSIFIER_HEURISTIC_FALLBACK` | `true` | 分类 LLM 失败是否降级（`false` 可致流水线 failed） |
| `EXTRACT_LLM_ENABLED` | `true` | 图谱抽取 LLM；`false` → 启发式 + `extract_heuristic_fallback` |
| `EXTRACT_HEURISTIC_FALLBACK` | `true` | 抽取 LLM 失败是否降级 |
| `EXTRACT_MAX_INPUT_CHARS` | `20000` | 送入抽取 LLM 的全文上限；超过且启用 chunked 时进入两阶段分块抽取 |
| `EXTRACT_CHUNK_OVERLAP_RATIO` | `0.12` | 长文分块滑动窗口重叠比例（0.0 表示无重叠） |
| `EXTRACT_MAX_GENERIC_EDGE_RATIO` | `1.0` | 允许的最大通用兜底边比例（如 `RELATES_TO`）；调低可强制 LLM 发明具体关系动词 |

分类与抽取**互不影响**：分类准确仍可能出现抽取 fallback。排查：后端日志 `extract_llm attempt failed` / `extract_llm_fallback`（含 `reason`、`elapsed_ms`）。

**pytest 与本地 `.env`**：CI 默认 `tests/conftest.py` 设 `SCHOLARGRAPH_IGNORE_DOTENV=1`；本地全量门禁可 `$env:SCHOLARGRAPH_IGNORE_DOTENV="1"` 避免 `.env` 中 `LLM_MODE=live` 污染默认单测。

**冒烟测试**（P0 完成后）：

```bash
uv run pytest
export APP_PROFILE=ci
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000/api/v1/health 或 http://127.0.0.1:8000/docs
```

**集成测试（调用真实 LLM）**：

```bash
uv run pytest -m integration
# E-10 live 异常路径（无效 Key / 超时，需 LLM_MODE=live 与真实 .env）
uv run pytest tests/integration/test_dod_e10_live_exceptions.py -m live_e10 -q
uv run python scripts/probe_e10_live_exceptions.py
```

日常开发优先跑默认 pytest（Mock LLM，不耗额度）。

**Patrol `claim_evolution` 与 Reranker（live / 演示必读）**：

| 变量 | 演示推荐 | 说明 |
|------|----------|------|
| `RERANKER_ENABLED` | `true` | `false` 时 claim_evolution **不走**粗筛 0.42 + 精排漏斗，回退严格双塔（中文 0.75 / 英文 0.55），易出现 `INSUFFICIENT_DATA` |
| `RERANKER_MODEL` | 必填 | 如 `bge-reranker-v2-m3`；空则精排无法调用 |
| `PATROL_CLAIM_RQ_COARSE_THRESHOLD` | `0.42`（默认） | 漏斗阶段 1，仅 `RERANKER_ENABLED=true` 时生效 |
| `PATROL_RERANK_THRESHOLD` | `0.60`（默认） | 漏斗阶段 2 硬卡点 |

启动后查看 `GET /api/v1/health` 的 `patrol_claim_rq_funnel_enabled` / `patrol_note`；live 模式配置不当时日志会输出 `patrol_config:` 警告。

### 后端同学禁止

- 在仓库外全局 `pip install` 替代 `uv sync`
- 新建第二个 FastAPI `app` 或私自改 `backend/main.py`（交 BE-L 注册路由）
- 在代码 / PR 中提交 API Key
- 使用 `feature/be1/` 等非规范分支名

---

## 4. 前端（FE）

`frontend/` 骨架已包含 Vue 3 + Vite + Pinia + Element Plus + G6；详见 [frontend/README.md](../../frontend/README.md)。

```bash
cd frontend
npm install
cp .env.development.example .env.development
# 推荐留空 VITE_API_BASE_URL，走 Vite /api 代理；直连后端时设为 http://localhost:8000
# VITE_USE_MOCK=false  # 默认关闭前端 Mock，走真实 API

npm run dev
# 默认 http://localhost:5173
```

**Mock 开发**（后端未就绪时）：

1. 使用 [`docs/api/fixtures/`](../api/fixtures/)（后端 Mock 同源）；可选 `import '@/mocks'` 见 [`frontend/src/mocks/README.md`](../../frontend/src/mocks/README.md)
2. 或用 MSW 拦截 `/api/v1/*`，响应体与 fixtures 一致
3. 类型生成（OpenAPI 就绪后）：

```bash
npx openapi-typescript ../docs/api/openapi.yaml -o src/types/api.ts
```

### 前端同学禁止

- 在浏览器配置 LLM API Key
- 修改 `backend/`、`pyproject.toml`
- 自建与 [api-contract.md](./api-contract.md) 不一致的 JSON 字段名

---

## 5. 按角色阅读顺序

| 角色 | 第 1 天阅读 |
|------|-------------|
| **FE** | 本页 → [tech-stack.md](./tech-stack.md) → [api-contract.md](./api-contract.md) → [work-assignment §4.1](./work-assignment.md#41-fe--前端) |
| **BE-L** | 本页 → [collaboration.md](./collaboration.md) → 推进 P0 |
| **BE-1** | 本页 → [handoff-to-platform.md](./handoff-to-platform.md) → [work-assignment §4.3](./work-assignment.md#43-be-1--摄入) |
| **BE-2** | 本页 → handoff → [api-contract §1](./api-contract.md#1-范式分类-jsonparadigmclassification) → work-assignment §4.4 |
| **BE-3** | 本页 → handoff → [fixtures/graph-hss.json](../api/fixtures/graph-hss.json) → work-assignment §4.5 |
| **BE-4** | 本页 → handoff → [fixtures/patrol-lens-clash.json](../api/fixtures/patrol-lens-clash.json) → work-assignment §4.6 |

---

## 6. 日常协作节奏

| 事项 | 约定 |
|------|------|
| 每日 | 在本模块分支提交；结束前 push |
| PR | 目标分支 **`develop`**；描述用 [pr-checklist.md](./pr-checklist.md) |
| 周会 | 30min，过 [任务看板](./work-assignment.md#6-任务看板) |
| 契约变更 | Issue `[API RFC]` / `[Schema RFC]`，@BE-L + 相关人 |

**门禁脚本**（仓库根目录，与 CI 对齐）：

```bash
uv run python scripts/check_backend.py          # 每个后端 PR
uv run python scripts/run_d_gates.py            # 合 develop 前（D-01～D-10）
cd frontend && npm run check:ci                 # 每个前端 PR（= CI frontend.yml）
uv run python scripts/run_v1_ac_gates.py        # 答辩前 A～C 聚合
uv run python scripts/run_cp4_rehearsal.py --seed   # CP4 24 步（需前后端 dev）
```

---


## 7. 常见问题

**Q：`uv sync` 失败 / 找不到模块？**  
A：确认在仓库根目录执行；Python 3.11+ 与 uv 已安装。仍失败时在群内 @BE-L。

**Q：前端请求 404 / CORS？**  
A：确认后端 `uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000` 已启动；前端 `VITE_API_BASE_URL` 留空走 Vite 代理，或设为 `http://localhost:8000` 直连。

**Q：我能自己加一条 API 路由方便自测吗？**  
A：不要。模块内写 Service + 脚本自测；路由由 BE-L 在汇总 PR 中注册。

**Q：分类接口是 `/classification` 吗？**  
A：不是。分类结果在 `GET /api/v1/papers/{paper_id}` 的 `classification` 字段内嵌。

**Q：问答 SSE 用 GET 吗？**  
A：否。仅 `POST /api/v1/papers/{paper_id}/qa/stream` + JSON body。

---

## 8. 相关文档

- [PR 检查清单](./pr-checklist.md)
- [模块交付 BE-L](./handoff-to-platform.md)
- [协作规范](./collaboration.md)
