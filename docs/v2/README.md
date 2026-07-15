# ScholarGraph V2 文档目录

> 本目录存放 **V2 阶段** 的核心需求与设计文档。
> V2 阶段重点解决两大问题：
> 1. **持久化基座（P1）**：用关系型数据库替代内存单例，使服务可恢复、可扩展。
> 2. **多尺度混合 RAG（`feature/backend/rag`）**：在图谱骨架之外引入原文片段向量召回，提升 QA 与 Patrol 的细节忠实度。

---

## 文档清单

| 文档 | 主题 | 阅读顺序 |
|---|---|---|
| [`persistence-requirements.md`](persistence-requirements.md) | 持久化基座需求：数据模型、repository 接口、改造范围、验收标准 | **第 1 本** |
| [`rag-requirements.md`](rag-requirements.md) | RAG 四阶段任务：ChromaDB 基础设施、混合 QA、Patrol 增强、金标评估 | **第 2 本** |
| [`work-assignment.md`](work-assignment.md) | 团队分工协作规范：5 个 feature 分支、负责人、依赖节奏、PR 流程 | **第 3 本** |

---

## V2 阶段目标

```text
V1（已完成）
  ├── PDF 双路摄入
  ├── 双范式分类
  ├── Chunked Two-Phase 抽取
  ├── 图谱 QA（A 尺度）
  └── Patrol 基础模式

V2（当前阶段）
  ├── P1 持久化底座          ← 先完成或并行
  │     └── SQLite/PostgreSQL 替代内存单例
  ├── RAG Phase 1            ← B 尺度基础设施
  │     └── ChromaDB + chunking + embedding
  ├── RAG Phase 2            ← 混合 QA
  │     └── 图谱 + 原文片段 + 页码引用
  ├── RAG Phase 3            ← Patrol 增强
  │     └── method_overlap / claim_evolution + 强类型 Schema
  └── RAG Phase 4            ← 质量回归
        └── 金标 QA + LLM-as-a-Judge
```

---

## 如何开始

### 如果你是后端开发

1. 先读 [`persistence-requirements.md`](persistence-requirements.md) §3–§5，理解数据模型与 repository 接口。
2. 再读 [`rag-requirements.md`](rag-requirements.md) §3，理解 `backend/rag/` 模块结构。
3. 根据当前 sprint 选择任务：P1 持久化 或 RAG Phase 1。

### 如果你是前端开发

- V2 阶段前端改动较小：
  - P1 完成后无需改动（API 契约不变）。
  - RAG Phase 2 需要扩展 citation 渲染：支持 `type=chunk` / `type=page`。
  - RAG Phase 3 需要新增 Patrol `method_overlap` / `claim_evolution` 的展示组件。

### 如果你是测试/评估

- 参考 [`rag-requirements.md`](rag-requirements.md) §6 与 §8，准备金标问题集与 LLM-as-a-Judge 流程。

---

## 与 V1 文档的关系

- V1 文档位于 `docs/v1/`，描述已实现的能力与接口契约。
- V2 文档位于 `docs/v2/`，描述待实现的需求与架构升级。
- V2 实现完成后，相关设计决策应同步回写到 `docs/v1/design-spec.md` 与 `docs/v1/api-contract.md`。

---

## 状态

- **实现主线**：RAG Phase 1–4 + Patrol V2 后端已合；P13 双层 indexing watchdog / 孤儿线程世代撤销见 [`rag-requirements.md` §3.6](rag-requirements.md)。
- **当前前端焦点**：Part F（四模式 + `structured_points`）已合入 `develop`（PR #27）。后续以 RWW 图谱/问答 UX、文档同步等排期项为主（见本地 `problems-v2.md`，勿提交）。
- **版本号**：以根目录 `pyproject.toml` 为准（点分式 `M.S.F.B`）。
- **协作分工**：[`work-assignment.md`](work-assignment.md)。
