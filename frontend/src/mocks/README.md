# 前端 Mock 数据

**权威来源**：仓库根目录 [`docs/api/fixtures/`](../../../docs/api/fixtures/)（与 OpenAPI / 后端骨架 Mock 一致）。

本目录提供**可选**的 TypeScript 再导出，便于离线脚本或 `VITE_USE_MOCK` 联调时 `import '@/mocks'`，**勿**在此维护第二份 JSON。

新增契约样例时：先改 `docs/api/fixtures/`，再在本目录 `index.ts` 增加对应 export（若需要）。
