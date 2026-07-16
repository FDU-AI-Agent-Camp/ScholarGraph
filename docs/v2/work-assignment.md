# V2 后端分工协作规范

> **团队规模**：1 位组长 + 4 位组员，共 5 人  
> **目标**：高效推进 P1 持久化基座与 RAG 四阶段任务  
> **分支策略**：每人负责一个 `feature/backend/xxx` 分支，组长承担最核心、任务量最大的分支（约 45%），其余 4 位组员分担剩余 55%  
> **设计原则**：分支间解耦、模块化；分支内部高内聚

---

## 1. 团队与分支总览

| 分支名 | 负责人 | 任务量 | 对应需求文档 | 核心职责 |
|---|---|---|---|---|
| `feature/backend/persistence-core` | **组长** | ~45% | `persistence-requirements.md` §3–§5 | 关系库持久化基座 + 事件总线：模型、Repository、PaperService 改造、PipelineFinalized 事件 |
| `feature/backend/rag-vector-store` | 组员 A | ~12.5% | `rag-requirements.md` §3 | RAG Phase 1：ChromaDB 接入、chunk/entity/relation 索引、VectorStore、事件监听 |
| `feature/backend/rag-hybrid-retriever` | 组员 B | ~12.5% | `rag-requirements.md` §4.1–§4.2 | RAG Phase 2 检索层：尺度路由、HybridRetriever、统一向量召回 |
| `feature/backend/rag-qa-evaluation` | 组员 C | ~17.5% | `rag-requirements.md` §4.3–§4.5、§6 | RAG Phase 2 生成层 + Phase 4：QA Prompt、SSE citation、Edge label、金标评估、LLM-as-a-Judge |
| `feature/backend/rag-patrol-enhance` | 组员 D | ~12.5% | `rag-requirements.md` §5 | RAG Phase 3：Patrol 新模式、强类型 Schema、混合 context |

```text
总任务量：100%
├── 组长（persistence-core）        45%
├── 组员 A（rag-vector-store）      12.5%
├── 组员 B（rag-hybrid-retriever）  12.5%
├── 组员 C（rag-qa-evaluation）     17.5%
└── 组员 D（rag-patrol-enhance）    12.5%
```

---

## 2. 分支详细说明

### 2.1 `feature/backend/persistence-core` — 组长

**为什么留给组长**：
- 这是 V2 的**底座工程**，所有 RAG 分支都依赖它提供的稳定 DB 状态与论文元数据。
- 改造面最大：涉及 `PaperService`、`PipelineStatusService`、LangGraph nodes、启动加载、fixture seed、集成测试。
- 需要保证向后兼容（API 契约不变）和重启恢复等关键验收。

**范围**：
- `backend/db/models.py`：`papers` / `pipeline_runs` SQLAlchemy 模型
- `backend/db/base.py`：engine、session factory、WAL、begin_immediate、外键开启
- `backend/repositories/`：`PaperRepository`、`PipelineRepository`
- `backend/services/paper_service.py`：从内存 dict 迁移到 repository
- `backend/services/pipeline_status_service.py`：DB 化 + UPSERT + warnings 追加
- `backend/services/paper_fixture_seed.py`：`SEED_DEMO_PAPERS` 条件化
- `backend/services/pipeline_completion_service.py`：写 `graph_version` / `extractor_config_hash`，并在 finalize 成功后**发出 `PipelineFinalized` 事件**
- `backend/events/`：轻量级事件总线 + `PipelineFinalized` 事件定义
- Alembic 初始迁移
- 集成测试：上传 → ready → 重启 → 列表仍在

**事件驱动设计**：
- 组长只负责在 `pipeline_completion_service.finalize()` 成功后发出 `PipelineFinalized(paper_id, full_text, graph)` 事件。
- 严禁组员 A 直接修改 `pipeline_completion_service.py`；组员 A 通过监听该事件触发向量化。
- 事件总线可用最简实现：`asyncio.Queue` + 一组 `@on_event(EventType)` 装饰器，或用 FastAPI `BackgroundTasks` 的发布订阅封装。

**输入**：现有内存版 `PaperService`、Pydantic schemas
**输出**：DB 为唯一状态真相源，API 契约不变
**依赖**：无（最先开工）
**验收**：`tests/repositories/`、`tests/integration/test_persistence_restart.py` 全绿

---

### 2.2 `feature/backend/rag-vector-store` — 组员 A

