# V1 前端 UI 设计规格（Figma / 实现）

> **用途**：ScholarGraph V1 前端视觉与交互的权威设计参考，供 Figma 设计、Element Plus 主题定制与 FE 实现对齐。  
> **范围**：App Shell + 六主屏 + Design Tokens + 组件库 + Prototype 答辩路径。  
> **相关文档**：[tech-stack.md](./tech-stack.md)、[api-contract.md](./api-contract.md)、[collaboration.md](./collaboration.md) §3（页面 ↔ API）。

---

## 1. 设计决策（已确认）

| 维度 | 决策 |
|------|------|
| **气质** | C — 混合：首页 **Serif**，内页 **Sans** |
| **主色** | 学术青 `#0D6E6E` |
| **主题** | V1 仅 **浅色** |
| **详情页布局** | 左问答 + 右图谱 **双栏**（≥1024px） |
| **组件库** | **Element Plus 深度定制主题**（非替换为全新组件库） |
| **图谱节点** | V1 **统一圆角矩形**，不按范式区分形状 |
| **重点打磨** | Home、Detail（QA + citation 联动）、Graph |
| **设备优先级** | Desktop 优先（1440 基准），移动端 V1 仅标注折叠行为 |

**设计参数（参考 design-taste 三维）**

| 参数 | 值 | 含义 |
|------|-----|------|
| DESIGN_VARIANCE | 5～6 | 工作台稳定对称；Home / 巡检报告可略不对称 |
| MOTION_INTENSITY | 4～5 | 进度、SSE、citation 联动有过渡，不喧宾夺主 |
| VISUAL_DENSITY | 5～7 | 文献库 / 详情偏密；Home 可疏朗 |

**反模式（设计与实现均须规避）**

- 居中大 Hero + 三等分卡片（典型 AI 落地页）
- Inter 字体 + 紫色 / 蓝色渐变主色
- 用 emoji 作导航或功能图标
- 图谱过度装饰导致节点不可读
- 仅用颜色区分 HSS / STEM（须配合 Badge / 文案）

---

## 2. Figma 文件结构

```text
ScholarGraph V1
├── 00 — Design Tokens
├── 01 — Components
├── 02 — Screens
│   ├── Shell / AppLayout
│   ├── 01 Home
│   ├── 02 Papers（含 Upload）
│   ├── 03 Paper Detail（5 态）
│   ├── 04 Paper Graph（4 态）
│   └── 05 Patrol（4 态）
├── 03 — Prototype（答辩路径）
└── 04 — Handoff（EP 变量映射）
```

**画布基准**：Desktop `1440 × 900`（主设计稿）；另导出 `1280 × 800`、`1024 × 768` 适配帧。

**建议执行顺序**

1. 00 Design Tokens（Variables）
2. 01 Components（Badge、Button、Tag、Step、Graph Node）
3. 04 Graph / Default（定图谱视觉语言）
4. 03 Detail / QA-Citation-Active（定双栏 + 联动）
5. 01 Home（Serif 气质定调）
6. 02 Papers、05 Patrol
7. 03 Prototype
8. 04 Handoff

---

## 3. Design Tokens

### 3.1 色彩

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-primary` | `#0D6E6E` | 主按钮、链接、active 导航 |
| `--color-primary-hover` | `#0A5858` | 按钮 hover |
| `--color-primary-light` | `#E6F3F3` | 选中背景、Tag 浅底 |
| `--color-primary-muted` | `#B8DEDE` | 边框 hover、进度条轨道 |
| `--color-bg-page` | `#F8F9FB` | 页面背景 |
| `--color-bg-surface` | `#FFFFFF` | 卡片、侧栏、顶栏 |
| `--color-bg-canvas` | `#F1F5F9` | 图谱画布区背景 |
| `--color-border` | `#E5E7EB` | 分割线、卡片边框 |
| `--color-border-strong` | `#D1D5DB` | 输入框默认边框 |
| `--color-text-primary` | `#111827` | 标题、正文 |
| `--color-text-secondary` | `#6B7280` | 副文案、表头 |
| `--color-text-muted` | `#9CA3AF` | placeholder、hint |
| `--color-success` | `#059669` | ready 状态 |
| `--color-warning` | `#D97706` | 409、校验警告 |
| `--color-error` | `#DC2626` | failed、错误 alert |
| `--color-info` | `#2563EB` | processing、info banner |
| `--color-citation-active` | `#E11D48` | citation 高亮、图谱 active 节点 |
| `--color-hss-bg` | `#FEF3C7` | HSS Badge 背景 |
| `--color-hss-text` | `#92400E` | HSS Badge 文字 |
| `--color-stem-bg` | `#DBEAFE` | STEM Badge 背景 |
| `--color-stem-text` | `#1E40AF` | STEM Badge 文字 |

