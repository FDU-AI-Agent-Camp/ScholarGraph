# 浏览器全链路演示路径（FE-11）

本文档描述 ScholarGraph V1 前端答辩 / 联调时的**标准浏览器路径**，与 `progress.md` §6 一致。

## 前置条件

| 项 | 要求 |
|----|------|
| 后端 | 仓库根目录 `uv sync --group dev` 后启动 FastAPI |
| 前端 | `frontend/` 下 `npm install` 后 `npm run dev` |
| 巡检数据 | 已 seed 评测图谱（见下方一键脚本） |
| 代理 | Vite 将 `/api` 代理到 `http://127.0.0.1:8000` |

## 一键准备（推荐）

在**仓库根目录**执行：

```bash
uv run python scripts/run_frontend_demo.py
```

可选：

```bash
# 仅打印 URL，不 seed
uv run python scripts/run_frontend_demo.py --skip-seed

# seed 后额外跑 CLI 巡检冒烟（单模式）
uv run python scripts/run_frontend_demo.py --smoke-patrol --mode method_overlap

# seed 后四模式依次冒烟
uv run python scripts/run_frontend_demo.py --smoke-all-patrol
```

默认 seed 会写入 **HSS + STEM** 图谱（`hss-001/002` + `stem-001/002`），开箱即可试 V2 `method_overlap` / `claim_evolution`。

等价手动 seed：

```bash
uv run python scripts/run_patrol.py --seed-demo-graphs
```

## 启动命令

**终端 1 — 后端（仓库根目录，Demo Profile 必开）**

```bash
export APP_PROFILE=demo
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell：

```powershell
$env:APP_PROFILE='demo'
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

`APP_PROFILE=demo` 会叠加加载 `.env.demo`，其中 **硬性开启** `RERANKER_ENABLED=true` 与 `RERANKER_MODEL=bge-reranker-v2-m3`。若 Reranker 未配置或握手失败，应用将在启动期 Fail-Fast 阻断。

**终端 2 — 前端**

```bash
cd frontend
npm run dev
```

默认前端地址：`http://localhost:5173`

## 演示路径（Home → 上传 → 详情 → 图谱 → 问答 → 巡检）

按顺序在浏览器中完成以下步骤，用于 CP4 端到端答辩。

### 1. 工作台（Home）

- URL：`http://localhost:5173/`
- 验收：导航栏可见「文献库」「巡检」等入口；可点击进入各模块。

### 2. 文献库 + 上传

- URL：`http://localhost:5173/papers`
- 操作：在页面内嵌上传区选择 PDF，提交 `POST /papers`。
- 验收：列表刷新或出现新论文；失败时展示 `INGEST_FAILED` 等错误提示。
- 上传成功后详情页自动轮询 `GET .../status`，直至 `ready` / `ready_with_warnings` / `failed`（支持暂停/继续刷新）。
- 亦可跳过上传，直接使用 seed 论文 `hss-001` / `hss-002`。

### 3. 论文详情（状态轮询）

| 场景 | URL | 验收 |
|------|-----|------|
| ready | `/papers/hss-001` | 元数据展示；状态面板为 ready |
| ready_with_warnings | 使用质量门控触发的论文 | 元数据展示；状态面板为 ready_with_warnings，画布带黄色警示边框 |
| indexing | 真上传流水线（finalize 后） | `BadgeStatus` 显示「索引中」；**非终态**，继续轮询至 `ready` / `ready_with_warnings`；此阶段无 preview 时开图谱页可能 409 |
| processing | `/papers/hss-002` | 进度条 / stage 轮询 |
| failed | `/papers/hss-failed-001` | 红色告警：`LLM_JSON_INVALID`、`failed_during: classifying` |

### 4. 知识图谱（G6）

- URL：`http://localhost:5173/papers/hss-001/graph`
- 带高亮：`/papers/hss-001/graph?node=n_lens_a`
- 验收：dagre 布局渲染节点与边；路由 `?node=` 高亮对应节点。
- 409：若图谱未就绪，页面提示 `GRAPH_NOT_READY`（需 seed 或 BE-2 真图）。

### 5. 问答（SSE，详情页内嵌）

