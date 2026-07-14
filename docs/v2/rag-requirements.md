# V2 RAG 四阶段需求文档（`feature/backend/rag`）

> **目标**：将单篇 QA 从「纯图谱检索」升级为「图谱骨架 + 原文片段向量召回」的多尺度混合 RAG；同时增强 Patrol 的混合 context 与结构化输出，并建立可自动回归的 QA 金标评估体系。
> **范围**：新增 `backend/rag/` 模块（含 chunking/indexing/vector_store/hybrid_retriever）、改造 `backend/graph/qa.py`、改造 `backend/services/paper_service.py` / `pipeline_completion_service.py`、新增 Patrol 模式、新增 benchmark 脚本。
> **版本**：v0.5.0.x
> **负责人**：待定
> **依赖**：P1 持久化基座建议先完成或并行，但 RAG 可在现有内存服务上先跑通，再迁移到 DB。

---

## 1. 背景与现状

### 1.1 当前 QA 局限

`backend/graph/qa.py` 当前只消费图谱子图：

```python
subgraph = self._query.subgraph_for_question(graph, question)
prompt = self._build_prompt(graph, subgraph, question, is_preview=is_preview)
```

问题：
- 细节型问题（如「方法 X 的模块 B 如何设计？」）依赖图谱节点是否足够细。
- 答案缺少原文页码/片段引用，用户无法快速核验。
- 无法回答「某实验数值具体是多少」等需要 verbatim 文本的问题。

### 1.2 已有基础

| 模块 | 能力 | 是否可复用 |
|---|---|---|
| `backend/llm/embeddings.py` | `EmbeddingClient`，支持 openai/ollama，默认 `bge-m3` | ✅ 直接复用 |
| `backend/graph/query.py` | 图谱 2-hop 子图检索 | ✅ 作为 A 尺度 |
| `backend/graph/qa.py` | SSE 流式 QA、`[CITE:node_id]` 解析 | ✅ 扩展 |
| `backend/ingest/chunking.py` | 文本切分逻辑 | ✅ 复用或增强 |
| `backend/services/paper_service.py` | `full_text` 与 PDF 路径 | ✅ 用于 chunk 来源 |

### 1.3 缺失部分

- ChromaDB / 向量存储
- chunk → embed → persist 流程
- 图谱实体（Entities）与关系（Relations）的 Embedding 索引
- 统一向量召回 Entities + Relations + Chunks 的混合检索
- 支持 `[CITE:chunk_index]` / `[CITE:page_X]` / `[CITE:entity_id]` / `[CITE:edge_id]` 的 Prompt 与 citation 解析
- QA 尺度路由
- HyDE（Hypothetical Document Embeddings）扩展接口
- 金标评估与 LLM-as-a-Judge

### 1.4 架构借鉴：轻量版 LightRAG

本分支借鉴 **LightRAG**（HKUDS 实验室，2024 年 10 月发布，EMNLP 2025，arXiv:2410.05779）的设计思想。LightRAG 是 Microsoft GraphRAG 的轻量级替代方案，保留了图结构的优势，但大幅降低了构建成本和检索延迟。

#### LightRAG 与 GraphRAG 的关键差异

| 维度 | Microsoft GraphRAG | LightRAG |
|---|---|---|
| 核心机制 | 社区检测（Leiden）+ 逐社区摘要 | 双向量索引：实体向量 + 关系向量 |
| 构建成本 | 高：需遍历全图、多轮 LLM 摘要 | 低：仅需实体/关系 embedding |
| 检索延迟 | 高 | 低 |
| 增量更新 | 困难 | 天然支持：新文档只需插入新实体/关系 |

#### LightRAG 的三层检索

1. **实体向量索引**：每个实体节点有独立向量表示（实体名称 + 描述）。查询时问题向量与实体向量相似度匹配，找到相关实体后沿关系边扩散到邻居节点（对应 GraphRAG Local Search）。
2. **关系向量索引**：每条关系边也有独立向量表示（关系描述 + 两端实体信息）。能捕捉跨实体的语义模式（如趋势、对比），而不仅是单个实体匹配。
3. **关键词引导查询**：LightRAG 从问题中提取关键词，将关键词向量拼接成组合查询向量，比直接用整句 embedding 更聚焦，减少语义稀释。