**阴影**

```text
shadow-sm:  0 1px 2px rgba(15, 23, 42, 0.05)
shadow-md:  0 4px 12px rgba(15, 23, 42, 0.08)
shadow-lg:  0 8px 24px rgba(15, 23, 42, 0.10)
```

**z-index 层级**

```text
z-0   页面背景
z-10  卡片
z-20  侧栏 / 顶栏（sticky）
z-30  图谱浮动工具栏
z-40  Drawer / 节点详情面板
z-50  Modal
```

### 3.2 字体

| Token | 字体 | 用途 |
|-------|------|------|
| `--font-serif` | **Noto Serif SC** | 仅 Home 大标题、Home 区块标题 |
| `--font-sans` | **Source Han Sans SC**（或 IBM Plex Sans SC） | 内页全部 UI |
| `--font-mono` | **JetBrains Mono** | paper_id、node_id、code |

| 样式名 | 字体 | 字号 | 字重 | 行高 | 用途 |
|--------|------|------|------|------|------|
| Display | Serif | 40px | 600 | 1.2 | Home 主标题 |
| H1 | Sans | 24px | 600 | 1.3 | 页面标题 |
| H2 | Sans | 18px | 600 | 1.4 | 区块标题 |
| H3 | Sans | 16px | 500 | 1.4 | 卡片标题 |
| Body | Sans | 14px | 400 | 1.6 | 正文 |
| Body-lg | Sans | 16px | 400 | 1.6 | 问答答案区 |
| Caption | Sans | 12px | 400 | 1.5 | hint、时间戳 |
| Mono | Mono | 13px | 400 | 1.5 | ID、代码 |

### 3.3 间距与圆角

```text
Spacing: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
Radius:  sm=4  md=6  lg=8  xl=12  full=9999
```

内容区最大宽度：`1280px`（Graph 页 canvas 区除外，full-bleed）。

### 3.4 Element Plus 主题映射

建议在 `frontend/src/styles/` 新增主题文件（如 `element-theme.scss`、`tokens.css`），覆盖至少：

- `el-button`、`el-menu`、`el-table`、`el-tag`、`el-progress`
- `el-alert`、`el-upload`、`el-input`、`el-card`、`el-page-header`、`el-collapse`

```scss
// element-theme.scss 示例
$colors: (
  'primary': (#0D6E6E, #0A5858, #E6F3F3, ...),
  'success': (#059669, ...),
  'warning': (#D97706, ...),
  'danger':  (#DC2626, ...),
);
$border-radius-base: 6px;
$font-family: 'Source Han Sans SC', sans-serif;
```

---

## 4. App Shell（全局框架）

**Frame 名**：`Shell / Desktop 1440`

### 4.1 结构

```text
总宽 1440 · 高 900（min-height 100vh）
├─ Aside 240px fixed
└─ Main flex-1
   ├─ Header 56px sticky
   └─ Content padding 24px 32px · max-width 1280（Graph 页除外 full-bleed）
```

**代码落点**：`frontend/src/components/layout/AppLayout.vue`

### 4.2 侧栏 Aside

