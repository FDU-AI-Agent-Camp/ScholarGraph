# 🛠 软件开发通用规范指南 (General Development Standards)

本指南定义了在不同编程语言环境下均应遵循的代码质量、安全性及测试标准，旨在构建可维护、健壮且易于协作的代码库。

---

## 1. 标识符与命名 (Naming Conventions)

* **语义优先**：变量名应准确表达含义。严禁使用 `theList`, `data`, `x1` 等无意义命名。
* **消除魔法值**：所有硬编码的数字或字符串必须定义为**具名常量**（如 `MAX_RETRY_COUNT`）。
* **风格统一**：严格遵守所属语言的主流风格：
    * **类/结构体**：通常使用 `PascalCase` (大驼峰)。
    * **函数/变量**：使用 `camelCase` (小驼峰) 或 `snake_case` (下划线)。
    * **常量**：全大写加下划线 `UPPER_SNAKE_CASE`。
* **类型暗示**：对于布尔值，建议使用 `is`, `has`, `can` 等前缀（如 `is_authenticated`）。

## 2. 结构与排版 (Layout & Formatting)

* **行宽限制**：单行代码建议不超过 **120 字符**，以适应现代显示器并支持分屏对比。
* **垂直留白**：
    * 逻辑相关的语句块之间不留空行。
    * 不同功能区（属性定义、初始化、公共方法、私有方法）之间必须空行分隔。
* **嵌套与缩进**：使用统一的缩进（推荐 4 空格或 2 空格），严格禁止混用 Tab 和空格。

## 3. 注释与文档 (Documentation)

* **解释“为什么”，而非“是什么”**：代码已经表达了“如何做”，注释应侧重于设计意图、特殊业务背景或复杂的算法权衡。
* **标记技术债**：使用标准的 `TODO:`（待办）或 `FIXME:`（需修复）标记。
* **API 文档化**：所有对外公开的接口（Public Methods/Exported Functions）必须包含文档注释（如 Javadoc, Docstring, TSDoc）。

## 4. 逻辑复杂度控制 (Complexity Management)

* **卫语句 (Guard Clauses)**：优先处理异常分支并提前返回，避免深层的 `if-else` 嵌套。
* **职责单一 (SRP)**：
    * **函数/方法**：一个函数只做一件事，长度通常建议控制在 50 行以内。
    * **类/模块**：避免“上帝类 (God Object)”，应根据职责拆分为小的协作单元。
* **完备性**：确保所有的分支（如 `switch` 的 `default`）都有明确的处理逻辑。

---

## 5. 防御性编程 (Defensive Programming)

* **显式处理空值**：
    * **返回集合**：若无结果，应返回空列表/集合，而非 `null/None/nil`。
    * **返回单值**：使用该语言的包装类（如 `Optional`, `Maybe`, `Option`）或明确的联合类型（如 `Type | null`）。
* **契约式验证**：
    * 对函数输入参数进行显式的空值检查或类型注解。
    * **绝不信任外部输入**：所有来自前端或第三方 API 的数据必须在入口处进行合法性校验（格式、长度、范围、业务规则）。
* **错误处理原则**：
    * **早抛出，晚捕获**：在检测到异常的第一时间抛出；在能够处理异常的顶层（如控制器或全局处理器）统一捕获。
    * **响应脱敏**：对终端用户返回易读的错误码和脱敏信息；在服务端日志中保留完整的堆栈信息用于复盘。

---

## 6. 单元测试要求 (Unit Testing)

* **最小单元验证**：测试应针对逻辑层（Service）和接口层（Controller/Router）进行。
* **依赖隔离 (Mocking)**：
    * 必须使用 Mock 框架屏蔽数据库、文件系统、外部网络调用。
    * 测试应具备**幂等性**，无论运行多少次结果都一致。
* **覆盖率平衡**：
    * **正常路径**：验证符合预期的输出。
    * **边界与异常路径**：验证错误输入时的系统鲁棒性。
* **自动化断言**：禁止使用 `print/console.log` 人肉观察，必须使用断言库（Assert）。

---

## 7. 增量开发原则 (Incremental Development)

1.  **纵向切片 (Vertical Slicing)**：
    
    优先完成一个完整功能点的全链路打通（从入口到数据库），而非横向地先写完所有 Controller。
2.  **契约优先**：当依赖的模块未就绪时，先定义接口协议并使用 Mock 实现占位，确保自身逻辑可以先行推进。
3.  **原子化提交**：每个 Commit 或 PR 只关注一个原子化的改动（如“添加登录逻辑”或“重构用户查询”）。
4.  **持续验证**：每一步改动都应保证代码可编译，且通过现有的核心单测路径。

