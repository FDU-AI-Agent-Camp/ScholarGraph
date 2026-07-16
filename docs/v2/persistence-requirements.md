# V2 持久化基座需求文档（P1）

> **目标**：将 `PaperService` 从内存单例改造为以关系型数据库为唯一状态真相源（Source of Truth），使服务重启后用户数据、流水线状态、warnings 不丢失。
> **范围**：后端 `backend/services/`、`backend/graph/nodes.py`、启动加载、fixture seed。
> **版本**：v0.4.0.x
> **负责人**：待定

---

## 1. 背景与现状

### 1.1 当前问题

`backend/services/paper_service.py` 当前维护大量内存字典：

```python
self._papers: dict[str, PaperDetail] = {}
self._status: dict[str, PaperStatusData] = {}
self._refined_classifier_input: dict[str, str] = {}
self._refined_head: dict[str, IngestHead] = {}
self._head_refine_warnings: dict[str, list[str]] = {}
self._classify_warnings: dict[str, list[str]] = {}
self._extract_warnings: dict[str, list[str]] = {}
self._preview_graphs: dict[str, UnifiedPaperGraph] = {}
self._preview_available: dict[str, bool] = {}
self._pdf_paths: dict[str, Path] = {}
```

后果：
- 后端重启后，文献列表回到 fixture seed，真实上传的 PDF/图谱成为孤儿文件。
- 无法横向扩展、无法做持久化巡检、无法恢复后台任务。

### 1.2 文件系统现状（保持不变）

| 数据 | 位置 | 持久化 |
|---|---|---|
| 原始 PDF | `UPLOAD_DIR`（默认 `./uploads/{paper_id}.pdf`） | ✅ |
| 知识图谱 | `GRAPH_DATA_DIR`（默认 `./data/graphs/{paper_id}.json`） | ✅ |
| head refine 结果 | `GRAPH_DATA_DIR/{paper_id}.head.json` | ✅ |

关系库只存**元数据与状态指针**，不存大文件内容。

---

## 2. 数据模型

### 2.1 最小表结构

使用 SQLAlchemy 2.0 风格声明。默认数据库 `sqlite:///./data/scholargraph.db`，生产可切 PostgreSQL。

#### `papers` 表

| 字段 | 类型 | 说明 |
|---|---|---|
| `paper_id` | `String(36), PK` | UUID |
| `title` | `String(500)` | 论文标题；上传时先用文件名占位 |
| `paradigm` | `String(10)` | `STEM` / `HSS` / `NULL` |
| `status` | `String(30)` | `pending` / `processing` / `ready` / `ready_with_warnings` / `failed` |
| `pdf_path` | `String(500)` | 相对路径或绝对路径 |
| `graph_path` | `String(500)` | 图谱 JSON 路径，ready 后写入 |
| `head_path` | `String(500)` | head refine JSON 路径 |
| `preview_available` | `Boolean` | MVP 骨架是否可预览 |
| `classification` | `JSON` | `ParadigmClassification` 原始 JSON |
| `graph_version` | `String(20)` | 图谱版本号，默认 `"1"`；重抽或 Schema 升级时递增 |
| `extractor_config_hash` | `String(64)` | 抽取配置/模型/Prompt 的哈希；用于判断是否需要重刷 |
| `created_at` | `DateTime, TZ` | UTC |
| `updated_at` | `DateTime, TZ` | UTC，任何状态变更更新 |

#### `pipeline_runs` 表（当前运行状态表）

> **定位**：本表为**当前运行状态表**，不是历史流水表。每篇论文仅保留一行最新状态，通过 `paper_id` 一对一关联 `papers`。LangGraph 节点更新进度时执行 UPSERT/覆盖写，避免表膨胀。
>
> 未来 P2 若需要结构化事件流，再额外引入追加型的 `pipeline_events` 表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `paper_id` | `String(36), PK, FK` | 一对一关联 papers |
| `stage` | `String(30)` | 当前 stage |
| `percent` | `Integer` | 0–100 |
| `message` | `String(1000)` | 用户可见消息 |
| `error_code` | `String(100)` | failed 时机器码 |
| `failed_during` | `String(30)` | 失败所在业务阶段 |
| `head_refine_warnings` | `JSON` | list[str]，累加产生 |
| `classify_warnings` | `JSON` | list[str]，累加产生 |
| `extract_warnings` | `JSON` | list[str]，累加产生 |
| `active_rag_run_id` | `String(64), NULL` | 当前生效的 RAG 索引 run id；`NULL` 表示从未索引，`""` 表示已清空 |
| `preview_graph` | `JSON, NULL` | 抽取预览图谱（`UnifiedPaperGraph` JSON）；finalize 后清空 |
| `created_at` | `DateTime, TZ` | 首次写入时间 |
| `updated_at` | `DateTime, TZ` | 最新更新时间 |