- URL：`http://localhost:5173/papers/hss-001`（页面下方问答区）
- 操作：输入问题，发送 `POST /papers/{id}/qa/stream`。
- 验收：
  - 流式 `message` 增量展示答案；
  - `citation` 事件生成可点选标签；
  - 点选 citation 后内嵌 compact 图谱高亮，可跳转全屏图谱页 `?node=`。
- `LLM_MODE=mock` 时返回本地模板；`live` 时走真实 MaaS。流内异常见 SSE `error` 事件 `QA_STREAM_ERROR`。

### 6. 共同体巡检（Patrol）

- URL：`http://localhost:5173/patrol`
- 操作：
  1. `paper_ids` 输入：`hss-001,hss-002`（恰好 2 篇）
  2. `mode` 选择四模式之一（`lens_clash` / `contradiction` / `method_overlap` / `claim_evolution`）
  3. V2 模式使用 `stem-001,stem-002`（默认 seed 已包含 STEM 语料）
  4. 点击「运行巡检」
- 验收：
  - 展示 `mode`、`generated_at`、`paper_ids`；
  - 每条 insight 含 `title`、`summary`、`structured_points`（V2）与 `node_refs` 表格。
- 错误态：
  - `409 GRAPH_NOT_READY`：先执行 `run_patrol.py --seed-demo-graphs`
  - `422 PATROL_INSUFFICIENT_DATA`：切换 mode 或检查图谱节点类型
- **`claim_evolution` 演示（live 模式）**：确认 `GET /api/v1/health` 中 `patrol_claim_rq_funnel_enabled=true`；否则需在 `.env` 设置 `RERANKER_ENABLED=true` 与 `RERANKER_MODEL`（见 [onboarding §3](../onboarding.md)）

CLI 对照（可选）：

```bash
uv run python scripts/run_patrol.py --paper-ids hss-001,hss-002 --mode lens_clash
uv run python scripts/run_patrol.py --seed-stem-demo
uv run python scripts/run_patrol.py --paper-ids stem-001,stem-002 --mode method_overlap
```

## 自动化门禁（开发侧）

```bash
# 代码基座 D-01～D-10（仓库根目录）
uv run python scripts/run_d_gates.py
uv run python scripts/run_d_gates.py --skip-frontend   # 仅后端 + Git 治理

# 前端 CI 等价
cd frontend && npm run check:ci

# 后端（与 CI backend.yml 一致）
uv run python scripts/check_backend.py
```

## CP4 端到端 rehearsal（自动化）

前后端已启动时，在**仓库根目录**执行：

```bash
# 终端 1
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# 终端 2
cd frontend && npm run dev

# 终端 3 — 全链路联调（API + Vite 代理 + Playwright 浏览器）
uv sync --group e2e
uv run playwright install chromium
uv run python scripts/run_cp4_rehearsal.py --seed

# 分段探针
uv run python scripts/run_cp4_rehearsal.py --seed --api-only      # C-05 仅后端 API（8 步）
uv run python scripts/run_cp4_rehearsal.py --skip-browser         # C-05 + C-06（16 步）

# C-09：合 develop / 答辩前复跑 A～C（含 check_backend + check:ci + CLI 冒烟）
uv run python scripts/run_v1_ac_gates.py
uv run python scripts/run_v1_ac_gates.py --with-cp4-api           # 额外 C-05（需 :8000）
```

脚本覆盖：`GET /papers`、详情/状态（ready/processing/failed）、图谱、SSE 问答、`POST /patrol`、六页 SPA 渲染、详情页 QA 提问、巡检页运行。

退出码 0 表示 **24/24** 步骤通过（`--api-only` 为 8/8，`--skip-browser` 为 16/16）。

## C-08 人工答辩彩排

按上文 **§1～§5 演示路径** 逐项走读；自动化无法替代口播与临场切换。建议答辩前：

1. 执行 `run_frontend_demo.py` 打印 URL 清单
2. 跑通 `run_cp4_rehearsal.py --seed`（24/24）
3. 人工走一遍 Home → Papers → Detail QA → Graph ?node= → Patrol

## 相关文档

- 契约：`docs/api/openapi.yaml`、`docs/v1/api-contract.md`
- 巡检样本：`docs/v1/eval/patrol_samples.md`
- PR 清单：`docs/v1/pr-checklist.md`（前端 FE 小节）
