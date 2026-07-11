# QA SSE 流式契约（V2 citation）

`POST /api/v1/papers/{paper_id}/qa/stream` 返回 `text/event-stream; charset=utf-8`。

OpenAPI 机器可读 schema 见 [`openapi.yaml`](./openapi.yaml) 中 `QaStream*` 组件；本文档与 `backend/graph/qa_v2.dispatch_citation()` 运行时行为一致。

## 请求

```http
POST /api/v1/papers/hss-001/qa/stream HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{"question":"这篇论文的核心论点是什么？"}
```

建立流**之前**的错误（400/404/409）返回 JSON `ErrorResponse`，不是 SSE。

| HTTP | 场景 |
|------|------|
| 400 | `CROSS_PAPER` — 跨论文比较类问题，应引导用户使用 Patrol |
| 404 | 论文不存在 |
| 409 | 图谱未就绪 |

## 帧格式

每帧两行（`\n\n` 分隔）：

```text
event: <name>
data: <单行 JSON>
```

| `event` | `data` schema（OpenAPI） | 说明 |
|---------|-------------------------|------|
| `message` | `QaStreamMessageData` | LLM 增量文本 `{ "delta": string }` |
| `citation` | `QaStreamCitation` | 引用锚点，V2 含 `type` 判别 |
| `done` | `QaStreamDoneData` | 流结束 `{ "answer_id", "answer"? }` |
| `error` | `QaStreamErrorData` | 流内异常；HTTP 仍为 200，随后通常仍有 `done` |

## V2 citation 类型

LLM 在回答中使用 `[CITE:...]` 标记；后端解析后发出 `event: citation`。

| `type` | LLM 标记 | 必填字段 | 可选/附加 |
|--------|----------|----------|-----------|
| `node` | `[CITE:{node_id}]` | `paper_id`, `node_id`, `label` | V1 兼容：缺 `type` 时 FE 视为 `node` |
| `edge` | `[CITE:edge:{edge_id}]` | `paper_id`, `edge_id`, `label` | `label` 通常为 `"{source} → {target}"` |
| `chunk` | `[CITE:chunk:{chunk_id}]` | `paper_id`, `chunk_id`, `label`, `text_preview` | `text_preview` ≤ 120 字符 |
| `page` | `[CITE:page:{page}]` | `paper_id`, `page`, `label` | `page` 为 integer 或 string（如 `appendix`） |

### 示例帧

```text
event: message
data: {"delta":"根据检索上下文，"}

event: citation
data: {"type":"node","paper_id":"hss-001","node_id":"n1","label":"核心论点"}

event: citation
data: {"type":"edge","paper_id":"hss-001","edge_id":"e_supports_01","label":"分论点 → 核心论点"}

event: citation
data: {"type":"chunk","paper_id":"hss-001","chunk_id":"hss-001-00001","label":"片段 hss-001-00001","text_preview":"制度一旦形成便会产生路径依赖。"}

event: citation
data: {"type":"page","paper_id":"hss-001","page":12,"label":"第12页"}

event: done
data: {"answer_id":"ans-550e8400"}
```

标准 Mock 帧列表见 [`fixtures/qa-stream-v2-frames.json`](./fixtures/qa-stream-v2-frames.json)。

## 前端集成

1. `npm run generate:api-types` 生成 `QaStreamCitation` 等 TS 类型。
2. `parseQaStreamEvent()`（`frontend/src/api/qaStream.ts`）按 `event` 名解析 JSON。
3. `type=node` 时可联动图谱高亮 `node_id`；其他类型以标签展示为主。

## 变更记录

| 版本 | 变更 |
|------|------|
| V1 | 仅 `citation` 含 `paper_id` / `node_id` / `label` |
| V2 | 增加 `type` 判别与 edge/chunk/page 载荷（RAG hybrid QA） |
