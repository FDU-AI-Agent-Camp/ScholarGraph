# 业务模块交付 BE-L 规范

> BE-1～4 完成模块后，按本文「交给平台层」；**不要**自行注册 HTTP 路由或改 `workflow.py`。  
> BE-L 负责：`backend/api/routes/*`、`backend/graph/workflow.py`、OpenAPI 与合并 `develop`。

---

## 1. 交付原则

| 原则 | 说明 |
|------|------|
| **只交付 Service** | 可导入的函数/类，无 FastAPI `APIRouter` |
| **可单测** | `tests/{模块}/` 使用 Mock LLM，不依赖真实 API |
| **可脚本演示** | `scripts/run_*.py` 在仓库根 `uv run` 可执行 |
| **PR 说明** | 写明「请 BE-L 注册路由：…」并 @BE-L |

```text
组员 PR → develop（仅业务包）
       ↓
BE-L 汇总 PR：注册路由 + workflow 节点 + 集成测试
       ↓
FE 联调 develop
```

---

## 2. BE-1 — 摄入（`ingest`）

### 交付路径

| 类型 | 路径 |
|------|------|
| 实现 | `backend/ingest/pdf.py`（PyMuPDF 全文 + 前 25 页 head）、`backend/ingest/snippets.py`（分类器输入切片） |
| 导出 | `backend/ingest/__init__.py` 暴露 `ingest_pdf` |
| 门面 | `backend/services/ingest_service.py`（workflow / API 调用） |
| 脚本 | `scripts/extract_text.py` |
| 测试 | `tests/ingest/` |
| 文档 | `docs/v1/corpus.md` 填齐 |

### 必须实现的接口

```python
# backend/ingest/__init__.py
from pathlib import Path
from typing import TypedDict

class IngestResult(TypedDict):
    paper_id: str
    full_text: str
    classifier_input: str  # 标题+摘要+关键词+引言片段

async def ingest_pdf(file_path: Path, paper_id: str | None = None) -> IngestResult:
    """解析 PDF，返回全文与分类器输入片段。"""
    ...
```

### 交给 BE-L 时

- [ ] `ingest_pdf` 签名与上表一致
- [ ] 微语料 3 篇 PDF 可解析（路径见 corpus.md）
- [ ] PR 描述写：**请 BE-L 在 workflow 增加 `ingest` 节点，写入 `stage=ingesting`**

### 禁止

- 调用 `classify` / `extract`；不依赖 `backend.agents`

---

## 3. BE-2 — Agent（`agent`）

### 交付路径

| 类型 | 路径 |
|------|------|
| Schema | `backend/schemas/paradigm.py`、`graph.py`、`validators.py` |
| Agent | `backend/agents/classifier.py`、`extractor.py` |
| Prompt | `backend/prompts/classifier.md`、`extract_stem.md`、`extract_hss.md` |
| 脚本 | `scripts/run_classifier.py`、`scripts/run_extract.py` |
| 测试 | `tests/agents/`、`tests/test_schema.py`（协商） |
| 评测 | `docs/v1/eval/classifier_labels.csv` |

### 必须实现的接口

```python
# backend/agents/__init__.py 或明确导出路径
async def classify(classifier_input: str) -> ParadigmClassification: ...

async def extract(full_text: str, paradigm: Paradigm) -> UnifiedPaperGraph: ...
```