可选扩展（P2）：`pipeline_events` 表（只追加）记录结构化事件流。

### 2.2 Schema 约束

- `papers.status` 必须是 `PaperStatus` 枚举值之一。
- `pipeline_runs.stage` 必须是 `PipelineStage` 枚举值之一。
- `pipeline_runs.paper_id` 是主键且外键关联 `papers.paper_id`，一对一关系，级联删除（`CASCADE`）。
- **SQLite 外键必须显式开启**：默认 `PRAGMA foreign_keys=OFF`，需在 engine connect 事件中执行 `PRAGMA foreign_keys=ON;`，否则级联删除在 SQLite 下不生效。
- `papers.paradigm` 允许 `NULL`（分类前）。
- `papers.pdf_path` 非空。
- `papers.graph_version` 默认 `"1"`，`extractor_config_hash` 默认空字符串。

### 2.3 进程内临时态下沉（D6）

以下字段**不得**再驻留 `PaperService` 内存；重启后须从 DB / 磁盘恢复：

| 原内存字段 | 新真相源 | 读写约定 |
|---|---|---|
| `_active_run_id` | `pipeline_runs.active_rag_run_id` | `VectorStore` 经 `PaperService.get/set_active_run_id` 读写；`reextract` / `clear_ephemeral_pipeline_state` 置 `NULL` |
| `_preview_graphs` | `pipeline_runs.preview_graph` | LangGraph 预览节点 `save_preview_graph`；`pipeline_completion_service.finalize` 成功后 `clear_preview_graph` |
| `_refined_head` / `_refined_classifier_input` | `HeadStore` 磁盘 JSON | `PaperService` 每次穿透 `HeadStore.load()`，禁止本地 cache |
| `_bootstrapped` | `papers` 表计数 | `bootstrap()` 仅当 `SEED_DEMO_PAPERS=true` 且 `PaperRepository.is_empty()` 时 seed |

**生命周期**：

1. 上传 / 重抽：`reset_for_reextract` 末尾调用 `clear_ephemeral_pipeline_state`（清空 preview + active run id）。
2. RAG 全量索引：`VectorStore.replace_paper_index` 写入新 `run_id` 到 `active_rag_run_id`。
3. Pipeline finalize：正式图谱落盘后清空 `preview_graph`；`active_rag_run_id` 保留供检索过滤。

---

## 3. Repository 层接口

在 `backend/repositories/` 新建模块，先提供同步 + 异步两套接口（或统一 async）。

### 3.1 建议文件结构

```text
backend/repositories/
├── __init__.py
├── base.py              # SQLAlchemy engine/session 工厂
├── paper_repository.py  # papers 表 CRUD
└── pipeline_repository.py  # pipeline_runs 表 CRUD
```

#### `base.py` Engine 与 Session 约束

**Engine 初始化（SQLite）**：

```python
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = create_async_engine(
    "sqlite+aiosqlite:///./data/scholargraph.db",
    future=True,
    # aiosqlite 默认 BEGIN DEFERRED；写事务需强制 IMMEDIATE 避免锁升级冲突
    connect_args={"timeout": 30, "check_same_thread": False},
    isolation_level="AUTOCOMMIT",  # 由业务层显式控制事务，便于写操作使用 begin_immediate
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
```

**写事务使用 `begin_immediate()`**：

```python
async with async_session_factory() as session:
    async with session.begin():  # 对于 aiosqlite，推荐在 repository 层显式 begin_immediate
        ...
```

> **注意**：`sqlalchemy.ext.asyncio` 对 `begin_immediate` 的支持依赖驱动与版本。若默认 `session.begin()` 仍使用 `BEGIN DEFERRED`，可在 Repository 写操作前显式执行 `await session.execute(text("BEGIN IMMEDIATE"))`，确保写锁尽早获取，避免两个并发读取后同时 commit 导致的 `database is locked`。

**Session 生命周期约束**：
- 必须使用**短生命周期 AsyncSession**，禁止跨协程/跨后台任务共享同一个 session。
- FastAPI 请求处理函数中需要 DB 时，使用 `async with async_session_factory() as session:`。
- LangGraph 节点（包括 `extract_node` 触发的后台异步任务）中需要 DB 时，同样显式创建新 session。
- SQLite 在 WAL 模式下支持并发读，但同一时刻只允许一个写入连接；长生命周期 session 会长时间持有连接，导致后台任务与主请求争用锁（`database is locked`）。
- Repository 方法内部负责打开/关闭 session，禁止由调用方传入 session 跨越 await 边界。

