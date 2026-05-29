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
├── mocks/         # 可选：再导出 docs/api/fixtures（权威仍在仓库 fixtures）
└── views/         # 页面级组件
```

## 脚本

| 命令                         | 说明                                                    |
| ---------------------------- | ------------------------------------------------------- |
| `npm run dev`                | 本地开发                                                |
| `npm run build`              | 生产构建（含 `vue-tsc`）                                |
| `npm run typecheck`          | 仅 TypeScript 检查（`vue-tsc --noEmit`）                |
| `npm run test`               | Vitest 单元/组件测试（`src/**/*.test.ts`）              |
| `npm run test:watch`         | 监听模式                                                |
| `npm run lint`               | ESLint（Vue `recommended` + TS；`src/` 禁止裸 `axios`） |
| `npm run lint:fix`           | ESLint 自动修复                                         |
| `npm run format`             | Prettier 格式化全仓                                     |
| `npm run format:check`       | Prettier 检查（CI 用）                                  |
| `npm run knip`               | 未使用文件/依赖/导出（Knip）                            |
| `npm run check`              | 静态门禁：typecheck + format:check + lint + knip        |
| `npm run check:ci`           | CI 全量：check + test + build                           |
| `npm run generate:api-types` | 从 OpenAPI 生成 `src/api/generated/schema.d.ts`         |

## 提 PR 前门禁（本地与 CI 一致）

合并到 `develop` 前，在 `frontend/` 目录执行（与 [`.github/workflows/frontend.yml`](../.github/workflows/frontend.yml) 相同顺序）：

```bash
cd frontend
npm ci
npm run check:ci
```

等价于 `npm run check`（typecheck + format:check + lint + knip）后接 `test` 与 `build`。

格式化与 ESLint 分工：**Prettier** 管排版（`prettier.config.js`），**ESLint** 管逻辑与 Vue/TS 规则（`eslint.config.js`，末尾 `eslint-config-prettier` 避免冲突）。

PR 描述请粘贴 [docs/v1/pr-checklist.md](../docs/v1/pr-checklist.md) 中 **前端（FE）** 小节并逐项勾选。

## 契约变更流程（全员）

对外 HTTP 契约变更须先走 Issue **`[API RFC]`**，并 @BE-L @FE；破坏性变更见 [api-contract.md](../docs/v1/api-contract.md)（标签 `api-v1.1`）。

```text
[API RFC] Issue（@BE-L @FE）
    → BE-L：Pydantic + docs/api/openapi.yaml + docs/v1/api-contract.md
    → FE：npm run generate:api-types → 提交 schema.d.ts
    → FE：调整 src/api/types.ts 薄封装 / SSE 手写类型 / fixtures 测试
    → FE：npm run typecheck && npm run lint && npm run test && npm run build
    → PR 勾选 pr-checklist「前端（FE）」+ 说明是否改契约
```

| 步骤 | 负责人             | 产出                                                            |
| ---- | ------------------ | --------------------------------------------------------------- |
| 1    | BE-L（RFC 通过后） | `docs/api/openapi.yaml`、`docs/v1/api-contract.md`              |
| 2    | FE                 | `npm run generate:api-types` → `src/api/generated/schema.d.ts`  |
| 3    | FE                 | `src/api/types.ts`、客户端与视图；SSE 等 OpenAPI 未覆盖处仍手写 |
| 4    | FE                 | `docs/api/fixtures/` 对齐或契约测试更新                         |
| 5    | 双方               | 联调；BE-L Review 时确认 OpenAPI 与实现 `/docs` 一致            |

详细协作分层见 [docs/v1/collaboration.md §2](../docs/v1/collaboration.md#2-契约先行流程)。

## OpenAPI 类型生成

契约源文件：**仓库根目录** `docs/api/openapi.yaml`（不是 OpenAI / LLM 接口）。

RFC 合并或拉取含 OpenAPI 变更的分支后，在 `frontend/` 执行：

```bash
npm run generate:api-types
```

然后：

1. 检查 `src/api/types.ts` 薄封装（`components['schemas']`）与业务导入是否需要改
2. SSE（`qaStream.ts`）等未写入 OpenAPI 的类型保持手写并与 [api-contract.md](../docs/v1/api-contract.md) 一致
3. 运行 `npm run typecheck`、`npm run test`

生成物 `src/api/generated/schema.d.ts` **纳入版本库**；改契约后必须重新 generate 并随 PR 提交，否则 CI `typecheck` 会失败。

## 对接

- 契约：`docs/api/openapi.yaml`、`docs/v1/api-contract.md`
- Mock：`docs/api/fixtures/`（后端骨架亦会加载同名 fixture）
- **禁止**在浏览器内配置 LLM API Key

### 失败态 status Mock 联调

1. 仓库根目录启动后端：`uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
2. 前端：`npm run dev`，打开论文详情 `/papers/hss-failed-001`
3. 应看到红色告警：`LLM_JSON_INVALID` + 失败说明，以及 `failed_during: classifying`

也可仅跑测试：`npm run test`（含 `types.contract.test.ts` 与 `PaperStatusPanel.integration.spec.ts`）。
