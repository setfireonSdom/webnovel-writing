# NovelWriter - AI 驱动的网文写作系统

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-39%20passing-green.svg)](tests/)

一个基于大语言模型的中文网文写作系统。通过多层审查机制和状态追踪，尽量让长篇小说写作保持一致性。

> ⚠️ 这不是"一键生成百万字小说"的魔法工具。它辅助你写作，不替代你写作。AI 会犯错，所有检查机制都是概率性的。你需要审查输出。

---

## 📋 目录

- [🚀 快速开始](#快速开始)
- [📖 完整使用流程](#完整使用流程)
- [🔧 命令参考](#命令参考)
- [⚙️ 配置](#配置)
- [📁 文件结构](#文件结构)
- [⚠️ 已知问题与限制](#已知问题与限制)
- [📈 性能数据](#性能数据)

---

## 快速开始

### 两条路，选一条

**路径 A：用 uv（推荐，更快）**

```bash
git clone <你的仓库地址>
cd novel-writer

# 安装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
uv pip install -r requirements.txt
uv pip install -e .

cp .env.example .env
# 编辑 .env，把 QWEN_API_KEY 改成你自己的 Key

uv run novel-writer preflight
uv run novel-writer init --title "我的小说" --genre "都市"
```

**路径 B：用 venv + pip（标准库，不需要额外安装）**

```bash
git clone <你的仓库地址>
cd novel-writer

python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux

pip install -r requirements.txt
pip install -e .

cp .env.example .env
# 编辑 .env，把 QWEN_API_KEY 改成你自己的 Key

novel-writer preflight
novel-writer init --title "我的小说" --genre "都市"
```

> **最低要求**：Python 3.10+、一个能用的 LLM API Key。其他都是可选的。

---

## 完整使用流程

下面是从零到写完一本小说的**每一步操作**，按顺序走就行。

### 第 1 步：初始化项目

**目的**：创建项目目录结构、生成 `state.json`（核心状态文件）、写入设定集。

两种方式，选一种：

```bash
# 方式一：AI 全自动（推荐，30 秒搞定）
novel-writer init --title "我的小说" --genre "都市" --auto
# AI 会自动生成主角设定、金手指、世界观、力量体系等全部设定

# 方式二：手动填写（交互式引导，适合有明确想法的用户）
novel-writer init --title "我的小说" --genre "都市"
# 系统会一步步问你：主角姓名、性别、欲望、缺陷、性格、金手指、世界观、力量体系...
```

执行成功后会创建以下目录：
```
我的小说/
├── .webnovel/
│   └── state.json              # 核心状态文件（角色、进度、世界观）
├── 设定集/
│   ├── 角色设定.md
│   ├── 力量体系.md
│   └── 世界观.md
├── 大纲/
│   └── 总纲.md
└── 正文/                        # 空目录，等写作后生成
```

**接下来要做的**：进入项目目录，编辑设定文件确认内容符合预期。

```bash
cd "我的小说"
cat 设定集/角色设定.md    # 查看主角设定
cat 设定集/世界观.md      # 查看世界观设定
```

---

### 第 2 步：生成细纲

**目的**：为每一章写详细的章节大纲（细纲），写作时 AI 严格按细纲执行。

```bash
# 方式一：AI 自动生成（推荐）
novel-writer plan --volume 1 --chapters 50 --auto --batch-size 5

# 方式二：人工辅助（AI 辅助但你可以逐章审核）
novel-writer plan --volume 1 --chapters 20
```

**参数说明**：
- `--volume`：卷号，第几卷
- `--chapters`：要生成多少章的细纲
- `--auto`：自动生成模式
- `--batch-size`：自动生成时每批生成几章（默认 5，带前文上下文）

**如果提示"未找到总纲"**：系统会引导你填写总纲（一句话简介、核心冲突、主要卖点、故事主线），填完重新运行 `plan` 命令即可。

生成完成后查看细纲：
```bash
cat 大纲/细纲/卷1_细纲.json    # 查看第1卷细纲
```

---

### 第 3 步：检查和优化细纲

**目的**：AI 检查细纲的逻辑问题（节奏、冲突、伏笔等）并自动优化。

```bash
novel-writer check-outline --volume 1
# AI 会检查第1卷细纲的逻辑漏洞、节奏问题，并自动修复
```

这一步不是必须的，但建议跑一下，能提前发现大纲层面的问题。

---

### 第 4 步：开始写作

有 **三种模式** 和 **两种方式**：

#### 写作模式

| 模式 | 做了什么 | 耗时 | 适用场景 |
|------|---------|------|---------|
| **standard** | 初稿 → 风格优化 → 逻辑审查 → 7维审查 → 智能润色 → 保存 → 状态更新 → Git备份 | ~45-60s/章 | 正式写作，质量优先 |
| **fast** | 初稿 → 风格优化 → 保存 → 状态更新 | ~25-35s/章 | 快速生成，跳过审查 |
| **minimal** | 只生成初稿 | ~15-20s/章 | 原型测试，最快 |

#### 写作方式

**单章模式**：写某一章，适合精修

```bash
novel-writer write --chapter 1 --mode standard
novel-writer write --chapter 2 --mode standard
novel-writer write --chapter 3 --mode standard
```

**批量模式**：一口气写多章，适合快速推进

```bash
novel-writer write --start 1 --end 10 --mode standard
novel-writer write --start 11 --end 20 --mode fast
```

**推荐工作流**：先用 fast 模式快速写完 10 章，再用 standard 模式逐章精修。

#### 写作过程

每一步 AI 会自动执行：
1. 读取该章细纲
2. 加载角色状态面板（性别、境界、关系、物品）
3. 加载前情摘要和 BM25 检索相关历史章节
4. 加载世界观规则约束
5. 生成创作执行包
6. 撰写初稿
7. 风格优化（消除 AI 腔）
8. 逻辑审查（检查性别、境界、状态一致性）
9. 性别代词扫描（纯正则检查"他/她"是否正确）
10. 7 维并行审查（standard 模式）
11. 智能润色（修复 critical/high 问题）
12. 保存文件到 `正文/chXXXX.md`
13. 更新角色状态、因果债、伏笔追踪
14. Git 备份

如果逻辑审查失败（如性别写错），AI 会自动注入正确信息并重写（最多重试 2 次）。

#### 查看输出

```bash
cat 正文/ch0001.md    # 查看第1章
cat 正文/ch0002.md    # 查看第2章
```

---

### 第 5 步：审查和修改

**审查已有章节**：

```bash
# 审查第3章
novel-writer review --chapter 3 --depth core    # 快速审查
novel-writer review --chapter 3 --depth full    # 深度审查

# 查看审查结果
novel-writer query --type review
```

**重写某一章**：

```bash
novel-writer write --chapter 3 --mode standard
# 会重新生成第3章，覆盖原文件
```

---

### 第 6 步：查看项目状态

```bash
# 查看所有角色状态
novel-writer query --type character

# 查看某个角色
novel-writer query --type character --name "主角名"

# 查看写作进度
novel-writer query --type progress

# 查看所有实体（角色、地点、势力）
novel-writer query --type entities

# 查看审查记录
novel-writer query --type review
```

---

### 第 7 步：自动审计（每 50 章自动触发）

写到第 50、100、150... 章时，系统会自动生成健康报告：

```bash
cat .webnovel/audits/audit_chapter_0050_*.md
```

报告包含：
- 整体健康度评分（0-100）
- 伏笔回收率
- 角色弧光一致性
- 质量趋势（上升/下降/稳定）
- 可操作建议

---

### 第 8 步：继续写下一卷

```bash
# 生成第2卷细纲
novel-writer plan --volume 2 --chapters 50 --auto --batch-size 5

# 检查细纲
novel-writer check-outline --volume 2

# 开始写作（接着第1卷的最后章节号）
novel-writer write --start 51 --end 100 --mode standard
```

---

### 中断后恢复

如果写作过程中被打断（网络断了、API 报错等）：

```bash
novel-writer resume
# 系统会显示中断的任务，选择 continue（继续）/ restart（重头来）/ cancel（取消）
```

---

## 命令参考

| 命令 | 说明 | 必需参数 | 可选参数 | 示例 |
|------|------|---------|---------|------|
| `preflight` | 检查环境是否就绪 | 无 | 无 | `novel-writer preflight` |
| `init` | 创建新项目 | `--title`, `--genre` | `--auto` | `novel-writer init --title "书名" --genre "都市" --auto` |
| `plan` | 生成章节细纲 | `--volume`, `--chapters` | `--auto`, `--batch-size` | `novel-writer plan --volume 1 --chapters 50 --auto --batch-size 5` |
| `check-outline` | 检查并优化细纲 | `--volume` | 无 | `novel-writer check-outline --volume 1` |
| `write` | 写作章节 | `--chapter` 或 `--start`+`--end` | `--mode` | `novel-writer write --chapter 1 --mode standard` |
| `write` (批量) | 批量写作 | `--start`, `--end` | `--mode` | `novel-writer write --start 1 --end 10 --mode fast` |
| `review` | 审查章节 | `--chapter` | `--depth` | `novel-writer review --chapter 5 --depth full` |
| `query` | 查询信息 | `--type` | `--name` | `novel-writer query --type character --name "张三"` |
| `resume` | 恢复中断任务 | 无 | 无 | `novel-writer resume` |
| `dashboard` | 启动 Web 面板 | 无 | `--host`, `--port`, `--reload` | `novel-writer dashboard --port 8765` |

### query 支持的类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `character` | 角色状态 | `novel-writer query --type character` |
| `character --name` | 指定角色 | `novel-writer query --type character --name "张三"` |
| `progress` | 项目进度 | `novel-writer query --type progress` |
| `entities` | 所有实体 | `novel-writer query --type entities` |
| `review` | 审查记录 | `novel-writer query --type review` |

如果 `novel-writer` 命令不可用，用 `uv run novel-writer` 或 `python -m src.main` 替代。

---

## 配置

### .env（必须）

```bash
# 最少只需要改这三行
NOVEL_LLM_PROVIDER=openai
QWEN_API_KEY=替换成你的key
QWEN_MODEL=qwen3-max-2026-01-23

# 可选参数（不写有默认值）
NOVEL_LLM_TEMPERATURE=0.7
NOVEL_LLM_MAX_TOKENS=4096
NOVEL_WORKFLOW_MODE=standard       # standard | fast | minimal
NOVEL_REVIEW_DEPTH=core            # core | full
```

### config.yaml（可选）

不创建也能跑，用内置默认值。想自定义就创建：

```yaml
workflow:
  default_mode: standard
  chapter_min_words: 2000
  chapter_max_words: 2500
  git_backup: true
```

---

## 文件结构

### 运行后你的项目

```
你的书名/
├── .webnovel/
│   ├── state.json                # 核心：全局状态 + 角色面板
│   ├── workflow_state.json       # 工作流进度（中断恢复用）
│   ├── world_rules.json          # 世界观规则库
│   ├── character_arcs.json       # 角色弧光追踪
│   ├── causal_chain.json         # 因果债 + 伏笔
│   ├── state_machine.json        # 显式状态机
│   ├── summaries/                # 每章摘要
│   ├── audits/                   # 审计报告（每50章自动生成）
│   └── rag_index/                # BM25 检索索引
├── 设定集/
│   ├── 角色设定.md               # 主角、配角、反派设定
│   ├── 力量体系.md               # 境界等级、能力规则
│   └── 世界观.md                 # 世界概述、社会结构
├── 大纲/
│   ├── 总纲.md                   # 一句话简介、核心冲突、故事主线
│   └── 细纲/
│       └── 卷1_细纲.json         # 每章的详细大纲
└── 正文/
    ├── ch0001.md                 # 第1章正文
    ├── ch0002.md                 # 第2章正文
    └── ...
```

---

## 已知问题与限制

### 严重的
- **State Machine AI 提取未实现**：状态机只能手动初始化，不会从章节自动更新
- **测试覆盖不足**：39 个测试全是单元测试，没有端到端测试。`write_chapter()` 整个流程没被自动化测试覆盖
- **LLM 调用量大**：standard 模式写一章约 12-15 次 API 调用，成本不低

### 中等的
- **向量检索未完全接入**：默认只用 BM25，embedding/rerank 需要额外配置
- **知识状态追踪刚加上**：`knowledge` 字段和提取 prompt 刚更新，实际效果未知
- **检查器都是 LLM 驱动**：唯一的确定性检查是性别代词扫描器（正则），其他依赖 LLM 判断

### 轻微的
- **旧项目需要迁移**：运行 `python scripts/migrate_state.py --project /path/to/novel --auto-gender` 补充缺失字段
- **Dashboard 功能有限**：只能查看数据，不能编辑
- **中文 prompt 为主**：用非中文 LLM 可能效果差

---

## 性能数据

实测数据（qwen3-max，2000-2500 字/章）：

| 模式 | 耗时/章 | LLM 调用次数 | 说明 |
|------|---------|-------------|------|
| standard | ~45-60s | 12-15 次 | 完整流程 |
| fast | ~25-35s | 3-4 次 | 跳过审查和润色 |
| minimal | ~15-20s | 1-2 次 | 只生成初稿 |

成本估算：按 qwen3-max 价格，standard 模式一章约 0.1-0.3 元，100 章约 10-30 元。

---

## 技术栈

Python 3.10+, Pydantic 2, httpx, OpenAI SDK, rank-bm25, jieba, Rich, FastAPI, pytest

---

GPL v3