### 3.2 `PaperRepository` 接口（草案）

```python
class PaperRepository:
    async def create(
        self,
        paper_id: str,
        title: str,
        pdf_path: str,
        status: PaperStatus = PaperStatus.PENDING,
    ) -> PaperDetail: ...

    async def get(self, paper_id: str) -> PaperDetail | None: ...

    async def list(
        self,
        *,
        paradigm: Paradigm | None = None,
        status: PaperStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PaperSummary], int]: ...

    async def update_status(
        self,
        paper_id: str,
        *,
        status: PaperStatus,
        stage: PipelineStage | None = None,
        percent: int | None = None,
        message: str | None = None,
    ) -> None: ...

    async def update_classification(
        self,
        paper_id: str,
        classification: ParadigmClassification,
    ) -> None: ...

    async def update_paths(
        self,
        paper_id: str,
        *,
        graph_path: str | None = None,
        head_path: str | None = None,
    ) -> None: ...

    async def mark_preview_available(self, paper_id: str) -> None: ...

    async def update_graph_version(
        self,
        paper_id: str,
        *,
        graph_version: str,
        extractor_config_hash: str | None = None,
    ) -> None: ...
```

### 3.3 `PipelineRepository` 接口（草案）

```python
class PipelineRepository:
    async def save_status(self, paper_id: str, data: PaperStatusData) -> None: ...
    async def get_latest(self, paper_id: str) -> PaperStatusData | None: ...
    async def record_warnings(
        self,
        paper_id: str,
        *,
        head_refine: list[str] | None = None,
        classify: list[str] | None = None,
        extract: list[str] | None = None,
    ) -> None: ...
```

**`record_warnings` 追加语义**：

LangGraph 多节点/异步执行中，warnings 是逐步产生的。`record_warnings` 必须实现「读取已有 → 去重追加 → 原子写回」：

```python
async def record_warnings(self, paper_id, *, head_refine=None, classify=None, extract=None):
    async with async_session_factory() as session:
        run = await session.get(PipelineRun, paper_id)
        existing_head = set(run.head_refine_warnings or [])
        existing_head.update(head_refine or [])
        run.head_refine_warnings = list(existing_head)
        # classify / extract 同理
        await session.commit()
```

禁止直接覆盖已有 warnings。

> **P1.5 优化项**：当前为 read-merge-write 模式。若未来出现多节点高并发同时写入 warnings（如多个后台提取分支并行），存在极小概率的 Lost Update 风险。届时应升级为数据库层行级锁：`await session.get(PipelineRun, paper_id, with_for_update=True)`，或在业务编排上保证同一 paper_id 的 warnings 写操作串行化。

---

## 4. 改造范围

### 4.1 `PaperService`

- 移除所有内存字典（`_papers`、`_status` 等），改为注入 `PaperRepository` 与 `PipelineRepository`。
- 保留 `HeadStore` / `GraphStore` 的磁盘读写逻辑（文件系统不变）。
- `seed_from_fixtures` 改为条件执行：仅当 `SEED_DEMO_PAPERS=true` 且 DB 为空时 seed。
- `_hydrate_head_refine_from_disk` 保留：从 `HeadStore` 加载 head JSON。

### 4.2 `PipelineStatusService`

- `start_processing`、`advance_stage`、`mark_ready`、`mark_ready_with_warnings`、`mark_failed` 全部写入 `pipeline_runs`。
- `save_status` 使用 **UPSERT 语义**：`paper_id` 存在则更新，`不存在则插入`，保持 `pipeline_runs` 每篇论文只有一行。
- 同时更新 `papers.status` / `papers.updated_at`。
- warnings 通过 `PipelineRepository.record_warnings` 追加，禁止覆盖。

### 4.3 LangGraph Nodes

`backend/graph/nodes.py` 各节点目前通过 `get_pipeline_status_service()` 写状态。改造后：
- 不需要直接改动 node 代码，只需确保 `PipelineStatusService` 内部写 DB。
- `extract_node` 中 `background_extraction_scheduled=True` 时，主流水线 END；后台任务仍需能更新 DB 状态。
- 后台任务（`extract_worker` 等）更新状态时，必须显式创建新的 `AsyncSession`，禁止复用主流水线 session。

### 4.4 `pipeline_completion_service.py`

