# V1 API 契约详表

> 本文档为 [协作规范](./collaboration.md) §3 的展开版，与 [`docs/api/openapi.yaml`](../api/openapi.yaml)、[`docs/api/fixtures/`](../api/fixtures/) 保持一致。  
> **V1 已冻结**：变更须走 `[API RFC]` 并打标签 `api-v1.1`。

---

## 1. 范式分类 JSON（`ParadigmClassification`）

与 [产品 README](../../README.md#1-范式分类器paradigm-classifier) **完全一致**。用于分类器输出，并**内嵌**于 `GET /papers/{paper_id}` 的 `classification` 字段。

```json
{
  "paradigm": "HSS",
  "confidence": 0.95,
  "reason": "本文使用了历史制度主义视角，考察近代中国通商口岸的制度演变，无显式数据集与量化指标，属于典型的人文社科规范。"
}
```

| 字段 | 类型 | 约束 |
|------|------|------|
| `paradigm` | string | `"STEM"` \| `"HSS"` |
| `confidence` | number | 0～1 |
| `reason` | string | 面向用户/答辩展示 |

**V1 不设** `GET /papers/{id}/classification` 独立路由。

---

## 2. `status` 与 `stage` 区别

| 字段 | 出现位置 | 枚举 | 含义 |
|------|----------|------|------|
| **`status`** | `POST /papers`、`GET /papers`、`GET /papers/{id}`、`GET .../status` | `pending` `processing` `ready` `failed` | 论文**业务生命周期** |
| **`stage`** | 仅 `GET /papers/{id}/status` | `ingesting` `classifying` `extracting` `storing` `ready` `failed` | 流水线**当前步骤** |

- `status=processing` 时必有 `stage`（且 `stage` ≠ `ready`）。
- `status=ready` 时 `stage=ready`，`percent=100`。
- `status=pending`：任务已创建，流水线尚未写入 `stage` 时可返回 `stage=null` 或省略。

---

## 3. SSE（已冻结）

| 项 | 值 |
|----|-----|
| 方法 | **POST** |
| 路径 | `/api/v1/papers/{paper_id}/qa/stream` |
| 请求头 | `Content-Type: application/json`、`Accept: text/event-stream` |
| 请求体 | `{"question": "..."}` |
| FE 库 | `@microsoft/fetch-event-source`（**不用** GET + `EventSource`） |

详见 [§8](#8-post-apiv1paperspaper_idqastream)。

---

## 4. `POST /api/v1/papers`

**请求**：`multipart/form-data`，字段 `file`（PDF，`application/pdf`，建议 ≤32MB）。

**201 成功**：

```json
{
  "data": {
    "paper_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "pending",
    "message": "已接收 PDF，正在自动解构…"
  },
  "meta": { "request_id": "550e8400-e29b-41d4-a716-446655440000" }
}
```

**400 `INGEST_FAILED`**：

```json
{
  "error": {
    "code": "INGEST_FAILED",
    "message": "无法解析 PDF 或文件已损坏",
    "details": { "filename": "broken.pdf" }
  }
}
```

---

## 5. `GET /api/v1/papers`

**查询参数（均可选）**：

| 参数 | 类型 | 默认 |
|------|------|------|
| `paradigm` | `STEM` \| `HSS` | — |
| `status` | `pending` \| `processing` \| `ready` \| `failed` | — |
| `offset` | integer | `0` |
| `limit` | integer | `20`（max `100`） |

**200**：

```json
{
  "data": {
    "items": [
      {
        "paper_id": "hss-001",
        "title": "近代通商口岸制度演变研究",
        "paradigm": "HSS",
        "status": "ready",
        "created_at": "2026-05-19T10:00:00Z",
        "updated_at": "2026-05-19T10:05:00Z"
      }
    ],
    "total": 3,
    "offset": 0,
    "limit": 20
  },
  "meta": { "request_id": "…" }
}
```

---

## 6. `GET /api/v1/papers/{paper_id}`

**200（`ready`）**：

```json
{
  "data": {
    "paper_id": "hss-001",
    "title": "近代通商口岸制度演变研究",
    "status": "ready",
    "paradigm": "HSS",
    "created_at": "2026-05-19T10:00:00Z",
    "updated_at": "2026-05-19T10:05:00Z",
    "classification": {
      "paradigm": "HSS",
      "confidence": 0.95,
      "reason": "本文使用了历史制度主义视角，考察近代中国通商口岸的制度演变，无显式数据集与量化指标，属于典型的人文社科规范。"
    }
  },
  "meta": { "request_id": "…" }
}
```

处理中：`status` 为 `pending`/`processing` 时，`classification` 可为 `null`。

---

## 7. `GET /api/v1/papers/{paper_id}/status`

**200（处理中）**：

```json
{
  "data": {
    "paper_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "processing",
    "percent": 50,
    "stage": "classifying",
    "message": "正在识别范式与理论视角…",
    "updated_at": "2026-05-19T10:02:30Z"
  },
  "meta": { "request_id": "…" }
}
```

**200（完成）**：`status=ready`，`stage=ready`，`percent=100`。  

**200（失败）**：`status=failed`，`stage=failed`；并返回 `error_code` 与 `failed_during`（失败时所在流水线步骤，不含 `ready`/`failed`）：

```json
{
  "data": {
    "paper_id": "hss-failed-001",
    "status": "failed",
    "percent": 40,
    "stage": "failed",
    "message": "分类阶段 LLM 返回无效 JSON",
    "updated_at": "2026-05-19T10:15:00Z",
    "error_code": "LLM_JSON_INVALID",
    "failed_during": "classifying"
  },
  "meta": { "request_id": "…" }
}
```

本地 Mock 论文 ID：`hss-failed-001`（fixture 见 `docs/api/fixtures/paper-status-hss-failed-001.json`）。

---

## 8. `POST /api/v1/papers/{paper_id}/qa/stream`

**请求**：

```http
POST /api/v1/papers/hss-001/qa/stream HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{"question":"这篇论文的核心论点是什么？"}
```

**响应**：`text/event-stream; charset=utf-8`

```text
event: message
data: {"delta":"根据图谱，"}

event: citation
data: {"paper_id":"hss-001","node_id":"n1","label":"核心论点"}

event: done
data: {"answer_id":"ans-550e8400"}
```

| event | data |
|-------|------|
| `message` | `{"delta": string}` |
| `citation` | `{"paper_id", "node_id", "label"}` |
| `done` | `{"answer_id": string}` |
| `error` | `{"code", "message"}` |

建立流之前的错误（如 404/409）返回 JSON 错误体，不是 SSE。

---

## 9. `POST /api/v1/patrol`

**请求**：

```json
{
  "paper_ids": ["hss-001", "hss-002"],
  "mode": "lens_clash"
}
```

**200**：

```json
{
  "data": {
    "mode": "lens_clash",
    "paper_ids": ["hss-001", "hss-002"],
    "insights": [
      {
        "insight_id": "ins-001",
        "title": "理论视角冲突（Lens Clash）",
        "summary": "两篇论文研究对象均为平台零工经济劳动者，但理论框架存在潜在学派冲突。",
        "paper_ids": ["hss-001", "hss-002"],
        "node_refs": [
          { "paper_id": "hss-001", "node_id": "n_lens_a", "label": "消费社会" },
          { "paper_id": "hss-002", "node_id": "n_lens_b", "label": "公共领域" }
        ]
      }
    ],
    "generated_at": "2026-05-19T11:00:00Z"
  },
  "meta": { "request_id": "…" }
}
```

V1 同步接口，建议超时 60s。

---

## 10. Fixtures

| 文件 | 用途 |
|------|------|
| [fixtures/papers-list.json](../api/fixtures/papers-list.json) | `GET /papers` |
| [fixtures/paper-create.json](../api/fixtures/paper-create.json) | `POST /papers` 201 |
| [fixtures/paper-detail-ready.json](../api/fixtures/paper-detail-ready.json) | `GET /papers/{id}` |
| [fixtures/paper-status-processing.json](../api/fixtures/paper-status-processing.json) | `GET .../status` |
| [fixtures/graph-hss.json](../api/fixtures/graph-hss.json) | `GET .../graph` |
| [fixtures/patrol-lens-clash.json](../api/fixtures/patrol-lens-clash.json) | `POST /patrol` |
