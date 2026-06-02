# ScholarGraph V1

V1 是首个**可演示、可评测**的纵向切片版本：从 PDF/文本输入到范式分流、单篇逻辑图谱、带引用的多尺度问答，并完成**至少一种**双文共同体巡检（HSS Lens Clash 或 STEM 矛盾探测），最后由 LangGraph 串联全链路。

## 版本目标

| 维度 | V1 要做到 | V1 不做 |
|------|-----------|---------|
| 范式 | STEM / HSS 双轨分类 + 分 Schema 抽取 | 跨范式自动对齐（Cross-paradigm Alignment） |
| 图谱 | 单篇 JSON 图谱 + 文件/SQLite 持久化 | Neo4j 生产级部署、大规模图库 |
| 问答 | 基于图谱遍历的多尺度 QA，答案含节点/边引用 | 纯 RAG 无结构兜底 |
| 巡检 | 2 篇论文 Demo（Lens Clash **或** STEM 矛盾） | 全库批量巡检、复杂调度 |
| Agent | LangGraph 状态机（分类 → 抽取 → 存储 → 问答/巡检） | 训练/微调、本地 GPU 推理 |
| 界面 | **Vue 3 工作台**（Vite + Pinia + G6）；Gradio 仅作备份 | 用户系统 / 登录注册 |
| 评测 | 微语料集 + 人工小样 + pytest 冒烟 | 大规模基准与自动标注流水线 |

## 与 README 里程碑对应

| README 阶段 | V1 包内阶段 | 代号 |
|-------------|-------------|------|
| 微语料 + 分类器 | P0–P2 | M0 |
| 单篇图谱入库 | P3 | M1 |
| 单篇多尺度问答 | P4 | M2 |
| 双文巡检 Demo | P5 | M3 |
| LangGraph 全链路 | P6 | M4 |

**任务分工**见 [work-assignment.md](./work-assignment.md)；**协作与接口**见 [collaboration.md](./collaboration.md)。

## 成功标准（Definition of Done）

1. 在**黄金微语料集**（1 STEM + 2 HSS）上，范式分类与人工标注一致。
2. 各范式至少 1 篇生成可解析的 `UnifiedPaperGraph` JSON，Schema 校验通过且无越界节点类型。
3. 对单篇至少 3 类问题（摘要 / 细节 / 验证）能返回**可复核**的图谱路径引用。
4. 双文巡检产出 1 份结构化报告（含范式、触发模式、涉及节点）。
5. `uv sync` + `uv run python scripts/check_backend.py` 通过；`uv run python scripts/run_v1_ac_gates.py` 与 `run_cp4_rehearsal.py --seed` 在合 develop 前可复跑。
6. 文档：`docs/v1/`、`README`、门禁脚本说明与当前实现对齐。

## 技术栈（既定）

- **前端**：Vue 3 + Vite + Pinia + Ant Design Vue / Element Plus + **AntV G6 v5**
- **后端**：Python + **uv** + **FastAPI** + LangGraph + Pydantic
- **交互**：REST + **SSE**（问答）+ **长轮询**（解构建图进度）

详见 [tech-stack.md](./tech-stack.md)、[任务分工](./work-assignment.md)、[协作规范](./collaboration.md)。

新人请先读 [onboarding.md](./onboarding.md)；提 PR 用 [pr-checklist.md](./pr-checklist.md)；后端模块交付见 [handoff-to-platform.md](./handoff-to-platform.md)。
