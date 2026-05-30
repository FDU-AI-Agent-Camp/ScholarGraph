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

# seed 后额外跑 CLI 巡检冒烟
uv run python scripts/run_frontend_demo.py --smoke-patrol --mode lens_clash
```

等价手动 seed：

```bash
uv run python scripts/run_patrol.py --seed-demo-graphs
```

## 启动命令

**终端 1 — 后端（仓库根目录）**

```bash
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

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
- 备注：若后端 ingest 未就绪，可跳过上传，直接使用 seed 论文 `hss-001` / `hss-002`。

### 3. 论文详情（状态轮询）

| 场景 | URL | 验收 |
|------|-----|------|
| ready | `/papers/hss-001` | 元数据展示；状态面板为 ready |
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
- 备注：BE-3 真流未就绪时，后端可能仍返回 Mock SSE；前端壳与单测已覆盖事件解析。

### 6. 共同体巡检（Patrol）

- URL：`http://localhost:5173/patrol`
- 操作：
  1. `paper_ids` 输入：`hss-001,hss-002`（恰好 2 篇）
  2. `mode` 选择 `lens_clash` 或 `contradiction`
  3. 点击「运行巡检」
- 验收：
  - 展示 `mode`、`generated_at`、`paper_ids`；
  - 每条 insight 含 `title`、`summary`、`node_refs` 表格（paper_id / node_id / label）。
- 错误态：
  - `409 GRAPH_NOT_READY`：先执行 `run_patrol.py --seed-demo-graphs`
  - `422 PATROL_INSUFFICIENT_DATA`：切换 mode 或检查图谱节点类型

CLI 对照（可选）：

```bash
uv run python scripts/run_patrol.py --paper-ids hss-001,hss-002 --mode lens_clash
```

## 自动化门禁（开发侧）

```bash
# 前端 CI 等价
cd frontend && npm run check:ci

# 后端
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
uv pip install playwright   # 首次需安装
uv run playwright install chromium
uv run python scripts/run_cp4_rehearsal.py --seed
```

脚本覆盖：`GET /papers`、详情/状态（ready/processing/failed）、图谱、SSE 问答、`POST /patrol`、六页 SPA 渲染、详情页 QA 提问、巡检页运行。

退出码 0 表示 **24/24** 步骤通过。

## 相关文档

- 契约：`docs/api/openapi.yaml`、`docs/v1/api-contract.md`
- 巡检样本：`docs/v1/eval/patrol_samples.md`
- PR 清单：`docs/v1/pr-checklist.md`（前端 FE 小节）
