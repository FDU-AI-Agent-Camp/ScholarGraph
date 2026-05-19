# 黄金微语料集（V1）

V1 评测与 Demo 固定使用 **3 篇**论文：1 篇 STEM + 2 篇 HSS（主题可对齐、理论视角可冲突）。

## 登记模板

| paper_id | 范式（人工） | 标题 | 作者/年份 | 文件路径 | 备注 |
|----------|--------------|------|-----------|----------|------|
| `stem-001` | STEM | *待填* | | `data/corpus/stem-001.pdf` | 建议：大模型 / Agent 框架类 |
| `hss-001` | HSS | *待填* | | `data/corpus/hss-001.pdf` | 与 hss-002 同一议题 |
| `hss-002` | HSS | *待填* | | `data/corpus/hss-002.pdf` | 与 hss-001 理论视角形成张力 |

## 选题建议（来自 README）

- **STEM**：熟悉方向的 Agent / LLM 论文，便于核对指标、基线、实验设定节点。
- **HSS**：两篇围绕**同一社会热点或历史议题**（例：AI 与零工经济劳动者心理），一篇偏乐观、一篇偏批判，便于 **Lens Clash**。

## 版权与存储

- PDF 默认 **不提交** 到 Git（体积与版权）；在 `.gitignore` 已忽略 `data/corpus/*.pdf` 时，于团队网盘或课程仓库另行分发。
- 可提交：提取后的 `.txt`（若课程允许）或仅提交 `corpus.md` 元数据。

## 完成定义

- [ ] 三篇 PDF 路径可访问
- [ ] `docs/v1/eval/classifier_labels.csv` 人工范式标签已填
- [ ] `scripts/extract_text.py` 对三篇均能导出文本
