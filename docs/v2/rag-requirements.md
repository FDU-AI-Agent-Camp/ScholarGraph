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

### 3.6 写入时机

在 `pipeline_completion_service.finalize()` 成功后，异步触发索引构建：

```python
async def _index_paper_for_rag(
    paper_id: str,
    *,
    full_text: str,
    graph: UnifiedPaperGraph,
) -> None:
    store = VectorStore()
    await store.delete_by_paper(paper_id)  # 幂等：先清旧索引

    chunks = chunk_text(paper_id, full_text)
    entities = graph_to_entities(paper_id, graph)
    relations = graph_to_relations(paper_id, graph)

    await store.index_chunks(chunks)
    await store.index_entities(entities)
    await store.index_relations(relations)
```

注意：
- 不阻塞 `store_node` 返回 ready。
- 失败不导致流水线 failed，但写入 `extract_warnings: ["rag_index_failed"]` 并记录日志。
- 重新抽取（re-extract）时先 `delete_by_paper` 再重建。

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
HTTP / Benchmark → HybridRetriever.retrieve() → RetrievalContext
  ├─ nodes/edges     → Prompt {nodes}/{edges}   （RC 非空时唯一来源）
  └─ entities/relations/chunks → Prompt 向量段   （format_retrieval_context）
       ↓
qa_stream(..., retrieval_context=RC) → QaEngine._build_prompt()
```

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

输出结构：

```json
{
  "mode": "method_overlap",
  "method": "PCA",
  "paper_a_usage": "用于降维",
  "paper_b_usage": "用于特征选择",
  "dataset_a": "Dataset A",
  "dataset_b": "Dataset B"
}
```

#### `claim_evolution`

触发：两篇论文 `ResearchQuestion` 或 `Thesis` 相似，但结论不同。

**部署配置（live / 演示）**：RQ 对齐采用 TD-4 两阶段漏斗——双塔粗筛（`PATROL_CLAIM_RQ_COARSE_THRESHOLD`，默认 0.42）→ Cross-Encoder 精排（`PATROL_RERANK_THRESHOLD`，默认 0.60）。**需 `RERANKER_ENABLED=true` 且配置 `RERANKER_MODEL`**；默认 `.env.example` 中 `RERANKER_ENABLED=false` 会回退严格双塔阈值（中文 0.75 / 英文 0.55），与 CI 金标门禁行为不一致，易导致大量 `INSUFFICIENT_DATA`。启动后见 `GET /api/v1/health` 的 `patrol_note`。

输出结构：

```json
{
  "mode": "claim_evolution",
  "research_question": "...",
  "paper_a_claim": "...",
  "paper_b_claim": "...",
  "evidence_summary": "..."
}
```

### 5.3 强类型子 Schema

`backend/schemas/patrol.py` 当前 `PatrolInsight.structured_points` 为 `list[dict]`，需改为：

```python
class PatrolPoint(BaseModel):
    mode: Literal["contradiction", "lens_clash", "method_overlap", "claim_evolution"]

class ContradictionPoint(PatrolPoint):
    mode: Literal["contradiction"]
    point_a: str
    point_b: str
    conflict_type: str

class LensClashPoint(PatrolPoint):
    mode: Literal["lens_clash"]
    lens_a: str
    lens_b: str
    clash_aspect: str

class MethodOverlapPoint(PatrolPoint):
    mode: Literal["method_overlap"]
    method: str
    paper_a_usage: str
    paper_b_usage: str

class ClaimEvolutionPoint(PatrolPoint):
    mode: Literal["claim_evolution"]
    research_question: str
    paper_a_claim: str
    paper_b_claim: str

class PatrolInsight(BaseModel):
    ...
    structured_points: list[
        Union[ContradictionPoint, LensClashPoint, MethodOverlapPoint, ClaimEvolutionPoint]
    ] = Field(..., discriminator="mode")
```

### 5.4 Patrol 混合 Context

Patrol 在构造 context 时，除了图谱节点，还应召回两篇论文的关键 chunks（如 Thesis / Method / Dataset 相关段落），提升 LLM 判断的事实依据。

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
- 遍历金标中的 `node_id` / `edge_id`
- 校验是否仍存在于 `data/graphs/` 样本中
- 发现过期引用时抛出 Error，提示重刷

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