| 元素 | 规格 |
|------|------|
| 背景 | `#FFFFFF`，右边框 1px `#E5E7EB` |
| Logo 区 | 高 72px，padding 20px 16px |
| 产品名 | Sans 18px/600 `#111827` |
| V1 标签 | 12px，bg `#E6F3F3`，text `#0D6E6E`，radius 4px，padding 2px 8px |
| Nav 项 | 高 44px，padding 12px 16px，icon 20px + 文字 14px |
| Nav active | 背景 `#E6F3F3`，文字 `#0D6E6E`，左侧 3px accent 条 |
| Nav hover | 背景 `#F8F9FB` |
| 导航项 | 工作台 `/` · 文献库 `/papers` · 共同体巡检 `/patrol` |
| 底部（可选） | 范式图例折叠卡：HSS / STEM 两色 Badge 示例 |

**图标**：Element Plus Icons — HomeFilled、Document、Search（巡检）

### 4.3 顶栏 Header

| 元素 | 规格 |
|------|------|
| 背景 | `#FFFFFF`，底边框 1px `#E5E7EB` |
| 左 | 面包屑（内页）或留空（Home） |
| 中 | 页面标题 Sans 16px/500（route meta.title） |
| 右 | 「API 文档 ↗」链接 14px `#0D6E6E`；可选后端状态点（绿 8px 圆点 +「已连接」） |

### 4.4 内容区

- 默认：`bg #F8F9FB`，内层 `page-card`（radius 12px，shadow-sm，padding 24px）
- **Graph 页**：去掉 page-card 包裹，画布 full-bleed 至 Main 右边缘

---

## 5. 页面 01 — Home `/`

**Frame**：`01-Home / Default · 1440×900`  
**代码落点**：`frontend/src/views/HomeView.vue`  
**气质**：Serif Display + 非对称布局（重点页）

### 5.1 布局

58% 左文 + 42% 右图，内容 max-width 1200，垂直 padding-top 48px。**禁止**居中 Hero + 三等分卡片。

### 5.2 左栏（自上而下）

| # | 元素 | 规格 |
|---|------|------|
| 1 | Eyebrow | Caption 12px `#0D6E6E`，tracking 0.08em：「AI AGENT · GRAPH RAG」 |
| 2 | 主标题 | **Noto Serif SC** 40px/600，两行：「解构论文逻辑，」「发现学术共同体」 |
| 3 | 副标题 | Body-lg 16px `#6B7280`，max-width 480px，说明 HSS/STEM 双范式 |
| 4 | CTA | 间距 12px；主「上传论文」→ `/papers`；次 Ghost「浏览文献库」 |
| 5 | 三步流程 | 横向 Step，间距 32px；图标圆 40px bg `#E6F3F3`：上传 PDF → 自动建图 → 问答·巡检 |
| 6 | 范式说明 | HSS / STEM Badge + Caption 一行差异说明 |

### 5.3 右栏 — 图谱视觉（装饰 mock）

| 元素 | 规格 |
|------|------|
| 容器 | 520×420，bg `#F1F5F9`，radius 16px，border 1px `#E5E7EB` |
| 内容 | 6～8 个统一圆角矩形节点 + 有向边 |
| 浮动卡片 | 2 个 insight 卡片叠在右下，shadow-md，模拟 Lens Clash |

### 5.4 底部快速入口（margin-top 64px）

2 列 asymmetric（左 60% / 右 40%）：

| 卡片 | 内容 |
|------|------|
| 左 · Lens Clash | H2 + 说明 +「查看巡检演示」→ `/patrol` |
| 右 · 多尺度问答 | H2 + 说明 +「打开示例论文」→ `/papers/hss-001` |

卡片：白底，padding 24px，radius 12px，hover shadow-md + border `#B8DEDE`。

### 5.5 交付 Frame

| Frame | 说明 |
|-------|------|
| `01-Home / Default` | 唯一态 |

---

## 6. 页面 02 — 文献库 `/papers`

**Frame**：`02-Papers / *`  
**代码落点**：`frontend/src/views/PapersView.vue`、`frontend/src/components/papers/PaperUpload.vue`

### 6.1 页头