**范围**：
- `pyproject.toml` 增加 `chromadb`
- `backend/rag/chunking.py`：文本切分
- `backend/rag/indexing.py`：entity/relation 描述文本生成
- `backend/rag/models.py`：`PaperChunk`、`PaperEntity`、`PaperRelation` 及返回模型
- `backend/rag/vector_store.py`：ChromaDB 三 collection 封装
- `backend/rag/handlers.py`：监听 `PipelineFinalized` 事件，异步触发 `_index_paper_for_rag`
- **禁止**：修改 `backend/services/pipeline_completion_service.py`
- 单测：`tests/rag/test_chunking.py`、`tests/rag/test_indexing.py`、`tests/rag/test_vector_store.py`

**输入**：`PipelineFinalized` 事件（含 `paper_id`, `full_text`, `graph`）、embedding client
**输出**：`VectorStore` 提供 `index_*` / `query_*` / `delete_by_paper` 接口
**依赖**：不强制依赖 P1；可在现有内存 `PaperService` 上测试；P1 完成后对接 repository
**验收**：上传论文 ready 后，三 collection 均有数据；re-extract 可重建

---

### 2.3 `feature/backend/rag-hybrid-retriever` — 组员 B

**范围**：
- `backend/rag/qa_router.py`：问题尺度判定（硬规则）
- `backend/rag/hybrid_retriever.py`：统一向量召回 + A 尺度图谱子图
- `backend/rag/models.py`：`RetrievalContext`（如组员 A 未定义则补充）
- 单测：`tests/rag/test_qa_router.py`、`tests/rag/test_hybrid_retriever.py`

**关键约束**：
- 必须使用 ChromaDB `where={"paper_id": paper_id}` 硬过滤
- 三类 collection 独立 Top-K，不做跨品类 distance 融合
- 预留 HyDE 接口：`query_transform`、`query_embedding`

**输入**：`question`、`paper_id`、`UnifiedPaperGraph`、`VectorStore`
**输出**：`RetrievalContext`（nodes/edges/entities/relations/chunks/scale）
**依赖**：`rag-vector-store` 完成后 rebase/merge
**验收**：摘要问题走 A 尺度，细节问题同时召回三类结果

**实现说明（与 develop SSOT 对齐，2026-07）**：

| 主题 | 实际约定 |
|------|----------|
| 问题尺度 | `QuestionScale.SUMMARY` / `DETAIL` / `VERIFICATION`；历史别名 `skeleton` 经 `coerce_question_scale()` 映射为 `SUMMARY` |
| 向量命中落位 | `entities` / `relations` / `chunks` 独立写入 RC，由 `format_retrieval_context` 注入 Prompt；**不** merge 进 `nodes/edges` |
| `scale` 参数 | 由 `qa_retrieval._load_graph_for_retrieval` 判定后**必填**传入 `HybridRetriever.retrieve()` |
| 跨论文问题 | `QuestionScale.CROSS_PAPER` 在 HTTP 入口由 `qa_deps.verify_question_scale` 返回 400，**不**进入 retriever |
| 降级子图 | `qa_retrieval` 预计算 subgraph 一次，超时/向量库故障时复用，避免重复 `GraphQuery` |

---

### 2.4 `feature/backend/rag-qa-evaluation` — 组员 C

**为什么 QA 评估也交给组员 C**：
- QA 生成层与 QA 评估层是研发闭环：谁写 Prompt 和生成流，谁最清楚应该用什么指标、什么金标来验证效果。
- 避免组员 D 在 Week 4 被组员 C 的进度阻塞。

**范围**：
- `backend/graph/qa.py`：接入 `HybridRetriever`、解析新 citation 语法
- `backend/prompts/qa.md`：扩展为包含 entity/relation/chunk 的混合 Prompt
- SSE `citation` 事件扩展：`type=node|edge|chunk|page`
- Edge citation label 自动拼接：`"{source_label} → {target_label}"`
- `data/qa_golden_set.json`：金标问题集（至少 10 题）
- `scripts/benchmark_qa.py`：QA 回归脚本
- `scripts/validate_golden_qa.py`：金标 ID 校验脚本
- 单测：`tests/rag/test_qa_citation.py`、`tests/graph/test_qa.py` 更新、`tests/eval/test_qa_golden_set.py`

**输入**：`RetrievalContext`、原始问题、金标问题集
**输出**：SSE 流式回答 + 多类型 citation 事件 + QA benchmark report
**依赖**：`rag-hybrid-retriever` 完成后 rebase/merge
**验收**：STEM 细节问题答案出现具体数值/数据集；citation 事件含 chunk/page/edge；金标集 Hallucination Rate == 0%