`ParadigmClassification` 字段见 [api-contract §1](./api-contract.md#1-范式分类-jsonparadigmclassification)。

### 交给 BE-L 时

- [ ] 微语料分类 **3/3** 与 `classifier_labels.csv` 一致
- [ ] 至少 1 篇 STEM + 1 篇 HSS 图谱 JSON 通过 Pydantic
- [ ] PR 描述写：**请 BE-L 在 workflow 串联 classify → extract，更新 stage=classifying/extracting`**
- [ ] 若改 `schemas/graph.py`，已走 `[Schema RFC]`

### 禁止

- 实现 `GraphStore`、`qa_stream`、`run_patrol`
- 修改 `backend/llm/client.py`（除非 BE-L 牵头 PR）

---

## 4. BE-3 — 图谱与问答（`graph-qa`）

### 交付路径

| 类型 | 路径 |
|------|------|
| 存储/查询 | `backend/graph/store.py`、`backend/graph/query.py` |
| 问答 | `backend/graph/qa.py`、`backend/prompts/qa.md` |
| 脚本 | `scripts/run_qa.py` |
| 测试 | `tests/graph/` |

### 必须实现的接口

```python
class GraphStore:
    async def save(self, paper_id: str, graph: UnifiedPaperGraph) -> None: ...
    async def load(self, paper_id: str) -> UnifiedPaperGraph: ...
    def to_g6(self, graph: UnifiedPaperGraph) -> dict: ...
        # 返回 {"nodes": [...], "edges": [...]}，字段见 api-contract

class GraphQuery:
    def subgraph_for_question(self, graph: UnifiedPaperGraph, question: str) -> dict: ...

async def qa_stream(paper_id: str, question: str) -> AsyncIterator[QaEvent]:
    """yield 事件：message | citation | done | error，供 SSE 序列化。"""
```

### 交给 BE-L 时

- [ ] `to_g6()` 与 [fixtures/graph-hss.json](../api/fixtures/graph-hss.json) 同构
- [ ] `qa_stream` 至少 Mock 测试覆盖 4 类事件
- [ ] PR 描述写：
  - **请 BE-L 注册 `GET /papers/{id}/graph` → GraphStore + to_g6**
  - **请 BE-L 注册 `POST /papers/{id}/qa/stream` → qa_stream**

> **平台接线状态**：`backend/api/routes/papers.py` 已注册 `GET .../graph`、`POST .../qa/stream`（委托 `backend/graph/qa.py` `qa_stream()`）。`POST /papers` 经 `paper_pipeline_scheduler.schedule_paper_pipeline` 异步启动 workflow。新模块 PR 仍须勾选上列交付项，便于 Review 与回归。

### 禁止

- 定义 `UnifiedPaperGraph` 结构（归 BE-2）；可读类型即可
- 自行实现 SSE HTTP 响应（只交异步迭代器或回调）

---

## 5. BE-4 — 巡检（`patrol`）

### 交付路径

| 类型 | 路径 |
|------|------|
| Schema | `backend/schemas/patrol.py` |
| 逻辑 | `backend/patrol/lens_clash.py`（及可选 `contradiction.py`） |
| 编排 | `backend/agents/patrol.py` 或 `backend/patrol/service.py` |
| 脚本 | `scripts/run_patrol.py` |
| 测试 | `tests/patrol/` |
| 评测 | `docs/v1/eval/patrol_samples.md` |

### 必须实现的接口

```python
async def run_patrol(paper_ids: list[str], mode: PatrolMode) -> PatrolReport:
    """paper_ids 长度 2；mode: lens_clash | contradiction。"""
```

响应结构与 [fixtures/patrol-lens-clash.json](../api/fixtures/patrol-lens-clash.json) 的 `data` 一致。

### 交给 BE-L 时

- [ ] 2 篇 HSS 语料可产出 ≥1 条 Lens Clash insight
- [ ] PR 描述写：**请 BE-L 注册 `POST /api/v1/patrol` → run_patrol**

### 禁止

- 直接读文件绕过 `GraphStore.load`
- 修改 `schemas/graph.py`（只读节点类型）

---

## 6. BE-L 汇总清单（集成时自检）

收到组员 PR 后，BE-L 在同一或后续 PR 中完成：

| 步骤 | 动作 |
|------|------|
| 1 | `from backend.ingest import ingest_pdf` 等导入无循环依赖 |
| 2 | `graph/workflow.py` 节点：`ingest` → `wait_head_refine` → `classify` → `extract` → `store`，经 `PipelineStatusService` 更新 `stage` / `percent` |
| 3 | `api/routes/papers.py`：REST + `schedule_paper_pipeline` |
| 4 | `api/routes/papers.py`：`POST .../qa/stream` SSE 序列化 `qa_stream()` |
| 5 | `api/routes/patrol.py`：调用 `run_patrol` |
| 6 | `tests/integration/` 端到端 Mock / DoD |
| 7 | 同步 `openapi.yaml` 与 `/docs` |

---

## 7. 路由注册对照表（仅供 BE-L）

| HTTP | 调用 |
|------|------|
| `POST /papers` | 存文件 → `schedule_paper_pipeline(paper_id, pdf_path)` |
| `GET /papers/{id}/status` | `PaperService.get_status` / `PipelineStatusService` 快照 |
| `GET /papers/{id}/graph` | `GraphStore.load` + `to_g6` |
| `POST /papers/{id}/reextract` | `PaperService.force_reextract()` → 重新调度流水线 |
| `POST /papers/{id}/qa/stream` | `qa_stream` → SSE（同在 `papers.py`） |
| `POST /patrol` | `run_patrol` |

---

## 8. 相关文档

- [协作规范 §4](./collaboration.md#4-对内-service-接口拼接契约)
- [API 契约详表](./api-contract.md)
- [PR 检查清单](./pr-checklist.md)
