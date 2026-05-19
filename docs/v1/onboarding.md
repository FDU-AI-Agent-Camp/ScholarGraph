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

# 同步依赖（P0 合并后可用；若 pyproject 尚未合入，先跳过，等 BE-L 通知）
uv sync --group dev

# 环境变量
cp .env.example .env
# 编辑 .env，填入 SCHOLARGRAPH_API_KEY（向 BE-L 索取，勿提交 Git）
```

**冒烟测试**（P0 完成后）：

```bash
uv run pytest
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000/api/v1/health 或 http://127.0.0.1:8000/docs
```

**集成测试（调用真实 LLM）**：

```bash
uv run pytest -m integration
```

日常开发优先跑默认 pytest（Mock LLM，不耗额度）。

### 后端同学禁止

- 在仓库外全局 `pip install` 替代 `uv sync`
- 新建第二个 FastAPI `app` 或私自改 `backend/main.py`（交 BE-L 注册路由）
- 在代码 / PR 中提交 API Key
- 使用 `feature/be1/` 等非规范分支名

---

## 4. 前端（FE）

```bash
cd frontend
npm install
cp .env.development.example .env.development   # 若仓库已提供；否则新建：
# VITE_API_BASE_URL=http://localhost:8000

npm run dev
# 默认 http://localhost:5173
```

**Mock 开发**（后端未就绪时）：

1. 复制 [`docs/api/fixtures/`](../api/fixtures/) 到 `frontend/src/mocks/`
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

---

## 7. 常见问题

**Q：`uv sync` 失败 / 没有 `backend` 包？**  
A：P0 可能尚未合入 `develop`，先阅读文档与 Mock 开发，等 BE-L 通知。

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