---

### 2.5 `feature/backend/rag-patrol-enhance` — 组员 D

**范围**：
- `backend/patrol/method_overlap.py`：新模式
- `backend/patrol/claim_evolution.py`：新模式
- `backend/schemas/patrol.py`：强类型 `structured_points` discriminated union
- `backend/patrol/service.py`：混合 context 召回（消费 `VectorStore`）
- 单测：`tests/patrol/test_method_overlap.py`、`tests/patrol/test_claim_evolution.py`、`tests/patrol/test_patrol_structured_points.py`

**输入**：两篇图谱、`VectorStore`
**输出**：结构化 Patrol 报告
**依赖**：`rag-vector-store` 完成后可并行启动
**验收**：新 Patrol 模式可用；返回强类型 `structured_points`

---

## 3. 协作规范

### 3.1 分支管理

```text
main
  └── develop
        ├── feature/backend/persistence-core        (组长)
        ├── feature/backend/rag-vector-store        (组员 A)
        ├── feature/backend/rag-hybrid-retriever    (组员 B)
        ├── feature/backend/rag-qa-evaluation       (组员 C)
        └── feature/backend/rag-patrol-enhance      (组员 D)
```

- 所有分支从 `develop` 切出。
- 不允许直接向 `develop` push，必须通过 PR/MR。
- 每个 feature 分支生命周期内保持与 `develop` 的定期同步（rebase），避免长期偏离。

### 3.2 开发顺序与依赖节奏

```text
Week 0:   契约冻结会（30 分钟）
          组员 A/B/C 共同确定 backend/rag/models.py 中 PaperChunk / PaperEntity / PaperRelation / RetrievalContext 字段
          空壳 commit 提到 develop，作为后续分支的基准

Week 1–2: persistence-core（组长）率先开工
          组员 A 并行开始 rag-vector-store（不依赖 DB）

Week 2–3: persistence-core 合入 develop
          rag-vector-store 合入 develop

Week 3–4: rag-hybrid-retriever（组员 B）基于 develop 开发

Week 4–5: rag-qa-evaluation（组员 C）基于 develop 开发

Week 5–6: rag-patrol-enhance（组员 D）基于 develop 开发

Week 6:   全部分支合入 develop，跑 `scripts/check_backend.py` + 金标回归
```

### 3.3 接口契约与解耦

**跨分支接口必须在代码中显式约定**，避免口头约定：

| 提供方 | 消费方 | 接口 |
|---|---|---|
| `persistence-core` | 全员 | `PaperRepository`、`PipelineRepository` |
| `persistence-core` | `rag-vector-store` | `PipelineFinalized` 事件 |
| `rag-vector-store` | `rag-hybrid-retriever` | `VectorStore.query_chunks/entities/relations` |
| `rag-hybrid-retriever` | `rag-qa-evaluation` | `HybridRetriever.retrieve(...) -> RetrievalContext` |
| `rag-vector-store` | `rag-patrol-enhance` | `VectorStore.query_*` |

**解耦原则**：
- 消费方通过接口调用，不直接读取提供方的内部数据结构。
- 若接口未就绪，使用 Mock/Fake 实现占位，不要阻塞开发。
- 接口变更需同步更新契约文档并通知相关同学。

### 3.4 提交规范

遵循仓库已有的 Conventional Commits：

```text
feat(persistence): add SQLAlchemy models for papers and pipeline_runs
feat(rag): implement VectorStore for chunks, entities, relations
fix(rag): enforce where filter on ChromaDB queries
test(persistence): add restart-recovery integration test
```

- 一个 commit 只做一件事。
- 提交前必须跑 `uv run ruff check backend tests` 与 `uv run ruff format --check backend tests`。
- 涉及类型变化时跑 `uv run pyright backend`。

### 3.5 PR 与 Code Review

| 分支 | Reviewer 要求 |
|---|---|
| `persistence-core` | 至少 1 位组员 review + 组长自己 double-check 关键状态机逻辑 |
| `rag-*` | 组长必须 review；相关上游分支负责人建议 review |

PR 描述模板：

```markdown
## 变更范围
- 修改了哪些文件
- 对应需求文档的哪个章节

## 依赖关系
- 依赖上游分支：xxx
- 阻塞下游分支：xxx（如无则写“无”）

## 测试
- 新增/更新了哪些测试
- 运行命令与结果

## 兼容性
- 是否改变 API 契约？是/否
- 是否需要前端同步修改？是/否
```

