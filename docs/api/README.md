# API 契约

V1 对外接口已冻结，以本目录与协作文档为准。

| 资源 | 说明 |
|------|------|
| [openapi.yaml](./openapi.yaml) | OpenAPI 3.1，供 `openapi-typescript` / Swagger |
| [fixtures/](./fixtures/) | 标准 Mock JSON，FE 可拷至 `frontend/src/mocks/` |
| 运行时文档 | 实现后 `http://localhost:8000/docs`（须与 `openapi.yaml` 同步） |

人文档：

- [协作规范 §3](../v1/collaboration.md#3-对外-http-apiv10已冻结)
- [API 契约详表](../v1/api-contract.md)

**标签**：契约冻结请打 `api-v1.0`；破坏性变更 `api-v1.1` + 会签。