| 元素 | 规格 |
|------|------|
| H1 | 「文献库」Sans 24px/600 |
| 副文案 | Body 14px `#6B7280`：「管理已上传论文，查看解构进度与图谱入口」 |

### 6.2 上传区 PaperUpload

| 元素 | 规格 |
|------|------|
| 区块标题 | H2「上传论文」 |
| 拖拽区 | 宽 100%，min-height 160px，border 2px dashed `#D1D5DB`，radius 12px，bg `#FAFBFC` |
| Hover | border `#0D6E6E`，bg `#E6F3F3` |
| 图标 | Upload 48px `#9CA3AF` |
| 主文案 | Body 14px：「拖拽 PDF 到此处，或 **点击上传**」 |
| Tip | Caption：「建议 ≤32MB · 上传后自动进入解构流水线」 |
| Uploading | 区内：progress + 文件名 Mono +「上传中…」 |
| 成功 | Toast success（标注即可） |

### 6.3 文献表格（margin-top 32px）

**区块标题**：H2「全部文献」+ 可选筛选（范式 / 状态，V1 可仅视觉）

| 列 | 宽 | 内容 |
|----|-----|------|
| 标题 | flex min 240 | 14px/500，ellipsis |
| 范式 | 88px | Badge HSS / STEM |
| 状态 | 100px | 色点 8px + 文字 |
| paper_id | 200px | Mono 12px `#6B7280`，可复制 icon |
| 操作 | 140px | Link「详情」；Link「图谱」仅 ready |

**表格样式**

- 表头 bg `#F8F9FB`，Caption 12px/500 `#6B7280`
- 行高 52px，stripe 偶数行 `#FAFBFC`
- hover 行 bg `#E6F3F3` 20% opacity

### 6.4 状态 Badge

| status | 色点 | 说明 |
|--------|------|------|
| pending | `#9CA3AF` | 已创建，未开始 |
| processing | `#2563EB`（可脉冲） | 流水线中 |
| ready | `#059669` | 可问答 / 图谱 |
| failed | `#DC2626` | 见 error_code |

### 6.5 Empty State

- 插画 120×120
- H3「还没有论文」
- Body「上传 PDF 开始自动解构」
- CTA 指向上传区

### 6.6 交付 Frame

| Frame | 说明 |
|-------|------|
| `02-Papers / Empty` | 空表 + Empty State |
| `02-Papers / Default` | mock：stem-001 ready、hss-001 processing、failed 各一行 |
| `02-Papers / Upload-Dragging` | 拖拽 hover |
| `02-Papers / Upload-Error` | INGEST_FAILED inline alert |

---

## 7. 页面 03 — 论文详情 `/papers/:id`

**Frame**：`03-Detail / *`  
**代码落点**：`frontend/src/views/PaperDetailView.vue`、`PaperStatusPanel.vue`、`PaperGraph.vue`（compact）

**布局**：左 45% 问答与元数据 · 右 55% 图谱预览（gap 24px，≥1024px）。重点页。

### 7.1 页头（全宽）

```text
← 返回文献库                                    [全屏图谱]
论文标题 H1 24px/600（最多 2 行）
Meta：paper_id mono · 范式 Badge · status Badge · 时间 caption
```

### 7.2 左栏模块

#### A. 元数据卡（可折叠）

| 字段 | 展示 |
|------|------|
| classification.paradigm | Badge |
| confidence | 百分比 + 细进度条 |
| reason | Body 14px，「查看分类依据」展开 |

#### B. 流水线进度 PaperStatusPanel

纵向 Stepper + 顶部 progress（高 8px，track `#E6F3F3`，fill `#0D6E6E`）：

| Step | 文案 |
|------|------|
| ingesting | 正在解析 PDF |
| classifying | 范式分类 |
| extracting | 抽取图谱 |
| storing | 写入存储 |
| ready | 建图完成 |

- active：accent + 脉冲点
- done：绿色 check
- failed：红色 + error_code + failed_during + message
- Caption：「每 2 秒自动刷新」

