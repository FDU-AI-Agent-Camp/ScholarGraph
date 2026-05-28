# Pull Request 检查清单

> 提 PR 时**复制下表到 PR 描述**，逐项勾选。  
> 目标分支：**`develop`**（勿直接 PR 到 `main`）。  
> 合并权限：**BE-L** Review 后合并。

---

## PR 元信息

| 项 | 填写 |
|----|------|
| 作者 / 角色 | FE / BE-L / BE-1 / BE-2 / BE-3 / BE-4 |
| 分支名 | 例：`feature/backend/agent/paradigm-classifier` |
| 关联任务 ID | 例：`P2-3`、`FE-8` |
| 是否改动对外 API 契约 | 是 / 否（若是，须已有 `[API RFC]` 并 @BE-L @FE） |
| 是否改动 Schema | 是 / 否（若是，须已有 `[Schema RFC]` 并 @相关人） |

---

## 全员必查

- [ ] 从最新 `develop` 拉取后创建分支，提交信息符合 [Conventional Commits](../../AGENTS.md)（scope：`frontend` / `platform` / `ingest` / `agent` / `graph-qa` / `patrol`）
- [ ] **未**向 `main` 直接 push
- [ ] **未**提交 `.env`、API Key、`API KEY.txt`、`data/corpus/*.pdf`
- [ ] PR 范围单一（一个模块或一条用户路径，避免「顺手改」无关文件）

---

## 前端（FE）

### 范围与契约

- [ ] 仅修改 `frontend/**`（或文档 `docs/design/`、`docs/api/` 中与 Mock/契约相关部分）
- [ ] 请求路径均为 `/api/v1/...`，与 [api-contract.md](./api-contract.md) 一致
- [ ] SSE 使用 **`POST .../papers/{id}/qa/stream`**，非 GET `EventSource`
- [ ] Mock / 测试数据与 [`docs/api/fixtures/`](../api/fixtures/) 或 [openapi.yaml](../api/openapi.yaml) 字段一致
- [ ] 未在浏览器或前端 env 中配置 LLM Key
- [ ] 若改对外 API：已有 **`[API RFC]`** Issue，并已 @BE-L @FE（见下方契约同步）

### CI 门禁（与 [frontend.yml](../../.github/workflows/frontend.yml) 一致）

在 `frontend/` 目录执行（**PR 前必跑**；合并前须 CI 绿）：

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run test
npm run build
```

- [ ] `npm run typecheck` 通过
- [ ] `npm run lint` 通过（业务代码经 `src/api/client.ts`，禁止 `src/` 裸 `axios`）
- [ ] `npm run test` 通过
- [ ] `npm run build` 通过

### 契约同步（仅当 PR 含 `docs/api/openapi.yaml` 或后端契约字段变更时勾选）

- [ ] 已按 RFC 更新 `docs/api/openapi.yaml` / `api-contract.md`（BE-L 侧或联调分支已合入）
- [ ] 已执行 `npm run generate:api-types` 并提交 `frontend/src/api/generated/schema.d.ts`
- [ ] 已检查 `frontend/src/api/types.ts` 薄封装与 SSE 手写类型（`qaStream.ts` 等）

**自测说明（必填一行）**：例：`npm ci && npm run typecheck && npm run lint && npm run test && npm run build`；`npm run dev` 打开 `/papers/hss-failed-001` 见失败态告警。

---

## 后端 · 平台（BE-L）

- [ ] `uv run pytest` 通过
- [ ] `docs/api/openapi.yaml` 与实现 `/docs` 同步（若改 API）
- [ ] CORS 含 `http://localhost:5173`
- [ ] 路由注册在 `backend/api/`，业务逻辑不堆在 `main.py`

**自测说明**：例：`uv run uvicorn backend.main:app --reload`，`GET /api/v1/health` 返回 200。

---

## 后端 · 摄入（BE-1）

- [ ] 仅修改 `backend/ingest/**`、`scripts/extract_text.py`、`tests/ingest/**`、语料相关文档
- [ ] `uv run pytest tests/ingest` 通过
- [ ] **未** `import backend.agents` 或调用 LLM
- [ ] 已实现/更新 `ingest_pdf()`，见 [handoff-to-platform.md](./handoff-to-platform.md)
- [ ] **未**自行添加 FastAPI 路由

**自测说明**：例：`uv run python scripts/extract_text.py`。

---

## 后端 · Agent（BE-2）

- [ ] 主要修改 `backend/schemas/`（graph/paradigm/validators）、`backend/agents/classifier.py`、`extractor.py`、`backend/prompts/`、`tests/agents/`
- [ ] `uv run pytest tests/agents tests/test_schema.py` 通过（路径按实际）
- [ ] 分类输出符合 [ParadigmClassification](./api-contract.md#1-范式分类-jsonparadigmclassification)
- [ ] **未**修改 `backend/llm/client.py` 内部（除非与 BE-L 事先约定）
- [ ] **未**自行添加 FastAPI 路由

**自测说明**：例：`uv run python scripts/run_classifier.py`，微语料 3/3。

---

## 后端 · 图谱与问答（BE-3）

- [ ] 主要修改 `backend/graph/store.py`、`query.py`、`backend/agents/qa.py`、`backend/prompts/qa.md`、`tests/graph/`
- [ ] `uv run pytest tests/graph` 通过
- [ ] `to_g6()` 输出与 [graph-hss.json](../api/fixtures/graph-hss.json) 结构一致
- [ ] `qa_stream()` 事件含 `message` / `citation` / `done` / `error`
- [ ] **未**自行添加 FastAPI 路由（SSE 壳由 BE-L 接）

**自测说明**：例：`uv run python scripts/run_qa.py`（或模块内脚本）。

---

## 后端 · 巡检（BE-4）

- [ ] 主要修改 `backend/patrol/**`、`backend/schemas/patrol.py`、`tests/patrol/`
- [ ] `uv run pytest tests/patrol` 通过
- [ ] 仅通过 `GraphStore.load` 读图，**未**调用 `extract`
- [ ] `run_patrol()` 返回结构与 [patrol-lens-clash.json](../api/fixtures/patrol-lens-clash.json) 一致
- [ ] **未**自行添加 FastAPI 路由

**自测说明**：例：`uv run python scripts/run_patrol.py`。

---

## BE-L Review 关注点（供审阅者勾选）

- [ ] 符合 [目录写权限](./collaboration.md#5-目录写权限)
- [ ] Service 接口与 [handoff-to-platform.md](./handoff-to-platform.md) 一致，便于接入 `workflow`
- [ ] 无重复 LLM 客户端、无硬编码密钥
- [ ] 若改 `openapi.yaml`，已通知 FE 更新类型/Mock

---

## 合并后（BE-L）

- [ ] 已更新 [任务看板](./work-assignment.md#6-任务看板) 对应项
- [ ] 里程碑 CP0～CP4 节点评估是否达成
