# ScholarGraph 后端（FastAPI + uv）

## 快速开始

在**仓库根目录**：

```bash
uv sync
cp .env.example .env
uv run pytest
uv run uvicorn backend.main:app --reload
```

## 目录约定

```text
backend/
├── api/routes/      # HTTP 路由（BE-L 注册；组员勿私自加 Router）
├── services/        # 平台层编排，调用各 BE 模块
├── schemas/         # Pydantic（与 OpenAPI 一致）
├── agents/          # BE-2 分类 / 抽取
├── ingest/          # BE-1 PDF 摄入
├── graph/           # BE-3 存储 / 查询 / QA
├── patrol/          # BE-4 巡检
├── prompts/         # BE-2 Prompt 文件
└── llm/             # 统一 LLM 客户端
```

## 组员交付

业务逻辑只提交 **Service 函数**（见 `docs/v1/handoff-to-platform.md`），由 BE-L 在 `api/routes` 与 `graph/workflow.py` 中接线。
