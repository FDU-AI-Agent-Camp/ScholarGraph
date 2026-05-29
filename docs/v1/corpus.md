# 黄金微语料集（V1）

V1 评测与 Demo 固定使用 **3 篇**论文：1 篇 STEM + 2 篇 HSS（主题可对齐、理论视角可冲突）。

## 本地目录（PDF 存放位置）

**仓库根目录**下统一放置（与 `scripts/run_pipeline.py`、`tests/graph/test_workflow_red.py` 路径一致）：

```text
ScholarGraph/
└── data/
    └── corpus/              ← 微语料 PDF 目录（已纳入 .gitignore 的 *.pdf）
        ├── stem-001.pdf     ← 必选文件名（勿改 paper_id 后缀）
        ├── hss-001.pdf
        └── hss-002.pdf
```

| 说明 | 内容 |
|------|------|
| **绝对路径示例** | `d:\Very_important_project_files\collaborate\ScholarGraph\data\corpus\` |
| **Git** | `data/corpus/*.pdf` 不提交；目录占位由 `data/corpus/.gitkeep` 跟踪 |
| **获取全文** | 从出版社 / arXiv / 课程网盘下载后，**重命名**为上表文件名再放入目录 |
| **校验** | 三文件就位后：`Test-Path data/corpus/stem-001.pdf` 等为 `True`（PowerShell） |

## 登记模板

| paper_id | 范式（人工） | 标题 | 作者/年份 | 文件路径 | 备注 |
|----------|--------------|------|-----------|----------|------|
| `stem-001` | STEM | ReAct: Synergizing Reasoning and Acting in Language Models | Yao et al. / 2022 | `data/corpus/stem-001.pdf` | Agent 推理+行动；arXiv:2210.03629；便于核对实验与基线节点 |
| `hss-001` | HSS | Algorithmic management in the gig economy: The politics of work visibility and invisibility | Lee et al. / 2015 | `data/corpus/hss-001.pdf` | 平台劳动、算法管理；偏**机制/政治经济**视角；与 hss-002 同议题「零工/平台劳动」 |
| `hss-002` | HSS | Good gigs: A typology of platform work and its consequences for workers | Wood et al. / 2019 | `data/corpus/hss-002.pdf` | 平台工作类型学；偏**类型划分与工人体验**；与 hss-001 形成 Lens Clash 张力 |

> **换篇约定**：若团队改用其他 PDF，请**保持 `paper_id` 与文件名不变**，只改本表「标题 / 作者 / 备注」，并同步 `docs/v1/eval/classifier_labels.csv` 的 notes。

## 选题建议（来自 README）

- **STEM**：熟悉方向的 Agent / LLM 论文，便于核对指标、基线、实验设定节点。
- **HSS**：两篇围绕**同一社会热点或历史议题**（本集默认：**平台劳动 / 零工经济**），理论或立场可形成对比，便于 **Lens Clash**。

## 版权与存储

- PDF 默认 **不提交** 到 Git（体积与版权）；在 `.gitignore` 已忽略 `data/corpus/*.pdf` 时，于团队网盘或课程仓库另行分发。
- 可提交：提取后的 `.txt`（若课程允许）或仅提交 `corpus.md` 元数据。

## 完成定义

- [ ] 三篇 PDF 路径可访问（见上表 `data/corpus/*.pdf`）
- [x] `docs/v1/eval/classifier_labels.csv` 人工范式标签已填
- [ ] `scripts/extract_text.py` 对三篇均能导出文本