#### C. 多尺度问答

**区块标题**：H2「多尺度问答」

**未 ready**：Info Alert + Textarea / 按钮 disabled

**ready**

| 元素 | 规格 |
|------|------|
| Textarea | min-height 96px，placeholder 示例问题 |
| 按钮 | 主「提问」· 次「停止」（streaming）· Ghost「全屏图谱」 |
| 答案区 | bg `#FAFBFC`，border 1px，padding 16px，Body-lg，pre-wrap |
| SSE 光标 | streaming 末尾闪烁 `\|`，accent 色 |
| Citation 区 | label Caption「引用节点」 |
| Citation Tag | default bg `#F1F5F9`；**active** bg `#FFF1F2` border `#E11D48` text `#BE123C` |
| Tag 内容 | `{label}` + Mono `(node_id)` |

**联动（Prototype / 实现必做）**

- 点击 Tag → 右栏节点 active
- 点击节点 → 左栏 Tag active

### 7.3 右栏 — 图谱预览 compact

| 元素 | 规格 |
|------|------|
| 区块头 | H2「逻辑图谱预览」+ Link「全屏查看 →」 |
| 画布 | 设计稿高 480px（实现 compact **320px**，见 §12） |
| 背景 | `#F1F5F9`，radius 12px |
| Legend | 左下浮层，白底 shadow-sm |

### 7.4 交付 Frame

| Frame | 场景 |
|-------|------|
| `03-Detail / Processing` | Stepper 进行中，问答 disabled |
| `03-Detail / Ready-Empty` | ready，无问答 |
| `03-Detail / QA-Streaming` | 流式答案 + 1 citation |
| `03-Detail / QA-Citation-Active` | 多 citation，一个 active，节点高亮 |
| `03-Detail / Failed` | failed step + alert |

---

## 8. 页面 04 — 知识图谱 `/papers/:id/graph`

**Frame**：`04-Graph / *`  
**代码落点**：`frontend/src/views/PaperGraphView.vue`、`frontend/src/components/graph/PaperGraph.vue`

**布局**：Canvas-first，full-bleed。重点页。

### 8.1 页头（高 56px）

```text
← 返回详情    H1「逻辑图谱」    paper_id mono    范式 Badge    节点数/边数 caption
```

### 8.2 画布区（min-height 720px）

| 元素 | 规格 |
|------|------|
| 背景 | `#F1F5F9` |
| 布局算法 | dagre TB（自上而下） |

#### 浮动工具栏（顶部居中，margin-top 16px）

白底 shadow-md radius 8px padding 8px 12px：

- 放大 / 缩小 / 适应画布 / 重置布局（icon 36×36）
- 搜索节点 Input 200px（V1 可标注 future）
- 分隔线

#### Legend（左下 margin 16px）

Caption「节点类型」+ 色块 12×12 + 类型名；HSS / STEM 各一套 variant。

#### 节点详情 Drawer（宽 320px，点击节点）

| 字段 | 样式 |
|------|------|
| label | H3 |
| type | Badge |
| node_id | Mono + 复制 |
| snippet | Body（若有） |

### 8.3 节点视觉（统一圆角矩形）

| 状态 | 规格 |
|------|------|
| Default | min 80 max 140 宽，min 40 高，radius 8px，fill 按 type，stroke 1px |
| Hover | stroke 2px `#0D6E6E` |
| Active | stroke 3px `#E11D48`，fill 提亮，optional scale 1.05 |
| Label | Sans 12px 居中，最多 2 行 |

**HSS 节点类型色（示例）**

```text
Intellectual_Context  #78716C
Thesis                #0D6E6E
Sub_argument          #0891B2
Analytical_Lens       #7C3AED
Object_or_Data        #CA8A04
```

**STEM 节点类型色（示例）**

```text
Research_Question  #0D6E6E
Method             #2563EB
Dataset            #0891B2
Metric             #059669
Claim              #D97706
Evidence           #64748B
```

**边**：stroke `#94A3B8` 1px，箭头，label Caption 10px。

