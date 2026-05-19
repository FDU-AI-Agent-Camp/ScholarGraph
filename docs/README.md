# ScholarGraph 文档

产品愿景与架构总览：[README.md](../README.md)。

## V1 核心文档（请优先阅读）

| 文档 | 说明 |
|------|------|
| [v1/README.md](./v1/README.md) | V1 范围、成功标准 |
| **[v1/work-assignment.md](./v1/work-assignment.md)** | **任务分工**：6 人角色、P0～P6、边界/指标/分支/排期/看板 |
| **[v1/collaboration.md](./v1/collaboration.md)** | **协作规范**：分层、流程、端点索引、联调清单 |
| **[v1/api-contract.md](./v1/api-contract.md)** | **API 详表**：请求/响应示例、SSE、status/stage、范式 JSON |
| [v1/tech-stack.md](./v1/tech-stack.md) | Vue3 + FastAPI、REST / SSE / 轮询 |
| [api/openapi.yaml](./api/openapi.yaml) | 机器可读 OpenAPI 3.1 |
| [api/fixtures/](./api/fixtures/) | FE Mock 样例 JSON |

## V1 协作流程（全员）

| 文档 | 说明 |
|------|------|
| [v1/onboarding.md](./v1/onboarding.md) | **上手指南**：环境、分支、角色阅读顺序 |
| [v1/pr-checklist.md](./v1/pr-checklist.md) | **PR 检查清单**（提 PR 时粘贴） |
| [v1/handoff-to-platform.md](./v1/handoff-to-platform.md) | **模块交付 BE-L**（BE-1～4 交接口，不注册路由） |

## V1 参考资料

| 文档 | 说明 |
|------|------|
| [v1/corpus.md](./v1/corpus.md) | 黄金微语料集 |
| [v1/eval/](./v1/eval/) | 评测标注 |
| [api/README.md](./api/README.md) | OpenAPI 与契约入口 |

## 分支

- 初始化：`feature/project-init`
- 稳定：`main` / `develop`
- 命名规则：见 [任务分工 §3](./v1/work-assignment.md#3-git-分支与-pr全员)
