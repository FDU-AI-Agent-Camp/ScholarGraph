# ScholarGraph 前端（Vue 3）

## 快速开始

```bash
cd frontend
npm install
cp .env.development.example .env.development   # 可选
npm run dev
```

默认 `http://localhost:5173`，`/api` 代理到后端 `http://127.0.0.1:8000`。

## 目录约定（FE 全员）

```text
frontend/src/
├── api/           # axios 封装、类型、SSE
├── components/    # 可复用 UI（layout、graph、papers）
├── composables/   # usePaperStatus 等
├── router/        # 路由
├── stores/        # Pinia
└── views/         # 页面级组件
```

## 脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 本地开发 |
| `npm run build` | 生产构建 |
| `npm run typecheck` | TypeScript 检查 |
| `npm run test` | Vitest 单元/组件测试（`src/**/*.test.ts`） |
| `npm run test:watch` | 监听模式 |

## 对接

- 契约：`docs/api/openapi.yaml`、`docs/v1/api-contract.md`
- Mock：`docs/api/fixtures/`（后端骨架亦会加载同名 fixture）
- **禁止**在浏览器内配置 LLM API Key

### 失败态 status Mock 联调

1. 仓库根目录启动后端：`uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
2. 前端：`npm run dev`，打开论文详情 `/papers/hss-failed-001`
3. 应看到红色告警：`LLM_JSON_INVALID` + 失败说明，以及 `failed_during: classifying`

也可仅跑测试：`npm run test`（含 `types.contract.test.ts` 与 `PaperStatusPanel.integration.spec.ts`）。