### 8.4 交付 Frame

| Frame | 场景 |
|-------|------|
| `04-Graph / Loading` | skeleton + 工具栏 disabled |
| `04-Graph / Default` | 完整 mock 15～25 节点 |
| `04-Graph / Node-Selected` | active 节点 + Drawer |
| `04-Graph / Deep-Link` | `?node=xxx` 进入即高亮 |
| `04-Graph / Error-409` | GRAPH_NOT_READY + CTA 回详情 |

---

## 9. 页面 05 — 共同体巡检 `/patrol`

**Frame**：`05-Patrol / *`  
**代码落点**：`frontend/src/views/PatrolView.vue`  
**API**：`POST /patrol`（见 [api-contract.md](./api-contract.md)）

### 9.1 页头

| 元素 | 规格 |
|------|------|
| H1 | 「共同体巡检」 |
| 副文案 | 「跨论文探测理论视角冲突与论点矛盾 · 需 2 篇 ready 论文」 |

### 9.2 配置区（白卡 padding 24px）

**论文选择**（设计优于逗号字符串输入）

| 元素 | 规格 |
|------|------|
| 标签 | 「论文 A」「论文 B」两列 |
| 输入 | Select / Autocomplete 或 Tag Input |
| 校验 | 恰好 2 篇；重复 ID 警告 |

**模式 Segmented Control**

| 选项 | 主标签 | 副标签 Caption |
|------|--------|----------------|
| lens_clash | Lens Clash | 分析视角冲突 · 适用 HSS |
| contradiction | Contradiction | 核心论点矛盾 · HSS/STEM |

选中：bg `#0D6E6E` text white。

**主按钮**：「运行巡检」，loading「分析中…」

**Hint**（可折叠）：Caption + Mono `uv run python scripts/run_patrol.py --seed-demo-graphs`

### 9.3 报告区

**摘要条**：mode Badge · generated_at · paper_ids mono

**Insight 卡片**（每 insight 一张）

| 区域 | 规格 |
|------|------|
| 头部 | title H3 + insight_id mono |
| 正文 | summary Body 14px pre-wrap |
| node_refs | 小表 paper_id · node_id mono · label；或 Tag 可跳转 graph `?node=` |

- Lens Clash：左边框 4px `#CA8A04`
- Contradiction：左边框 4px `#DC2626`

### 9.4 错误 Alert

| code | 标题 | CTA |
|------|------|-----|
| GRAPH_NOT_READY | 图谱未就绪 | → 文献库 |
| PATROL_INSUFFICIENT_DATA | 数据不足 | 换论文 |
| 校验 | 请输入恰好 2 个 paper_id | — |

### 9.5 交付 Frame

| Frame | 场景 |
|-------|------|
| `05-Patrol / Default` | 空表单 |
| `05-Patrol / Loading` | 按钮 loading |
| `05-Patrol / Report-LensClash` | 完整报告 + node_refs |
| `05-Patrol / Error-422` | 数据不足 |

---

## 10. 共享组件（Figma Components）

| 组件名 | Variants |
|--------|----------|
| `Button/Primary` | default, hover, active, loading, disabled |
| `Button/Ghost` | 同上 |
| `Badge/Paradigm` | HSS, STEM, unknown |
| `Badge/Status` | pending, processing, ready, failed |
| `Tag/Citation` | default, active |
| `Tag/NodeRef` | default, hover |
| `Input/Textarea` | empty, focused, disabled, error |
| `Upload/Dropzone` | idle, hover, uploading, error |
| `Table/Row` | default, hover, stripe |
| `Step/Pipeline` | pending, active, done, failed（5 steps） |
| `Alert/Inline` | info, warning, error, success |
| `Graph/Node` | by-type × default, hover, active |
| `Graph/Edge` | default |
| `Graph/Legend` | HSS, STEM |
| `Graph/Toolbar` | default |
| `Graph/NodeDrawer` | open |
| `Card/Insight` | lens_clash, contradiction |
| `EmptyState` | no-papers, no-graph, no-report |
| `Nav/Item` | default, active, hover |
| `Breadcrumb` | 2-level, 3-level |