### 3.6 PR 前验收 Gate

每个分支提交 PR 前必须通过以下两项，缺一不可。

#### ① 回归测试通过

```bash
# 全量回归（默认 CI 集）
uv run pytest -q -m "not red and not live_mineru and not live_grobid and not live_benchmark"

# 本分支新增/修改的模块必须补充对应单测，并单独通过
uv run pytest tests/<对应模块>/ -q
```

要求：
- 不得有失败的测试。
- 新增代码必须有对应单元/集成测试覆盖，核心逻辑覆盖率建议 ≥ 80%。
- 若修改了公共接口，必须同步更新调用方测试。

#### ② 代码静态检查通过 + 重要坏味道清理

```bash
uv run ruff check backend tests scripts
uv run ruff format --check backend tests scripts
uv run pyright backend
```

除工具检查全绿外，还需人工 review 并清理以下**重要代码坏味道**（参考 `AGENTS.md`）：

| 坏味道 | 示例 | 要求 |
|---|---|---|
| 过长函数 | 一个函数超过 50 行 | 拆分为单一职责小函数 |
| 过长类 | 一个类承担多种职责 | 按职责拆分或抽取 mixin |
| 重复代码 | 相同/相似逻辑出现 2 次以上 | 抽取公共函数/常量 |
| 魔法值 | 硬编码数字/字符串 | 定义为具名常量 |
| 无意义命名 | `data`、`x1`、`theList` | 使用语义化命名 |
| 缺少类型注解 | 公共函数无参数/返回值类型 | 补全类型签名 |
| 裸 `try/except` | `except:` 或 `except Exception:` 无处理 | 捕获具体异常，记录日志或抛出自定义错误 |
| 未使用的导入/变量 | ruff F401/F841 | 删除 |
| 深层嵌套 | 超过 3 层 if/for/while | 使用卫语句或提前返回 |
| 上帝类 | `PaperService` 式大类继续膨胀 | 新代码避免；旧代码改造时逐步拆分 |

审查方式：
- 工具自动化：ruff + pyright 必须在 CI 中全绿。
- 人工检查：PR reviewer 对照上表逐条扫读，发现坏味道在 PR 内解决，不带到 develop。

全部 5 个分支合入 develop 后，额外执行：

```bash
uv run python scripts/check_backend.py
uv run python scripts/benchmark_qa.py --dry-run
```

---

## 4. 沟通机制

### 4.1 每日同步（15 分钟）

每人回答：
1. 昨天完成了什么？
2. 今天计划做什么？
3. 是否被阻塞？需要谁协助？

### 4.2 阻塞升级

- 接口未就绪 → 找接口提供方负责人
- 技术方案争议 → 组长拍板
- 需求理解不一致 → 回到 `docs/v2/*.md` 对文档做澄清修改

### 4.3 文档同步

- 任何接口变更必须同步更新 `docs/v2/rag-requirements.md` 或 `docs/v2/persistence-requirements.md`。
- 实现细节（如具体函数签名）可在代码 docstring 中补充，不需要每次同步到需求文档。

---

## 5. 风险与兜底

| 风险 | 影响分支 | 缓解 |
|---|---|---|
| `persistence-core` 延期 | 全员 | 组长优先投入；RAG 分支先用内存服务 Mock 开发 |
| `rag-vector-store` 接口不稳定 | `rag-hybrid-retriever`、`rag-patrol-enhance` | 接口冻结后下游再开工；变更需发通知 |
| ChromaDB 本地文件冲突 | `rag-vector-store` | 每人本地使用不同 `CHROMADB_PATH` 或在测试中使用临时目录 |
| 金标准备不足 | `rag-qa-evaluation` | 先用已有 corpus 3 篇论文扩展，不足再补充 |
| 多人同时修改 `backend/graph/qa.py` | `rag-qa-evaluation` | 提前沟通改动范围；小步提交 |
| `backend/rag/models.py` 契约未冻结 | A/B/C 之间 | Week 0 开 30 分钟契约会；空壳 commit 后禁止随意改字段 |
| 事件总线实现过重 | 组长/A 之间 | 使用最简发布订阅，禁止引入复杂消息队列 |

---

## 6. 参考文件

- `docs/v2/persistence-requirements.md`
- `docs/v2/rag-requirements.md`
- `docs/v2/README.md`
- `AGENTS.md` §9 Conventional Commits
