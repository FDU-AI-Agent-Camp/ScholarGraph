# API 契约

V1 接口以 FastAPI 自动文档为准：

- 本地：`http://localhost:8000/docs`
- 字段命名与 `backend/schemas/` 中 Pydantic 模型一致，前端 AntV G6 直接消费 `GET /papers/{id}/graph` 的 `nodes` / `edges`。

交互模式（REST / SSE / 任务进度）见 [../v1/tech-stack.md](../v1/tech-stack.md)。

- 纲要：[openapi-v1-stub.yaml](./openapi-v1-stub.yaml)（BE-L 在 P0 后补全为完整 `openapi.yaml`）
- 字段与错误码以 [collaboration.md](../v1/collaboration.md) 为准