---

## 11. 动效与无障碍

| 场景 | 动效 | 时长 |
|------|------|------|
| 页面切换 | fade + slide-up 8px | 200ms |
| SSE 答案 | 逐字 + 闪烁光标 | — |
| Citation 点击 | Tag + 图谱节点同步 | 150ms |
| 进度 stage | Step check | 250ms |
| 节点 hover | stroke 加粗，不位移 | 120ms |
| 列表加载 | Skeleton row ×5 | — |

- Focus ring：2px accent
- 正文对比度 ≥ 4.5:1
- `prefers-reduced-motion`：禁用图谱 entrance 动画

---

## 12. 响应式（V1 标注，非完整移动适配）

| 断点 | 行为 |
|------|------|
| ≥1280 | 标准双栏 Detail |
| 1024～1279 | Detail 50% / 50% |
| 768～1023 | Detail 单列：元数据 → 问答 → 图谱 |
| <768 | 侧栏 hamburger；Graph 顶栏 banner「建议使用桌面浏览器」 |

---

## 13. 状态矩阵（全页 Frame 清单）

| 页面 | Frame |
|------|-------|
| Shell | Default |
| Home | Default |
| Papers | Empty, Default, Upload-Dragging, Upload-Error |
| Detail | Processing, Ready-Empty, QA-Streaming, QA-Citation-Active, Failed |
| Graph | Loading, Default, Node-Selected, Error-409 |
| Patrol | Default, Loading, Report-LensClash, Error-422 |

合计约 **20 个 Screen Frame**。

---

## 14. Prototype 答辩路径

```text
Home
 └─[上传论文]→ Papers / Default
      └─[hss-001 详情]→ Detail / Processing
           └─→ Detail / QA-Citation-Active
                ├─[全屏图谱]→ Graph / Node-Selected
                └─[返回]→ Detail
 └─[Lens Clash 演示]→ Patrol / Report-LensClash
      └─[node_ref]→ Graph / Deep-Link
```

**必连动效**：Citation Tag click ↔ Graph 节点 active（Smart Animate 150ms）。

---

## 15. 代码对齐清单

| Figma | 代码路径 |
|-------|----------|
| Shell | `frontend/src/components/layout/AppLayout.vue` |
| Home | `frontend/src/views/HomeView.vue` |
| Papers + Upload | `frontend/src/views/PapersView.vue`、`PaperUpload.vue` |
| Detail 双栏 | `frontend/src/views/PaperDetailView.vue` |
| Graph | `frontend/src/views/PaperGraphView.vue`、`PaperGraph.vue` |
| Patrol | `frontend/src/views/PatrolView.vue` |
| Pipeline | `frontend/src/components/papers/PaperStatusPanel.vue` |
| 主题 | `frontend/src/styles/tokens.css`、`element-theme.scss`（待建） |
| 图谱工具 | `frontend/src/utils/paperGraph.ts` |

**图谱尺寸（设计 ↔ 代码）**

| 场景 | 设计稿 | 代码常量 |
|------|--------|----------|
| Detail compact 预览 | 可画 480px 易读 | `COMPACT_HEIGHT = 320` |
| Graph 全屏 | canvas min 720px | `DEFAULT_HEIGHT = 480`（容器内，可随 resize 扩展） |
| Active 高亮色 | `#E11D48` | G6 `state.active` 与 Citation Tag 一致 |

---

## 16. 变更流程

- 视觉 / 布局变更：FE 分支 `feature/frontend/design-*`，PR 附 Figma 链接或截图
- 若影响 OpenAPI 或页面契约：走 `[API RFC]`（见 [collaboration.md](./collaboration.md)）
- 本文档变更：PR 更新 `docs/v1/design-spec.md`，@FE Review

---

*最后更新：2026-05-30 · 决策：气质 C · 主色 #0D6E6E · 浅色 · Detail 双栏 · EP 深度定制*