- `PipelineCompletionService.finalize()` **唯一**调用 `GraphPersistenceService.save(graph)` 写磁盘 JSON，并接收返回的 `graph_path`。
- `complete_paper_pipeline()` 仅更新 `papers.graph_path`、最终 `status`、`graph_version` 与 `extractor_config_hash`；**禁止**再次 `GraphStore().save()`（D7 消除双写）。
- finalize 成功后 **仅** 通过事件总线发射 `PipelineFinalized(paper_id, full_text, graph)`；**禁止**在 LangGraph `store_node` 内直调 RAG 索引。

### 4.5 `PipelineFinalized` 事件契约（SSOT）

**发射点**：`complete_paper_pipeline()` 在图谱持久化与 `mark_ready*` 之后，调用 `EventBus.publish_sync(PipelineFinalized(...))`。

**载荷字段（冻结，勿随意增删）**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `paper_id` | `str` | 已完成建图的论文 ID |
| `full_text` | `str` | PyMuPDF 抽取的全文，供 RAG chunk 切分 |
| `graph` | `UnifiedPaperGraph` | 已写入 `GraphStore` 的图谱快照 |
| `page_break_offsets` | `list[int] \| None` | 归一化全文中的分页累积偏移（供 chunk 页码推断，可选） |

定义位置：`backend/events/types.py` → `PipelineFinalized`。

**消费方（事件驱动 SSOT）**：

- **当前（persistence-core 临时桩）**：`backend/events/pipeline_finalized_handlers.py` 内 `temporary_pipeline_finalized_rag_handler` 监听 `EventType.PIPELINE_FINALIZED`，记录结构化日志并委托 `RagIndexService.index_paper_for_rag_async()`，维持端到端可用性。
- **目标（组员 A / `feature/backend/rag-vector-store`）**：在 `backend/rag/handlers.py` 使用 `@on_event(EventType.PIPELINE_FINALIZED)` 注册生产 Handler，接管向量化逻辑。
- **合并策略**：rag-vector-store PR 合并时，由 persistence-core 负责人删除 `pipeline_finalized_handlers.py` 中的临时桩，避免双索引。

**已废弃**：`backend/graph/nodes.py` `store_node` 对 `_index_paper_for_rag_async` 的同步直调（D4 清理项）。

**功能可用性（临时桩契约审计 + 可观测性）**：

- 订阅入口调用 `validate_pipeline_finalized_payload()`（`backend/events/pipeline_finalized_contract.py`），强类型校验 `PipelineFinalized`：`paper_id` 在 DB 存在、`full_text` 非空、`graph` JSON 往返反序列化成功且拓扑完整（节点非空、边端点合法）。
- 发布端（`complete_paper_pipeline` 内 `publish_sync` 直前）打 `pipeline_finalized_publishing`；订阅端（临时 handler 第一行）打 `pipeline_finalized_consumed`。两条日志共享 `correlation_id`（当前等于 `paper_id`），可凭时间戳与内容判定事件通道端到端打通。

### 4.6 启动加载

- `PaperService.__init__` 不再从 fixture 直接注入内存，而是从 DB `SELECT` 全部 papers 列表。
- fixture seed 改为可选：
  ```python
  if settings.seed_demo_papers and await repo.is_empty():
      seed_from_fixtures(repo)
  ```

### 4.7 环境变量

```env
# 默认 SQLite；生产可改为 postgresql+asyncpg://...
DATABASE_URL=sqlite:///./data/scholargraph.db

# true: 启动时若 DB 为空则加载 docs/api/fixtures/papers-list.json
# false: 空库启动
SEED_DEMO_PAPERS=false
```

---

## 5. 迁移策略

### 5.1 技术选型

| 组件 | 选择 | 理由 |
|---|---|---|
| ORM | SQLAlchemy 2.0 | 团队已有 Python 基础；async 支持 |
| 驱动 | SQLite（dev）/ asyncpg（prod） | 默认零运维 |
| SQLite 连接参数 | `check_same_thread=False` + WAL 模式 + `PRAGMA foreign_keys=ON` | 提升并发读写并确保外键生效 |
| 写事务策略 | `BEGIN IMMEDIATE` | 避免 DEFERRED 锁升级冲突 |
| 迁移 | Alembic | 逐步演进 |

### 5.2 分阶段实施

1. **Phase 1：模型 + Alembic**
   - 创建 `backend/models.py` 或 `backend/db/models.py`
   - 初始化 Alembic：`alembic init alembic`
   - baseline migration

2. **Phase 2：Repository 层**
   - 实现 `PaperRepository`、`PipelineRepository`
   - 单元测覆盖 CRUD

3. **Phase 3：替换 PaperService**
   - 保留原接口，内部改调 repository
   - 同步修复 `pipeline_status_service`