开源实现参考：[HKUDS/LightRAG](https://github.com/HKUDS/LightRAG)。

#### 本分支的落地裁剪

我们不追求完整复刻 LightRAG，而是吸收其核心思想做最小可行实现：

- **实体向量化**：将图谱节点的 `label` + `rationale` + `source_span` 生成 Embedding，存入 `paper_entities`。
- **关系向量化**：将边的 `source → target` 关系描述 + `rationale` 生成 Embedding，存入 `paper_relations`。
- **原文块向量化**：将 `full_text` 切分后的 chunks 生成 Embedding，存入 `paper_chunks`。
- **统一向量检索**：`HybridRetriever` 同时召回 Entities、Relations、Chunks，再交给 LLM 统一生成。
- **暂不实现**：关键词引导查询（可作为 Phase 2.x 优化项）；增量更新能力（P1 持久化后较容易补齐）。

相比微软 GraphRAG 的社区聚类+摘要，轻量版 LightRAG 更适合当前阶段：实现简单、全部走向量索引、同时吃到图谱语义红利。微软 GraphRAG 的宏观社区摘要能力可作为后续可选增强（不在本分支）。

---

## 2. 目标架构：三尺度 RAG 路由

```text
用户问题
  │
  ├─► 尺度 A：图谱骨架摘要
  │      NetworkX 骨架节点 + 1-hop 边
  │      适合：核心论点 / 整体结构 / "这篇论文做了什么"
  │
  ├─► 尺度 B：细节与证据
  │      ChromaDB 统一向量召回：Entities + Relations + Chunks
  │      适合：方法细节 / 数据集 / 实验数值 / 具体证据 / 某条边的 rationale
  │
  └─► 尺度 C：共同体巡检
         多篇图谱对比 + LLM 总结
         适合：两篇论文关系 / 矛盾 / 视角冲突
```

当前实现：
- **A 尺度**：已有（基于 `GraphQuery` 关键词 + 拓扑）。
- **B 尺度**：缺失，本分支核心目标。采用轻量版 LightRAG 思路，统一走向量召回。
- **C 尺度**：已有 `patrol` 基础，需增强。

---

## 3. Phase 1 — B 尺度基础设施

### 3.1 依赖

`pyproject.toml` 增加：

```toml
dependencies = [
    ...,
    "chromadb>=0.5.0",
]
```

执行 `uv lock && uv sync`。

### 3.2 模块结构

```text
backend/rag/
├── __init__.py
├── chunking.py          # 文本切分
├── indexing.py          # 实体/关系/Chunk 向量化索引构建
├── vector_store.py      # ChromaDB 统一封装（Chunks + Entities + Relations）
├── hybrid_retriever.py  # 统一向量召回 + 可选 A 尺度图谱
├── qa_router.py         # 问题尺度判定
└── models.py            # RAG 相关 Pydantic schemas
```

> **设计选择**：采用 3 个独立 collection（`paper_chunks`、`paper_entities`、`paper_relations`），每个 collection 内部用 `paper_id` 过滤。这样实现简单、类型清晰，也便于未来独立调优 top-k。

### 3.3 `chunking.py` 需求

输入：`paper_id` + `full_text`（PyMuPDF 提取的纯文本）。

输出：`list[PaperChunk]`：

```python
class PaperChunk(BaseModel):
    chunk_id: str          # 如 "{paper_id}-00012"
    paper_id: str
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None    # abstract / introduction / methods / ...
    chunk_index: int
    source: str            # "pymupdf" / "mineru" / "grobid"
    char_start: int
    char_end: int
```

策略（V1 先固定窗口）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `chunk_size` | 512 tokens（或 1500 chars） | 可配置 |
| `chunk_overlap` | 20% | 可配置 |
| `section_detection` | 规则：匹配 "Abstract", "Introduction", "Methods", "Results", "Conclusion" 等 | 简单正则 |

### 3.4 `indexing.py` 需求

负责将图谱中的实体与关系转换为可嵌入文本。

#### `PaperEntity` 与 `PaperRelation`

```python
class PaperEntity(BaseModel):
    entity_id: str        # 复用图谱 node id，如 "n_method_pca"
    paper_id: str
    label: str
    node_type: str
    description: str     # 优先取 rationale / source_span；否则 label + type
    source_span: str | None

class PaperRelation(BaseModel):
    relation_id: str      # 复用图谱 edge id，如 "e_supports_01"
    paper_id: str
    source_id: str
    target_id: str
    relation_type: str
    description: str     # source_label + " --" + relation_type + "--> " + target_label + ": " + rationale
    rationale: str | None
    source_span: str | None
```

生成规则：
- **Entity 描述文本**：`{label}（类型：{node_type}）。{rationale or source_span or ""}`
- **Relation 描述文本**：`{source_label} --[{relation_type}]--> {target_label}。依据：{rationale}。原文：{source_span}`
- 优先使用图谱中已有的 `rationale` 与 `source_span`，充分发挥抽取阶段的边属性升维成果。

### 3.5 `vector_store.py` 需求

封装 ChromaDB client，统一提供 3 个 collection：`paper_chunks`、`paper_entities`、`paper_relations`。

```python
class VectorStore:
    def __init__(self, settings: Settings | None = None) -> None: ...

    # ---- indexing ----
    async def index_chunks(self, chunks: list[PaperChunk]) -> None: ...
    async def index_entities(self, entities: list[PaperEntity]) -> None: ...
    async def index_relations(self, relations: list[PaperRelation]) -> None: ...

    # ---- retrieval ----
    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]: ...

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str | None = None,
        top_k: int = 5,
    ) -> list[RetrievedEntity]: ...

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str | None = None,
        top_k: int = 5,
    ) -> list[RetrievedRelation]: ...

    async def delete_by_paper(self, paper_id: str) -> None: ...

    async def exists(self, paper_id: str) -> bool: ...
```

返回模型（`backend/rag/models.py`）：

```python
class RetrievedChunk(PaperChunk):
    distance: float

class RetrievedEntity(PaperEntity):
    distance: float

class RetrievedRelation(PaperRelation):
    distance: float
```

ChromaDB 配置：
- 本地持久化路径：`./data/chroma/`（与 `data/graphs/` 同级）。
- 3 个 collection：
  - `paper_chunks`：metadata 含 `paper_id`, `page_start`, `page_end`, `section`, `chunk_index`, `source`
  - `paper_entities`：metadata 含 `paper_id`, `entity_id`, `node_type`
  - `paper_relations`：metadata 含 `paper_id`, `relation_id`, `relation_type`, `source_id`, `target_id`
- embedding 函数统一复用 `EmbeddingClient.embed_texts`。
- 单篇 QA 时所有查询必须带 `paper_id` metadata 过滤，避免跨论文污染。

### 3.6 写入时机与状态门禁（P10）

`pipeline_completion_service.finalize()` **不再直接 READY**：图谱落盘后先 `mark_indexing`（`PaperStatus.INDEXING`），再通过 EventBus 发布 `PipelineFinalized`。官方排他订阅者 `backend.rag.handlers.on_pipeline_finalized_for_rag` 完成索引后，再 promote 为 `ready` / `ready_with_warnings`，并发布 `RagIndexed`。

```python
# finalize (sync path)
status_service.mark_indexing(paper_id)  # graph on disk; vector index pending
event_bus.publish(PipelineFinalized(...))

# EventBus worker → on_pipeline_finalized_for_rag
await rag_index_service.index_paper_for_rag_async(...)  # delete_by_paper + upsert
await _promote_terminal_status(...)  # ready | ready_with_warnings + RagIndexed
```

**产品面行为（相对「finalize 即 READY」的变更）**：

| 场景 | 行为 |
|------|------|
| 状态为 `indexing` 且无 preview | `GET /papers/{id}/graph` → **409 `GRAPH_NOT_READY`**（图谱可能已落盘仍不可读） |
| FE 上传轮询 | `indexing` **非终态**；需等到 `ready` / `ready_with_warnings` / `failed`（`isTerminalStatus` + `BadgeStatus.indexing`） |
| EventBus 未消费 / worker 挂起 | **不再默认永久卡死**：超过 P13 macro watchdog 窗口（started 超时 + heartbeat 陈旧）或冷启动 reconcile 后强制 `ready_with_warnings` |
| 微观 `wait_for` 超时 | 立即 promote `ready_with_warnings`（`rag_index_timeout`）；线程池内 Chroma/embedding 可能仍短暂续跑（见下方残留） |

**超时 / 失败兜底**：

1. **Handler 内失败**：契约校验失败或索引异常 → promote `ready_with_warnings`（不长期卡在 `indexing`），写 `extract_warnings` / 日志，并发布 `RagIndexed(success=False)`。  
2. **进程级**：EventBus fire-and-forget；生命周期应 `register_pipeline_finalized_handlers`；拓扑测 `tests/events/test_event_bus_topology.py` 断言排他订阅。  
3. **P13 双层 indexing watchdog（已落地）**：  
   - **微观**：`on_pipeline_finalized_for_rag` 对 `index_paper_for_rag_async` 包 `asyncio.wait_for`（`RAG_SINGLE_INDEX_TIMEOUT_SECONDS`，默认 120s）；超时写入 `rag_index_timeout` 并 promote `ready_with_warnings`。  
   - **宏观**：`pipeline_runs.indexing_started_at` + `indexing_heartbeat`；lifespan 挂载周期扫尾（`RAG_INDEXING_WATCHDOG_SECONDS` / `INTERVAL`）；仅当 **started 超时且 heartbeat 陈旧**（`RAG_INDEXING_HEARTBEAT_STALE_SECONDS`）才强制收尾，写入 `rag_indexing_stuck_timeout`、promote、发布 `RagIndexed(success=False)`。Handler 索引期间按 `RAG_INDEXING_HEARTBEAT_INTERVAL_SECONDS` 续命，避免大文件误杀。  
   - **冷启动**：进程起来时 reconcile 所有遗留 `indexing`（EventBus 内存队列不跨进程；忽略心跳门闩）。  
   - **CI 防退化**：`scripts/check_rag_io_timeouts.py`（`make ci` / `check_backend`）断言 handler `wait_for` + 可配置超时 knobs + `backend/{rag,llm,patrol}` 内 `httpx.*.Client` 必须带 `timeout=`；强制收尾日志带 `[P13_WATCHDOG_HEAL]`（ELK/CloudWatch 可按该 tag 做小时级频次告警）。  
4. **Patrol**：索引未就绪时 insight 带 `is_degraded` + `INDEX_NOT_READY`；降级结果**不入**服务端进程 cache，HTTP `Cache-Control: private, no-store`，FE 10s/30s/60s 自愈轮询可拿到新鲜结果。健康报告 24h cache 键含 `graph_version` + `active index_run_id`，re-extract / 重索引后自动失效。Watchdog 强制终态后 Patrol 仍走 P9 降级闭环。

注意：

- 失败不导致流水线 `failed`，但可能以 `ready_with_warnings` 暴露。  
- 重新抽取（re-extract）时先 `delete_by_paper` / `replace_paper_index` 再重建。  
- `index_paper_for_rag` 按 `paper_id` 加锁，upsert 幂等。  
- **孤儿线程（best-effort）**：VectorStore 重活经 `asyncio.to_thread`；`wait_for` 超时取消的是 coroutine await，**不保证**取消线程池内 Chroma/embedding。已 promote 后陈旧线程仍可能 upsert / `set_active_run_id`；与后续 re-extract 的竞态多数由 paper 级锁缓解。后续增强可选超时路径显式 `delete_by_paper` 或令牌失效，当前按知情残留接受。  
- 同进程内若同步码**不经** `to_thread` 堵死事件循环，heartbeat / macro watchdog / HTTP 会一并挂起——属架构约束，非 P13 回退。

### 3.7 配置项

```env
# ChromaDB
CHROMADB_PATH=./data/chroma
CHROMADB_CHUNK_COLLECTION=paper_chunks
CHROMADB_ENTITY_COLLECTION=paper_entities
CHROMADB_RELATION_COLLECTION=paper_relations

# Chunking
CHUNK_SIZE_TOKENS=512
CHUNK_OVERLAP_RATIO=0.20

# Retrieval（每个 collection 独立 top-k）
RAG_TOP_K_CHUNKS=5
RAG_TOP_K_ENTITIES=5
RAG_TOP_K_RELATIONS=5
```

---

## 4. Phase 2 — QA 混合 RAG

### 4.1 尺度路由

`backend/rag/qa_router.py`（实现：`backend/llm/qa_scale.py`）：

```python
class QuestionScale(StrEnum):
    SUMMARY = "summary"          # 摘要 / 整体结构
    DETAIL = "detail"            # 方法 / 论证关系 / 结构细节
    VERIFICATION = "verification"  # 证据 / 材料 / 实验与指标

def detect_question_scale(question: str) -> QuestionScale: ...
```

与 `data/qa_golden_set.json` 的 ``scale`` 字段及 ``RetrievalContext.scale`` 使用同一套取值。

**遗留别名**（早期草案 ``skeleton`` / ``cross``）：``skeleton`` → ``summary``；``cross``（多篇对比）保留给 Patrol，**不是** ``QuestionScale`` 成员。

判定规则（V1 硬规则，后续可升级 LLM）：

| 关键词/模式 | 尺度 |
|---|---|
| "核心论点" / "做了什么" / "摘要" / "整体" / "主要结论" | SUMMARY |
| "方法" / "具体" / "关系" / "分论点" / "采用了" | DETAIL |
| "材料" / "证据" / "实验" / "数据集" / "哪些节点" / "如何论证" | VERIFICATION |
| "对比" / "矛盾" / "两篇" / "差异" | 多篇对比（Patrol，非 QuestionScale） |

### 4.2 Hybrid Retriever

`backend/rag/hybrid_retriever.py`：

```python
from collections.abc import Callable
from typing import Any

class HybridRetriever:
    def __init__(
        self,
        graph_query: GraphQuery | None = None,
        vector_store: VectorStore | None = None,
    ) -> None: ...

    async def retrieve(
        self,
        paper_id: str,
        question: str,
        graph: UnifiedPaperGraph,
        *,
        scale: QuestionScale,
        # ---- HyDE 预留接口 ----
        query_transform: Callable[[str], str] | None = None,
        query_embedding: list[float] | None = None,
    ) -> RetrievalContext:
        """
        Return graph subgraph + retrieved entities/relations/chunks.

        Args:
            query_transform: Optional hook to rewrite the question before embedding.
                             Used by HyDE in the future: question -> hypothetical answer -> embed.
            query_embedding: Optional pre-computed embedding. If None, embed the (possibly transformed) question.
        """
```

`RetrievalContext`：

```python
class RetrievalContext(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    entities: list[RetrievedEntity]
    relations: list[RetrievedRelation]
    chunks: list[RetrievedChunk]
    scale: QuestionScale
```

**Single Source of Truth（B7 统一可信源）**

``HybridRetriever.retrieve()`` 每轮只查询一次图谱与向量，组装完整 ``RetrievalContext``。
``QaEngine`` 为纯消费组件，不再在 Prompt 拼装阶段重复调用 ``GraphQuery``：

```text
HTTP / Benchmark → qa_retrieval._load_graph_for_retrieval (scale 判定)
                → HybridRetriever.compute_subgraph (一次 GraphQuery)
                → HybridRetriever.retrieve(subgraph=…) → RetrievalContext
  ├─ nodes/edges     → Prompt {nodes}/{edges}   （RC 非空时唯一来源）
  └─ entities/relations/chunks → Prompt 向量段   （format_retrieval_context）
       ↓
qa_stream(..., retrieval_context=RC) → QaEngine._build_prompt()
```

**尺度与路由（与 develop 一致）**：

- 枚举为 ``QuestionScale.SUMMARY | DETAIL | VERIFICATION``；字符串 ``skeleton`` 仅作兼容别名。
- ``scale`` 由 ``qa_retrieval`` 在调用 retriever **之前**判定并必填传入；retriever **不**做自动推断。
- ``QuestionScale.CROSS_PAPER`` 在 HTTP 层 ``verify_question_scale`` 拦截（400），不进入 retriever。

**向量命中与图谱子图**：

- 图谱子图 → ``RC.nodes`` / ``RC.edges``（A 尺度 / 全尺度 Prompt 图段）。
- 向量 Top-K → ``RC.entities`` / ``RC.relations`` / ``RC.chunks``（B 尺度独立 Prompt 段）。
- **禁止**将向量命中 merge 进 ``nodes/edges``；格式化职责在 ``qa_v2.format_retrieval_context``。

**降级（Fallback）**：

- **全量降级**：当 ``retrieval_context is None``，或 ``nodes`` 与 ``edges`` 均为空
  （V1 单测 / 未走 HybridRetriever 的路径）时，``QaEngine`` 惰性调用
  ``GraphQuery.subgraph_for_question()``，保持 M2 / A-09 向后兼容。
- **局部降级（半挂空挡）**：当 RC 仅含 ``nodes`` 或仅含 ``edges`` 时（例如分布式检索
  抖动导致边丢失），复用已有切片，**仅对缺失的一半**触发一次 ``GraphQuery`` 回填，
  避免 Prompt 关系链空白或重复全量查图。
- **不可变快照**：``QaEngine.stream()`` 入口对 RC 执行 ``model_copy(deep=True)``
  （``freeze_retrieval_context``），防止 SSE 并发消费者 ``.clear()`` / 原地改 dict
  污染 Prompt 拼装。
- **编排层子图复用**：``build_retrieval_context_with_fallback`` 在调用
  ``retrieve()`` 前 ``compute_subgraph`` 一次；超时或 ``VectorStoreUnavailableError``
  降级时将该 subgraph 传入 ``build_graph_only_context``，避免重复 GraphQuery。
- **离线 Replay**：``RetrievalContextReplayBundle``（``backend/rag/retrieval_context_io.py``）
  将 RC + 问题 + golden Prompt 固化为 JSON；CI 在阻断 ``GraphQuery`` / ``HybridRetriever``
  后反序列化 RC 直喂 ``qa_stream``，验证 Prompt 字节级一致，支撑 Prompt Tuning 流水线。
- **影子 Diff（M2 回归）**：同一问题分别走 V1（``retrieval_context=None`` → GraphQuery）
  与 V2（RC SSOT），对 Prompt 的 ``### 节点`` / ``### 关系`` 切片做排序 + 去空白后
  字符级比对（``subgraph_sections_shadow_fingerprint``），``Diff == 0``。

混合策略：
- `SUMMARY`：只用 A 尺度（图谱拓扑子图）。
- `DETAIL`：统一向量召回 Entities + Relations + Chunks，再与 A 尺度子图合并去重。
- `VERIFICATION`：偏重 B 尺度（实体 / 关系 / 原文 chunk）。

检索流程：
1. 根据 `query_transform`（如有）转换问题；否则使用原始问题。
2. 若未提供 `query_embedding`，则用 `EmbeddingClient` 对转换后文本生成 embedding。
3. 并行查询 3 个 collection：`query_entities`、`query_relations`、`query_chunks`。
   **必须使用 ChromaDB 元数据硬过滤 `where={"paper_id": paper_id}`**，由底层索引层加速；
   **严禁**全库 Top-K 检索后在 Python 内存中 filter。
4. 根据返回的 `entity_id` / `relation_id` 从原始图谱补全完整节点/边属性。
5. 合并到 Prompt context。

> **架构备忘**：Chunks（512 tokens）、Entity 描述、Relation 描述的文本长度差异巨大，返回的 distance（余弦/L2）绝对值范围不在同一维度，不具直接可比性。V1 阶段仅对三类结果分别做独立 Top-K 召回后平铺拼接，**暂不进行跨品类的分值归一化融合**。

> **HyDE 预留**：未来实现 HyDE 时，只需新增一个 `hyde_transform(question: str) -> str` 函数并传入 `query_transform`，底层检索逻辑无需改动。

### 4.3 Prompt 改造

`backend/prompts/qa.md` 扩展为：

```markdown
## 1. 论文元数据
范式：{paradigm}
标题：{title}

## 2. 相关图谱实体与关系
实体：...
关系：...

## 3. 相关原文片段
[page {page}] {text}
...

## 4. 引用要求
- 引用图谱节点时使用 [CITE:node_id]
- 引用图谱关系时使用 [CITE:edge:{edge_id}]
- 引用原文片段时使用 [CITE:chunk:{chunk_id}] 或 [CITE:page:{page}]

## 5. 回答要求
- 摘要/结构问题优先用图谱子图回答
- 细节/数值问题优先用原文片段 + 实体/关系描述回答
- 若上下文不足，明确说明"根据已有信息无法判断"
```

### 4.4 Citation 解析扩展

`backend/graph/qa.py` 中 `_CITE_RE` 扩展为同时匹配：
- `[CITE:node_id]`
- `[CITE:edge:{edge_id}]`
- `[CITE:chunk:{chunk_id}]`
- `[CITE:page:{page_number}]`

SSE `citation` 事件字段：

```json
{
  "type": "node" | "edge" | "chunk" | "page",
  "paper_id": "...",
  "node_id": "...",
  "edge_id": "...",
  "chunk_id": "...",
  "page": 12,
  "label": "...",
  "text_preview": "..."
}
```

**Edge citation 的 label 自动拼接**：
- 当 `type="edge"` 时，后端必须根据 `edge_id` 从图谱中查找对应边，自动拼接为 `"{source_label} → {target_label}"` 或 `"{source_label} --[{relation_type}]--> {target_label}"` 作为 `label` 字段返回。
- 这样旧前端无需改动即可展示边引用，保持响应契约兼容。

### 4.5 对 MVP 预览图谱的支持

如果当前只有 preview 骨架图但 chunks 尚未生成：
- QA 仍可用 A 尺度回答摘要问题。
- DETAIL 尺度路由到 B 尺度时若 chunks 不存在，返回友好提示："全文片段尚未索引完成，请稍后再试。"

---

## 5. Phase 3 — Patrol 增强

### 5.1 现有 Patrol 状态

- `lens_clash`：比对 `AnalyticalLens`。
- `contradiction`：比对 `Thesis` + `SubArgument`；无 SubArgument 时返回 `INSUFFICIENT_DATA`。

### 5.2 新增模式

#### `method_overlap`

触发：两篇 STEM 论文的 `Method` / `Dataset` 高度重合。

> **契约以 OpenAPI 为准**：[`docs/api/openapi.yaml`](../../api/openapi.yaml) 中 `MethodOverlapPoint`；示例 fixture 见 [`patrol-method-overlap.json`](../../api/fixtures/patrol-method-overlap.json)。

输出结构（`structured_points[]` 元素）：

```json
{
  "mode": "method_overlap",
  "overlap_type": "method",
  "overlap_label": "PCA",
  "overlap_score": 0.99,
  "match_type": "semantic",
  "paper_a_usage": "Applied PCA to MNIST pixel vectors before k-NN classification",
  "paper_b_usage": "Principal Component Analysis compressed MNIST features to 50 dimensions",
  "dataset_a": "MNIST",
  "dataset_b": "MNIST",
  "evidence_summary": "同义词方法标签在共享 MNIST 数据集上共振。",
  "node_refs": [
    { "paper_id": "stem-001", "node_id": "n_method_pca", "label": "PCA" },
    { "paper_id": "stem-002", "node_id": "n_method_pca_full", "label": "Principal Component Analysis" }
  ]
}
```

`method` 字段为 `@computed_field` 兼容别名，等价于 `overlap_label`（旧客户端可读，新实现请用 `overlap_label`）。

#### `claim_evolution`

触发：两篇论文 `ResearchQuestion` 或 `Thesis` 相似，但结论不同。

**部署配置（live / 演示）**：RQ 对齐采用 TD-4 两阶段漏斗——双塔粗筛（`PATROL_CLAIM_RQ_COARSE_THRESHOLD`，默认 0.42）→ Cross-Encoder 精排（`PATROL_RERANK_THRESHOLD`，默认 0.60）。**需 `RERANKER_ENABLED=true` 且配置 `RERANKER_MODEL`**；默认 `.env.example` 中 `RERANKER_ENABLED=false` 会回退严格双塔阈值（中文 0.75 / 英文 0.55），与 CI 金标门禁行为不一致，易导致大量 `INSUFFICIENT_DATA`。启动后见 `GET /api/v1/health` 的 `patrol_note`。

> **契约以 OpenAPI 为准**：`ClaimEvolutionPoint`；示例 fixture 见 [`patrol-claim-evolution.json`](../../api/fixtures/patrol-claim-evolution.json)。

输出结构（`structured_points[]` 元素）：

```json
{
  "mode": "claim_evolution",
  "research_question": "PCA 是否提升 MNIST 分类准确率？",
  "paper_a_claim": "PCA 将 MNIST 特征压缩至 50 维后分类准确率提升 3%",
  "paper_b_claim": "主成分分析在 MNIST 上保留 95% 方差，分类性能与基线相当",
  "evolution_type": "refined",
  "problem_fit_score": 82,
  "evidence_summary": "同一 RQ 下结论从「提升」演进为「与基线相当」。"
}
```

### 5.3 强类型子 Schema（已实现）

`backend/schemas/patrol.py` 中 `PatrolInsight.structured_points` 已使用 **discriminated union**（`mode` 字段区分四类 `PatrolPoint`）。前端类型以 `frontend/src/api/generated/schema.d.ts` 的 `PatrolPoint` 联合类型为准。

```python
class PatrolPoint(BaseModel):
    mode: Literal["contradiction", "lens_clash", "method_overlap", "claim_evolution"]

class MethodOverlapPoint(PatrolPoint):
    mode: Literal["method_overlap"]
    overlap_type: OverlapType
    overlap_label: str
    overlap_score: float | None
    match_type: Literal["literal", "semantic"] | None
    node_refs: list[NodeRef]
    paper_a_usage: str
    paper_b_usage: str
    dataset_a: str | None
    dataset_b: str | None
    evidence_summary: str | None
    # method: computed alias → overlap_label

class ClaimEvolutionPoint(PatrolPoint):
    mode: Literal["claim_evolution"]
    research_question: str
    paper_a_claim: str | None
    paper_b_claim: str | None
    evolution_type: EvolutionType | None  # inherit | contradict | refined
    problem_fit_score: int | None         # 0-100
    evidence_summary: str | None

class PatrolInsight(BaseModel):
    ...
    structured_points: Sequence[
        Annotated[
            ContradictionPoint | LensClashPoint | MethodOverlapPoint | ClaimEvolutionPoint,
            Field(discriminator="mode"),
        ]
    ]
```

### 5.4 Patrol 混合 Context

Patrol 在构造 context 时，除了图谱节点，还应召回两篇论文的关键 chunks（如 Thesis / Method / Dataset 相关段落），提升 LLM 判断的事实依据。


### 5.4.1 RAG 降级契约（P9 / F8）

PatrolInsight 对外暴露一等公民降级字段（不以 summary 文本拼接为准）：

| 字段 | 说明 |
|------|------|
| is_degraded | RAG context 变薄时为 	rue |
| degradation_profile.reason_code | INDEX_NOT_READY / QUERY_FAILED / VECTOR_STORE_UNAVAILABLE |
| degradation_profile.affected_papers | 受影响 paper_id 列表 |
| meta.patrol_rag_context_degraded | **兼容镜像**（遗留消费方） |

PatrolRAGService.enrich_context 先做 VectorStore.exists 探针：索引缺失则跳过 query_chunks；连通性异常映射为 VECTOR_STORE_UNAVAILABLE。降级结果不入服务端进程 cache；HTTP Cache-Control: private, no-store。前端根据 is_degraded 展示 Warning Banner，并对 INDEX_NOT_READY 退避自愈轮询（10s/30s/60s）。

---

## 6. Phase 4 — 质量回归与金标评估

### 6.1 金标问题集

文件：`data/qa_golden_set.json`

每题结构：

```json
{
  "version": "2026-07-04",
  "allowed_recall_floor": 0.80,
  "items": [
    {
      "question": "论文为了验证 PCA 的有效性，采用了什么 Dataset 以及对照了什么 Baseline？",
      "paradigm": "STEM",
      "paper_id": "stem-001",
      "gold": {
        "nodes": ["n_method_pca", "n_dataset_x", "n_baseline_y", "n_metric_z"],
        "edges": ["e_used_in_01", "e_compares_to_02"],
        "paragraphs": ["p_methods", "p_results"],
        "required_patterns": ["0.89", "F1"],
        "forbidden_patterns": ["本研究通过复杂的方法"]
      }
    }
  ]
}
```

### 6.2 LLM-as-a-Judge

Judge 模型：`JUDGE_MODEL=kimi-k2.6`（与 `LLM_MODEL` 独立配置）。

评估指标：

| 维度 | 指标 | 阈值 | 性质 |
|---|---|---|---|
| 忠实度 | Hallucination Rate | == 0% | 🔴 硬门槛 |
| 忠实度 | Context Entailment | ≥ 90% | 🟡 基线 |
| 完整性 | Graph Element Recall | ≥ 80%（允许下调至 70% 并记录） | 🟡 基线 |
| 有用性 | Verbosity Rate | ≤ 15% | 🟡 基线 |
| 范式对齐 | Paradigm Aligned | == true | 🔴 硬门槛 |

Judge 输出 JSON：

```json
{
  "faithfulness": {
    "hallucination_rate": 0.0,
    "entailment_rate": 0.95
  },
  "completeness": {
    "graph_element_recall": 0.85
  },
  "directness": {
    "verbosity_rate": 0.08,
    "paradigm_aligned": true
  },
  "sentence_judgments": [
    {"sentence": "...", "label": "supported"}
  ]
}
```

### 6.3 回归脚本

`scripts/benchmark_qa.py`：
- 读取 `data/qa_golden_set.json`
- 对每个问题调用 `qa_stream`
- 调用 Judge 模型评估
- 输出 JSON report 到 `data/benchmark_reports/qa-{timestamp}.json`
- 记录每次 Judge 调用的 token 消耗与耗时到 `data/logs/evaluation.log`

### 6.4 CI 门禁

| 级别 | 触发条件 | 行为 |
|---|---|---|
| 🔴 红线 | Hallucination Rate > 0% | 阻塞合入 |
| 🟡 警告 | Recall < floor 或 Verbosity > ceiling | 放行，记录日志 |
| ⚪ 信息 | 其他 minor 波动 | 仅记录 |

### 6.5 金标维护

新增 `scripts/validate_golden_qa.py`：
- 遍历金标中的 `node_id` / `edge_id` / chunk ID
- 校验是否仍存在于 `data/graphs/` 样本、chunk manifest 与 mock 向量索引中
- 发现过期引用时 **exit 1**

**图谱 bootstrap（B8）** — 默认 **strict=True** + 内置样本静默 auto-seed：

```text
validate (strict) → paper 图谱存在? → 强校验 gold IDs
                  → 缺失且 hss-001/stem-001 → 静默 seed → 重试
                  → 缺失且未知 paper → exit 2
                  → --no-strict / --allow-skip（仅本地，CI 强制 strict）
```

| 标志 | 默认 | 说明 |
|------|------|------|
| `--strict` / `--no-strict` | strict | 未知 paper 图谱缺失是否阻断 (exit 2) |
| `--allow-skip` | off | `--no-strict` 别名；**CI 中无效** |
| `--no-auto-seed` | off | 禁用 hss-001/stem-001 静默自举 |
| `--verbose` | off | 打印 auto-seed 日志 |

```bash
# CI / 门禁（默认 strict + auto-seed）
uv run python scripts/validate_golden_qa.py --graph-dir ./data/graphs

# 本地：允许跳过尚未 ingest 的 paper
uv run python scripts/validate_golden_qa.py --no-strict
```

**Exit codes（CI 分层捕获）**：

| Code | 场景 | 含义 |
|------|------|------|
| 0 | 全部通过，或 `--no-strict` 下无损 SKIP | Success |
| 1 | 图谱已加载，金标 node/edge/chunk ID 缺失/过期 | Data Drift（金标过期） |
| 2 | 图谱/金标文件缺失且无法 auto-seed | Infrastructure（环境不健壮） |

**退出码优先级（混合失效矩阵）**：全量扫描金标后聚合判定 —
`Infrastructure (2) > Data Drift (1) > Success (0)`；同时存在 drift 与 infra 时返回 **2**。

---

## 7. 配置项汇总

```env
# ── ChromaDB ──────────────────────────────────────────────
CHROMADB_PATH=./data/chroma
CHROMADB_CHUNK_COLLECTION=paper_chunks
CHROMADB_ENTITY_COLLECTION=paper_entities
CHROMADB_RELATION_COLLECTION=paper_relations

# ── Chunking ──────────────────────────────────────────────
CHUNK_SIZE_TOKENS=512
CHUNK_OVERLAP_RATIO=0.20

# ── Retrieval ─────────────────────────────────────────────
RAG_TOP_K_CHUNKS=5
RAG_TOP_K_ENTITIES=5
RAG_TOP_K_RELATIONS=5
RAG_HYBRID_GRAPH_WEIGHT=0.5
RAG_HYBRID_CHUNK_WEIGHT=0.5

# ── HyDE（未来启用）────────────────────────────────────────
RAG_HYDE_ENABLED=false
RAG_HYDE_MODEL=                       # 空则使用 LLM_MODEL_PRIMARY

# ── Judge ─────────────────────────────────────────────────
JUDGE_MODEL=kimi-k2.6
JUDGE_TIMEOUT_SECONDS=120

# ── QA 召回基线 ───────────────────────────────────────────
QA_RECALL_FLOOR=0.80
QA_VERBOSITY_CEILING=0.15
```

---

## 8. 验收标准

### 8.1 Phase 1 验收

| # | 验收项 | 通过标准 |
|---|---|---|
| P1-1 | ChromaDB 依赖 | `uv sync` 通过，`import chromadb` 成功 |
| P1-2 | 三类索引构建 | 上传论文 ready 后，`paper_chunks` / `paper_entities` / `paper_relations` 均有该论文数据 |
| P1-3 | 统一向量查询 | `VectorStore().query_*` 返回 top-k chunks / entities / relations |
| P1-4 | re-extract 重建 | 调用 `POST /papers/{id}/reextract` 后旧索引全部删除并重建 |

### 8.2 Phase 2 验收

| # | 验收项 | 通过标准 |
|---|---|---|
| P2-1 | 尺度路由 | 摘要问题走 A 尺度，细节问题走 A+B 尺度 |
| P2-2 | 混合 Prompt | QA prompt 同时包含图谱实体/关系与原文片段 |
| P2-3 | 多类型 citation | SSE 输出 `citation` 事件含 `type=node` / `edge` / `chunk` / `page` |
| P2-4 | 细节问题回答 | STEM 细节问题答案中出现具体数值/数据集/指标 |
| P2-5 | HyDE 接口预留 | `HybridRetriever.retrieve` 支持 `query_transform` 与 `query_embedding` 参数 |
| P2-6 | 忠实度 | 金标集 Hallucination Rate == 0% |

### 8.3 Phase 3 验收

| # | 验收项 | 通过标准 |
|---|---|---|
| P3-1 | method_overlap 模式 | `POST /patrol` 新 mode 可用，返回结构化点 |
| P3-2 | claim_evolution 模式 | 同上 |
| P3-3 | 强类型 Schema | `PatrolInsight.structured_points` 使用 discriminated union |
| P3-4 | Patrol 混合 context | 构造 context 时消费向量 chunks |

### 8.4 Phase 4 验收

| # | 验收项 | 通过标准 |
|---|---|---|
| P4-1 | 金标文件 | `data/qa_golden_set.json` 存在且通过 schema 校验 |
| P4-2 | benchmark 脚本 | `uv run python scripts/benchmark_qa.py` 输出 report |
| P4-3 | Judge 解耦 | Judge 模型与 live LLM 不同 |
| P4-4 | 评估日志 | `data/logs/evaluation.log` 记录 token 与耗时 |
| P4-5 | validate 脚本 | `uv run python scripts/validate_golden_qa.py` 在金标过期时报错 |

---

## 9. 测试要求

新增测试文件：

```text
tests/rag/
├── __init__.py
├── test_chunking.py
├── test_indexing.py           # entity/relation 文本生成
├── test_vector_store.py       # ChromaDB 三类 collection CRUD
├── test_hybrid_retriever.py   # 统一召回 + HyDE hook
├── test_qa_router.py
└── test_qa_citation.py

tests/patrol/
├── test_method_overlap.py
├── test_claim_evolution.py
└── test_patrol_structured_points.py

tests/eval/
└── test_qa_golden_set.py
```

运行：

```bash
uv run pytest tests/rag/ -q
uv run pytest tests/patrol/ -q
uv run pytest tests/eval/test_qa_golden_set.py -q
uv run python scripts/benchmark_qa.py --dry-run
```

---

## 10. 与 P1 持久化的衔接

| RAG 数据 | 存储位置 | 说明 |
|---|---|---|
| chunk / entity / relation 向量化数据 | `data/chroma/`（ChromaDB） | 文件系统，可重建 |
| 元数据 | ChromaDB metadata | 不存关系库 |
| 论文元数据 | `papers` 表 | P1 提供 |
| 流水线状态 | `pipeline_runs` 表 | P1 提供 |

RAG 模块通过 `paper_id` 关联，不直接依赖 P1 的 DB 实现，但 P1 完成后可让 `VectorStore` 在 `re-extract` 时通过 repository 查询论文状态。

---

## 11. 风险与回退

| 风险 | 缓解 |
|---|---|
| ChromaDB 本地文件损坏 | chunks / entities / relations 均可从 `full_text` 与图谱 JSON 重建；定期清理 `data/chroma/` 即可 |
| Embedding 调用成本高 | 异步批量 embed；三类数据可并发 embed；缓存 per-paper embeddings |
| 实体/关系embedding质量差 | 描述文本优先使用 rationale + source_span；保留 A 尺度拓扑作为兜底 |
| QA 混合后延迟增加 | A 尺度仍快路径；B 尺度三类查询可并行；失败可降级为纯图谱 QA |
| Judge 模型不稳定 | Hallucination 判定失败时人工 review；记录完整上下文 |
| 金标维护成本高 | 预生成 + 人工校验 + validate 脚本 |

---

## 12. 参考文件

- `backend/graph/qa.py`
- `backend/graph/query.py`
- `backend/llm/embeddings.py`
- `backend/ingest/chunking.py`
- `backend/patrol/contradiction.py`
- `backend/patrol/lens_clash.py`
- `backend/schemas/patrol.py`
- `progress-v2.md` §3.3