---

## 8. Git Commit Message 规范 (Conventional Commits)

提交说明采用 **Conventional Commits** 风格，整体分为 **header**、**body**、**footer** 三部分。

### 8.1 完整格式

```text
<type>(<scope>): <subject>

<body>

<footer>
```

* **header**：独占一行，包含 `type`（必填）、`scope`（选填）、`subject`（必填）。`type` 后接英文冒号 **`:`，冒号后必须有一个空格**，再写 `subject`。
* **body**：对本次提交的详细说明，可多行；与 header、footer 之间各空一行。
* **footer**：重大变更、Breaking changes、关联 Issue 等；与 body 之间空一行。若改动显著影响其他模块，应写明。

### 8.2 Header 字段说明

**（1）type（必填）**

仅使用下列类型之一，**勿自创** `task`、`update`、`delete` 等未在规范中的类型。细则可与 [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) 对齐。

| type | 说明 |
|------|------|
| `feat` | 新增产品功能 |
| `fix` | 修复 bug |
| `docs` | 文档变更 |
| `style` | 不改变代码行为的格式调整（如空格、格式化、去掉末尾分号等） |
| `refactor` | 重构（非 bug 修复、非新功能） |
| `perf` | 性能优化 |
| `test` | 添加或修改测试 |
| `build` | 构建流程、外部依赖变更（如升级依赖、修改打包配置） |
| `ci` | CI 配置或脚本变更 |
| `chore` | 构建过程、辅助工具与杂项变更，且不改变业务源码与测试语义的其他操作 |
| `revert` | 回滚某次 commit |

**（2）scope（选填）**

说明本次提交影响的范围（如模块、目录、功能域），由项目约定，无则省略括号，写作 `type: subject`。

**（3）subject（必填）**

用一句话概括提交目的；建议 **不超过 50 个字符**（英文可按词计数习惯把握），避免冗长。

### 8.3 示例

仅 header、无 body/footer 的常见写法：

```text
docs(README): 完善 README 与协作说明
```

含 body 的示例：

```text
docs(README.md): 完善 README.md

添加了:
- 关于 git flow 工作流程
- git commit message 规范（持续补充）
- 参考资料
```

---

## 9. 点分式产品版本号命名 (Dotted Version Numbering)

对外发布的产品版本号采用**点分式**命名，格式为：

```text
M.S.F.B([SP][C])
```

方括号 `[]` 表示可选部分；`SP` 与 `C` 仅在发布补丁包或补丁时追加。

### 9.1 各段含义

| 段 | 名称 | 说明 |
|----|------|------|
| **M** | 主版本号 | 标识产品平台或整体架构的重大演进 |
| **S** | 次版本号 | 标识局部架构调整、重大特性，或**无法向前兼容**的接口变更 |
| **F** | 特性版本号 | 标识规划中的新特性版本 |
| **B** | 编译版本号 | 标识一次编译构建的版本号 |
| **SP** | 补丁包版本号（可选） | 标识累计一段时间的补丁打包版本 |
| **C** | 补丁版本号（可选） | 标识补丁包内的单次补丁 |

### 9.2 递增原则

* **M**：平台或整体架构重构、不兼容的重大方向调整时递增，低位段归零。
* **S**：局部架构或重大特性发布、对外接口发生不兼容变更时递增，**F**、**B** 及可选段归零。
* **F**：按产品规划交付新特性时递增，**B** 及可选段归零。
* **B**：每次正式编译构建递增；日常开发构建可与发布流程约定是否对外暴露。
* **SP**：将一段时间内累计的补丁合并为补丁包发布时递增，**C** 归零。
* **C**：在已有补丁包（或基线版本）上发布单个补丁时递增。

### 9.3 示例

```text
1.0.0.1          # 首个正式构建
1.1.0.12         # 次版本升级后的第 12 次构建
2.0.3.100        # 主版本 2，特性版本 3，构建号 100
1.2.1.5.SP1      # 在 1.2.1.5 基线上发布第 1 个补丁包
1.2.1.5.SP1.C2   # 上述补丁包内的第 2 个补丁
```

### 9.4 使用约定

* 版本号各段均为**非负整数**，不使用前导零（写作 `1.2.3.4`，而非 `01.02.03.04`）。
* 发布说明、变更日志、安装包文件名、API 文档与运行时对外暴露的版本标识应**保持一致**。
* 未发布补丁时省略 **SP**、**C**；仅发单补丁而无补丁包概念时，按团队约定决定是否使用 **C** 段，并在发布流程中统一。