4. **Phase 4：启动加载 + fixture**
   - `SEED_DEMO_PAPERS` 开关
   - 启动从 DB 加载

5. **Phase 5：集成测 + 回归**
   - 上传 → ready → 重启 → 列表仍在
   - `run_v1_ac_gates` 全绿

---

## 6. 验收标准

### 6.1 功能验收

| # | 验收项 | 通过标准 |
|---|---|---|
| A1 | 创建论文 | `POST /papers` 后 `papers` 表新增一行，状态 `pending` |
| A2 | 状态推进 | 流水线运行过程中 `pipeline_runs` 持续写入最新状态 |
| A3 | 终态持久 | `ready` 后 `papers.status=ready`，`graph_path` 非空 |
| A4 | 重启恢复 | 停止 uvicorn 再启动，`GET /papers` 仍能看到已上传文献 |
| A5 | 空库启动 | `SEED_DEMO_PAPERS=false` 时新启动服务列表为空 |
| A6 | fixture seed | `SEED_DEMO_PAPERS=true` 且 DB 为空时加载 4 篇 seed |

### 6.2 测试验收

```bash
# 新增/更新测试
uv run pytest tests/repositories/ -q
uv run pytest tests/integration/test_persistence_restart.py -q
uv run pytest tests/services/test_paper_service_bootstrap.py -q
uv run pytest tests/services/test_paper_ephemeral_db_state.py -q
uv run pytest tests/repositories/test_ephemeral_pipeline_invariants.py -q
uv run pytest tests/services/test_ephemeral_state_chaos.py -q
uv run pytest tests/services/test_paper_service_db.py -q

# D6 断电重启 + bootstrap 零污染（§2.3）
# - test_mid_pipeline_ephemeral_state_survives_crash_recovery
# - test_bootstrap_seed_without_singleton_reset_has_zero_pollution

# D6 深度边界（JSON 变更追踪 / 并发读 / 混沌生命周期）
# - test_preview_graph_inplace_mutation_not_persisted_without_flag_modified
# - test_preview_graph_extreme_topology_survives_restart
# - test_active_run_id_reads_nonblocking_under_concurrent_pipeline_writes
# - test_ephemeral_state_chaos_lifecycle_invariants

# D6 → RAG 下游契约（index_run_id SSOT 跨重启）
# - test_rag_index_run_id_contract_survives_hard_restart_mock_consumer
# - test_vector_store_index_run_id_filter_survives_hard_restart

# 回归
uv run pytest -q -m "not red"
uv run python scripts/check_backend.py
```

### 6.3 性能与约束

- DB 查询不阻塞 LangGraph 节点：使用 async session。
- **Session 短生命周期**：每次 DB 操作使用 `async with async_session_factory() as session:`，操作完立即释放连接；禁止缓存或跨协程复用 session。
- **SQLite 并发写入**：WAL 模式下支持一写多读，但同一时刻仍只有一个写入连接。高频进度更新通过 `pipeline_runs` 单行 UPSERT 最小化写入次数；后台任务与主请求各自持有独立连接，避免锁冲突。
- SQLite 单文件：`./data/scholargraph.db` 与 `data/graphs/`、uploads 同目录。
- 不向 API 暴露内部 paths（`pdf_path`、`graph_path`、`head_path`）。

---

## 7. 接口兼容性

- `GET /papers`、`GET /papers/{id}`、`GET /papers/{id}/status`、`POST /papers` 的**响应契约不变**。
- 前端无需修改。
- OpenAPI schema 字段不变，仅后端存储层替换。

---

## 8. 风险与回退

| 风险 | 缓解 |
|---|---|
| 改造面大导致回归 | 每阶段完成后跑 `scripts/check_backend.py`；repository 抽象允许双写验证 |
| SQLite 并发写入/锁冲突 | WAL 模式 + 短生命周期 session + `pipeline_runs` 单行 UPSERT；后台任务独立连接 |
| Session 跨协程复用导致 `database is locked` | Repository 内部管理 session；禁止将 session 注入 LangGraph 节点或后台任务 |
| 旧 fixture 与真实数据混淆 | `SEED_DEMO_PAPERS=false` 默认；seed 前先检查 DB 是否为空 |
| Alembic 初始迁移失败 | 开发环境可删除 `scholargraph.db` 重建；生产需手动 review |

---

## 9. 参考文件

- `backend/services/paper_service.py`
- `backend/services/pipeline_status_service.py`
- `backend/services/pipeline_completion_service.py`
- `backend/schemas/paper.py`
- `backend/config.py`
- `progress-v2.md` §3.2
