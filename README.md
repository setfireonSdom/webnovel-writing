# NovelWriter - AI 驱动的网文写作系统

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-39%20passing-green.svg)](tests/)

一个基于大语言模型的中文网文写作系统。通过多层审查机制和状态追踪，**尽量**让长篇小说写作保持一致性。

> ⚠️ **说在前面**：这不是一个"一键生成百万字小说"的魔法工具。它辅助你写作，不替代你写作。AI 会犯错，所有检查机制都是概率性的，不是确定性的。你需要审查输出。

---

## 📋 目录

- [🤔 这到底是个什么](#这到底是个什么)
- [✅ 它能做什么](#它能做什么)
- [❌ 它不能做什么](#它不能做什么)
- [🚀 快速开始](#快速开始)
- [📖 使用方法](#使用方法)
- [⚙️ 配置](#配置)
- [🔧 命令参考](#命令参考)
- [📁 文件结构](#文件结构)
- [⚠️ 已知问题与限制](#已知问题与限制)
- [📈 性能数据](#性能数据)

---

## 这到底是个什么

这是一个 **LLM 包装器**。核心工作流是：

```
读取章节细纲 → 加载角色状态/前情摘要 → 调用 LLM 写初稿 → 风格优化 → 逻辑检查 → 多审查器并行评审 → 智能润色 → 保存 → 更新状态 → Git备份
```

它在 LLM 前后加了一堆"护栏"——角色状态面板、一致性检查器、逻辑审查、世界观规则库——目的是减少 LLM 胡编乱造的概率。

**但它不是完美的。** 所有检查器本身也依赖 LLM 调用，所以本质上是"用一个 AI 检查另一个 AI"。这比裸用 LLM 好，但不能保证 100% 不出错。

---

## 它能做什么

### 长篇写作辅助
- **角色状态追踪**：维护每个角色的性别、境界、状态、关系、持有物品。写作时注入 prompt，检查器会核对
- **性别代词硬性检查**：纯正则扫描器检测"他/她"是否与角色设定性别一致（不依赖 LLM，这是系统里少数确定性检查）
- **境界/状态一致性**：LogicChecker 检查境界倒退、伤势未愈就生龙活虎等问题
- **因果债/伏笔追踪**：记录"A 救了 B → B 欠 A 一条命"和伏笔状态，超期未回收会警告
- **世界观规则库**：从设定文件提取规则，写作时约束 LLM，审查时专项检查
- **BM25 检索**：从已写章节中检索与当前章相关的片段，帮助保持上下文连贯
- **记忆衰减**：按重要性权重压缩上下文，防止写到 100 章时 prompt 爆炸

### 质量控制
- **7 维审查**：一致性、连贯性、OOC、爽点、节奏、追读力、世界观规则（全部 LLM 驱动）
- **反 AI 腔扫描**：检测 200+ 高危 AI 词汇（总结词、枚举模板、学术腔等）
- **逻辑审查重试**：LogicChecker 失败后注入明确错误信息并重写（最多 2 次）
- **自动审计**：每 50 章生成健康报告，追踪质量趋势、伏笔回收率、角色弧光

### 工程管理
- **自动细纲生成**：按批次生成章节细纲（每批 5 章，带前文上下文）
- **Git 备份**：每章一个提交 + tag，方便回退
- **3 种写作模式**：standard（完整流程）、fast（跳过审查）、minimal（只生成初稿）
- **Dashboard**：FastAPI + 前端，查看章节、角色状态、统计数据

---

## 它不能做什么

**实话实说，这些很重要，买前须知：**

1. **不保证逻辑绝对一致**——所有检查器都是 LLM 驱动的概率判断，不是形式化验证。LLM 可能漏检
2. **不会"自动写小说"**——你需要提供细纲、设定、角色信息。没有这些输入，输出质量很差
3. **State Machine 的 AI 提取是空的**——`_extract_state_changes_with_ai()` 方法是 `pass`，状态更新不完整
4. **向量检索未完全集成**——代码有 `hybrid_rag.py` 但默认只用 BM25，embedding/rerank 需要额外配置
5. **没有端到端测试**——39 个测试都是单元测试，`write_chapter()` 整个流程没测过
6. **不知道角色知道什么**——`knowledge` 字段存在但提取 prompt 刚加上，实际效果未经检验
7. **LLM 调用量大**——standard 模式写一章约 12-15 次 LLM 调用（Context Agent + Draft + Style + Logic + 7 个审查器 + Polish + DataAgent），成本高
8. **不处理图片/音频/任何非文本输入**
9. **中文优化但非中文独占**——用英文 LLM 也行，但 prompt 全是中文，效果存疑
10. **不会自动修正所有问题**——"智能润色"只修 critical + high 问题（最多 5 个），小问题不管

---

## 快速开始

### Clone 下来之后（新用户必看）

两条路，选一条走：

**路径 A：用 uv（推荐，更快）**

```bash
git clone <你的仓库地址>
cd novel-writer

# 安装 uv（如果还没装）：curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
uv pip install -r requirements.txt
uv pip install -e .

cp .env.example .env
# 编辑 .env，把 QWEN_API_KEY 改成你自己的 Key

# 直接用 uv run 跑命令，不需要 source activate
uv run novel-writer preflight
uv run novel-writer init --title "我的小说" --genre "仙侠"
cd "我的小说"
uv run novel-writer plan --volume 1 --chapters 10 --auto --batch-size 5
uv run novel-writer write --chapter 1 --mode standard
```

**路径 B：用 venv + pip（标准库，不需要额外安装）**

```bash
git clone <你的仓库地址>
cd novel-writer

python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
pip install -e .

cp .env.example .env
# 编辑 .env，把 QWEN_API_KEY 改成你自己的 Key

novel-writer preflight
novel-writer init --title "我的小说" --genre "仙侠"
cd "我的小说"
novel-writer plan --volume 1 --chapters 10 --auto --batch-size 5
novel-writer write --chapter 1 --mode standard
```

> **最低要求**：Python 3.10+、一个能用的 LLM API Key。其他都是可选的。

---

## 使用方法

### 从零开始写一本小说

```bash
# 1. 创建项目
novel-writer init --title "我的小说" --genre "玄幻"
cd "我的小说"

# 2. 生成第1卷100章细纲（AI辅助）
novel-writer plan --volume 1 --chapters 100 --auto --batch-size 5

# 3. 开始写作
novel-writer write --start 1 --end 100 --mode standard

# 4. 每50章查看审计报告
cat .webnovel/audits/audit_chapter_0050_*.md
```

**你需要做的**：确认细纲质量、抽查输出章节、修正明显错误。系统不是全自动的。

### 中断后恢复

```bash
novel-writer resume
# 显示中断的任务，选择 continue / restart / cancel
```

### 审查已有章节

```bash
novel-writer review --chapter 3 --depth full
novel-writer query --type review  # 查看审查结果
```

### 旧项目迁移

如果你之前用过这个系统，state.json 可能缺少 gender 等新字段：

```bash
python scripts/migrate_state.py --project /path/to/your/novel --auto-gender
```

会自动补充 gender、personality、traits 等字段，并从章节内容推断性别。

---

## 配置

### .env（必须）

```bash
NOVEL_LLM_PROVIDER=openai
QWEN_MODEL=qwen3-max-2026-01-23
QWEN_API_KEY=sk-your_key

# 可选：写作模式
NOVEL_WORKFLOW_MODE=standard  # standard | fast | minimal
```

### config.yaml（可选）

```yaml
workflow:
  default_mode: standard
  chapter_min_words: 2000
  chapter_max_words: 2500
  git_backup: true
```

不创建 config.yaml 也能跑，用内置默认值。

---

## 命令参考

| 命令 | 说明 | 示例 |
|------|------|------|
| `preflight` | 检查环境是否就绪 | `novel-writer preflight` |
| `init` | 创建新项目 | `novel-writer init --title "书名" --genre "仙侠"` |
| `plan` | 生成章节细纲 | `novel-writer plan --volume 1 --chapters 20 --auto` |
| `write` | 写作章节 | `novel-writer write --chapter 1 --mode standard` |
| `write` (批量) | 批量写作 | `novel-writer write --start 1 --end 10 --mode fast` |
| `review` | 审查章节 | `novel-writer review --chapter 5 --depth full` |
| `query` | 查询信息 | `novel-writer query --type character` |
| `resume` | 恢复中断任务 | `novel-writer resume` |
| `dashboard` | 启动 Web 面板 | `novel-writer dashboard --port 8765` |

如果 `novel-writer` 命令不可用，用 `python -m src.main` 替代。

---

## 文件结构

### 运行后你的项目

```
你的书名/
├── .webnovel/
│   ├── state.json                # 核心：全局状态 + 角色面板
│   ├── workflow_state.json       # 工作流进度
│   ├── world_rules.json          # 世界观规则
│   ├── character_arcs.json       # 角色弧光
│   ├── causal_chain.json         # 因果债 + 伏笔
│   ├── state_machine.json        # 显式状态机
│   ├── state_archive.json        # 归档实体
│   ├── volume_summaries.json     # 卷摘要
│   ├── summaries/                # 每章摘要 ch0001.md ...
│   ├── audits/                   # 审计报告（每50章）
│   ├── rag_index/                # BM25 索引
│   └── observability/            # 性能日志
├── 设定集/
│   ├── 角色设定.md               # 含性别、性格、背景
│   ├── 力量体系.md
│   └── 世界观.md
├── 大纲/
│   ├── 总纲.md
│   └── 细纲/
│       └── 卷1_细纲.json
└── 正文/
    ├── ch0001.md
    └── ch0002.md
```

---

## 已知问题与限制

### 严重的
- **State Machine AI 提取未实现**：`_extract_state_changes_with_ai()` 是空方法，状态机只能手动初始化，不会从章节自动更新
- **测试覆盖不足**：39 个测试全是单元测试，没有端到端测试。`write_chapter()` 整个 pipeline 从未被自动化测试覆盖
- **LLM 依赖**：写一章 12-15 次 API 调用，用 commercial API 的话成本不低

### 中等的
- **向量检索未完全接入**：`hybrid_rag.py` 存在但默认不用。需要手动配置 embedding/rerank API
- **知识状态追踪刚加上**：`knowledge` 字段和提取 prompt 刚更新，实际效果未知
- **检查器都是 LLM 驱动**：唯一的确定性检查是性别代词扫描器（正则），其他全部依赖 LLM 判断

### 轻微的
- **旧项目需要迁移**：运行 `scripts/migrate_state.py` 补充缺失字段
- **Dashboard 功能有限**：只能查看数据，不能编辑
- **中文 prompt 为主**：用非中文 LLM 可能效果差

---

## 性能数据

**实测数据（qwen3-max，2000-2500 字/章）：**

| 模式 | 耗时/章 | LLM 调用次数 | 说明 |
|------|---------|-------------|------|
| standard | ~45-60s | 12-15 次 | 完整流程 |
| fast | ~25-35s | 3-4 次 | 跳过审查和润色 |
| minimal | ~15-20s | 1-2 次 | 只生成初稿 |

**成本估算**：按 qwen3-max 的价格，standard 模式写一章约 0.1-0.3 元。写 100 章约 10-30 元。

---

## 技术栈

- Python 3.10+
- Pydantic 2（数据模型）
- httpx（异步 HTTP）
- OpenAI SDK（API 调用，兼容模式支持任意后端）
- rank-bm25（RAG 检索）
- Rich（终端输出）
- FastAPI + Uvicorn（Dashboard）
- pytest（测试）

---

## 许可证

GPL v3

---

**总结**：这是一个**有护栏的 LLM 写作辅助工具**。护栏比裸用好很多，但护栏本身也不完美。用它辅助你写，别指望它替你写。
