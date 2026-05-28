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
| `npm run lint` | ESLint（`src/` 禁止 `axios` 直连，仅 `src/api/` 允许） |
| `npm run lint:fix` | ESLint 自动修复 |
| `npm run generate:api-types` | 从 OpenAPI 生成 `src/api/generated/schema.d.ts` |

## OpenAPI 类型生成

契约源文件：**仓库根目录** `docs/api/openapi.yaml`（不是 OpenAI / LLM 接口）。

当后端变更 HTTP 契约时，按顺序执行：

1. 更新 `docs/api/openapi.yaml`（及 `docs/v1/api-contract.md`，走 `[API RFC]` 若破坏性变更）
2. 在 `frontend/` 目录生成类型：

```bash
cd frontend
npm run generate:api-types
```

3. 检查 `src/api/types.ts` 薄封装是否需调整（SSE 事件等 OpenAPI 未覆盖部分仍手写）
4. 运行校验：

```bash
npm run typecheck
npm run test
```

生成物路径：`frontend/src/api/generated/schema.d.ts`（已纳入版本库，CI 可直接 `typecheck`；改契约后请重新 generate 并提交该文件）。

## 对接

- 契约：`docs/api/openapi.yaml`、`docs/v1/api-contract.md`
- Mock：`docs/api/fixtures/`（后端骨架亦会加载同名 fixture）
- **禁止**在浏览器内配置 LLM API Key

### 失败态 status Mock 联调

1. 仓库根目录启动后端：`uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
2. 前端：`npm run dev`，打开论文详情 `/papers/hss-failed-001`
3. 应看到红色告警：`LLM_JSON_INVALID` + 失败说明，以及 `failed_during: classifying`

也可仅跑测试：`npm run test`（含 `types.contract.test.ts` 与 `PaperStatusPanel.integration.spec.ts`）。
