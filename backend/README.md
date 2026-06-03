# ScholarGraph 后端（FastAPI + uv）

## 快速开始

在**仓库根目录**：

```bash
uv sync --group dev
cp .env.example .env
uv run python scripts/check_backend.py   # ruff + pytest（排除 red）
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

- 健康检查：`GET http://127.0.0.1:8000/api/v1/health`（含 `llm_mode` / `llm_connected`）
- Swagger：`http://127.0.0.1:8000/docs`

## 目录约定

```text
backend/
├── api/routes/      # HTTP 路由（health / papers / patrol）
├── services/        # Service 门面（API / workflow 只调此层）
│   ├── ingest_service.py
│   ├── agent_service.py
│   ├── graph_persistence_service.py
│   ├── paper_service.py
│   ├── patrol_service.py
│   ├── pipeline_status_service.py
│   └── paper_pipeline_scheduler.py   # 上传后 asyncio.create_task
├── schemas/         # Pydantic（与 OpenAPI 一致）
├── agents/          # BE-2 分类 / 抽取
├── ingest/          # BE-1 PDF 摄入（PyMuPDF）
├── graph/           # BE-3 存储 / 查询 / QA / LangGraph workflow
├── patrol/          # BE-4 巡检
├── prompts/         # BE-2 / BE-3 Prompt 文件
└── llm/             # 统一 LLM 客户端（mock / live）
```

## LLM 模式

| `LLM_MODE` | 行为 |
|------------|------|
| `mock`（默认） | `MockChat` 本地模板；无需 API Key |
| `live` | OpenAI 兼容网关（华为云 ModelArts MaaS 等）；需 `SCHOLARGRAPH_API_KEY` + `LLM_API_BASE_URL` |

配置见仓库根 `.env.example`；实现见 `backend/config.py`、`backend/llm/client.py`。

## 常用脚本（仓库根 `uv run`）

| 脚本 | 用途 |
|------|------|
| `scripts/check_backend.py` | PR 门禁：ruff + pytest |
| `scripts/run_d_gates.py` | D-01～D-10 合 develop 前 |
| `scripts/run_v1_ac_gates.py` | A～C 聚合 smoke |
| `scripts/run_cp4_rehearsal.py --seed` | CP4 24 步 API / 浏览器 rehearsal |
| `scripts/run_pipeline.py` | 单篇 PDF 流水线 CLI |
| `scripts/run_qa.py --smoke-m2` | 多尺度问答冒烟 |
| `scripts/run_patrol.py` | 双文巡检 CLI |

## 组员交付

业务逻辑只提交 **Service 函数**（见 `docs/v1/handoff-to-platform.md`），由 BE-L 在 `api/routes` 与 `graph/workflow.py` 中接线。