---

## 本项目特有补充规范（AI Agent + uv）

ScholarGraph 是面向科研阅读的 **AI Agent** 项目：编排（如 LangGraph）、大模型 API 调用、结构化抽取（Pydantic）、图谱与 GraphRAG 等。**不包含深度学习训练、微调或 GPU 算力栈**（无 PyTorch / TensorFlow / CUDA 等依赖预期），因此以 **[uv](https://docs.astral.sh/uv/)** 管理 Python 与依赖即可，无需 conda 或多环境 CUDA 工具链。

仓库采用 **前后端分离** 布局：

* **后端**：根目录 `pyproject.toml` + **`backend/`**（**FastAPI**、LangGraph、Pydantic），由 **uv** 管理依赖。
* **前端**：**`frontend/`**（**Vue 3 + Vite + Pinia**），由 **npm** 管理，**不使用 uv**。图谱渲染首选 **AntV G6 v5**；UI 组件库 **Ant Design Vue** 或 **Element Plus**。

技术选型与 REST / SSE / 任务进度等协作约定见 [docs/v1/tech-stack.md](docs/v1/tech-stack.md)。

### Python 与 Agent 运行时（uv）

1. **安装 uv**：按官方文档安装后，确保终端中能执行 `uv --version`。
2. **同步依赖**：在**仓库根目录**执行 `uv sync`（或 CI / 严格复现：`uv sync --frozen`），会创建/更新 `.venv` 并安装 `pyproject.toml` 中的依赖（LangGraph、HTTP 客户端、FastAPI 等）。若使用 MySQL 驱动，可额外执行 `uv sync --extra mysql`；**短 PDF ingest path B（MinerU）** 需 `uv sync --extra mineru`（不进默认依赖，体积较大）。
3. **运行 Agent 与脚本**：优先使用 **`uv run`**，无需手动激活虚拟环境。示例：`uv run python -m backend.app` 或 `uv run uvicorn backend.main:app --reload`。**请在仓库根目录执行**，以便 `.env`、默认 SQLite 路径等与项目约定一致。
4. **环境变量**：将 `.env.example` 复制为 `.env` 后配置大模型 API Key、数据库等（`.env` 已 gitignore，勿提交）。密钥勿写入源码或明文文件。
5. **变更依赖后**：修改 `pyproject.toml` 后执行 `uv lock`（或 `uv lock --upgrade`），再 `uv sync`；提交时**同时**带上 `pyproject.toml` 与 `uv.lock`。
6. **自动化测试**：根目录 `tests/` 为正式 **pytest** 用例。开发依赖：`uv sync --group dev`，运行：`uv run pytest`。临时实验脚本可放在已 gitignore 的 `backend/test/` 等目录。

### 前端（Vue 3）

1. **安装依赖**：在 `frontend/` 下执行 `npm install`（勿在仓库根目录用 npm 管理后端）。
2. **本地开发**：`npm run dev`（默认 `http://localhost:5173`），后端 `uv run uvicorn backend.main:app --reload`（默认 `http://localhost:8000`）。
3. **环境变量**：复制 `frontend/.env.development.example` 为 `.env.development`。本地开发推荐 **留空** `VITE_API_BASE_URL`，由 Vite 将 `/api` 代理到 `http://127.0.0.1:8000`；直连后端时再设为 `http://localhost:8000`。可选 `VITE_USE_MOCK=false` 关闭前端 Mock。
4. **对接方式**：常规 CRUD 用 REST；**多尺度问答**用 **SSE** 流式输出；**PDF 解构建图**用 `POST /papers` + **长轮询** `GET /papers/{id}/status`（详见 tech-stack 文档）。
5. **契约**：后端图谱 JSON 字段与 `UnifiedPaperGraph` / OpenAPI 一致；前端先用 Mock，禁止在浏览器内持有 LLM API Key。

### 后端 HTTP 基座（负责人维护）

* 必须配置 **CORS**（允许 Vite 开发源）。
* 提供 **`/docs`** Swagger；对外 JSON 由 Pydantic 约束，与前端 G6 节点/边字段命名一致。

### 演示界面（备用）

仅当前端排期严重不足时，可用 Gradio / Streamlit（uv 安装）做答辩备份；**产品主路径仍为 Vue 3 工作台**。

在执行 **Python 脚本**、**安装或更新依赖**、**启动 Agent / API 服务** 前，请确认已在仓库根目录完成 `uv sync`（及按需 `--group dev` / `--extra mysql` / **`--extra mineru`**），避免误用全局 Python 或未安装依赖的环境。