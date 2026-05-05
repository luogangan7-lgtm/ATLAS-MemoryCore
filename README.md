# ATLAS Memory v10.0

> OpenClaw 语义记忆插件 — 自动捕获 · 语义检索 · 知识提炼 · 反馈进化 · L1 课程知识库

---

## 简介

ATLAS Memory 是为 [OpenClaw](https://openclaw.ai) 设计的商业级记忆插件。它让 AI Agent 具备持久化的语义记忆能力：自动捕获对话中的关键信息，在需要时语义检索注入上下文，并随时间自主进化、提炼知识、淘汰错误记忆。

**v10 核心升级：** 在原有对话记忆基础上，新增四层知识成熟度体系（L0 原料 → L1 知识 → L2 洞见 → L3 框架），支持从课程转录稿批量提炼 L1 结构化知识节点。

---

## 架构（四层记忆 + 四层知识成熟度）

```
INJECT  ──  每次提问前从 Qdrant 语义检索相关记忆注入上下文
            层级优先搜索（L3→L2→L1→L0）+ LRU 嵌入缓存(200条)
            时间衰减重排 + 2.5s 超时保护 + 过滤负反馈记忆

CAPTURE ──  对话结束后自动提取事实存入 Qdrant
            omlx 质量评分(≥7才存) + 冲突检测 + 版本化(旧版标记superseded)
            每5轮对话触发一次中途捕获，distill写入内容自动去重

LEARN   ──  拦截搜索工具调用，自动学习网页内容
            分块处理(1500字/块, 300字重叠, 最多5块) + omlx提取

EVOLVE  ──  自动进化：每24h去重+过期清理+自动提炼通则
            L1CompletionAgent 自动监控并补全缺失知识节点
            每7天备份，每6h导出 Obsidian Bridge 镜像
            同标签 ≥5 条记忆自动触发 distill（每次最多3个标签）

知识层级：L0 原料（原始信息）→ L1 知识（结构化笔记）
         → L2 跨域洞见 → L3 智识框架
```

---

## 工具列表（13个）

| 工具 | 用途 |
|------|------|
| `atlas_store` | 手动存入记忆（含冲突检测） |
| `atlas_recall` | 语义检索记忆（向量搜索 + 时间衰减） |
| `atlas_feedback` | 反馈评价：correct/wrong/outdated（负评累积自动删除） |
| `atlas_distill` | 知识提炼：对某标签下的多条经验合成"通则" |
| `atlas_timeline` | 主题时间线：某标签下所有记忆按时间排序 |
| `atlas_evolve` | 手动触发进化（去重 + 过期清理 + 自动提炼） |
| `atlas_merge` | 智能合并近重复记忆 |
| `atlas_delete` | 按语义相似度删除记忆 |
| `atlas_stats` | 查看记忆库完整状态 |
| `atlas_web_learn` | 从 URL 或文本中学习知识 |
| `atlas_export` | 导出记忆库为 JSON 备份 |
| `atlas_import` | 从 JSON 备份恢复记忆库 |
| `atlas_obsidian_sync` | 手动触发 Obsidian Bridge 同步 |

---

## L1 课程知识提炼 Pipeline

v10 新增批量课程处理脚本，可将课程转录稿（.txt）提炼为结构化 L1 知识节点并自动写入 Qdrant + Obsidian Vault。

### 格式标准

每个知识节点使用以下结构：

```markdown
#### X.X [知识点标题]

**核心内容**
[书面语段落：是什么 + 为什么 + 深层逻辑]

**如何运用**
[实际场景 + 操作方法]

**关联知识**
[课程内部关联 + 通用知识体系]

> [完整原文，严禁摘要缩短]
```

### 使用方法

```bash
# 安装依赖（仅需 Ollama bge-m3 + Qdrant + DeepSeek API Key）
export DEEPSEEK_API_KEY=your_key_here

# 跑全部课程
python3 scripts/course_to_l1_pipeline.py

# 并行跑两组（避免内存压力）
python3 scripts/course_to_l1_pipeline.py --group 1 > logs/group1.log 2>&1 &
python3 scripts/course_to_l1_pipeline.py --group 2 > logs/group2.log 2>&1 &
```

### 配置

编辑 `scripts/course_to_l1_pipeline.py` 中的 `COURSES` 列表，每条格式为：
```python
("课程目录名", "课程名", "域", "xmind文件名或None")
```

脚本自动：
- 解析 .xmind 思维导图为骨架
- 按转录稿长度动态计算 token 预算
- 提炼后写入本地 `核心知识整理/` 目录
- 同步到 Obsidian Vault `L1/<域>/` 目录
- 向量化后 upsert 到 Qdrant `atlas_memories` 集合

---

## 模型依赖

### 本地模型（必须）

| 服务 | 模型 | 用途 |
|------|------|------|
| **Qdrant** | — | 向量数据库，1024-dim Cosine |
| **Ollama** | `bge-m3` | 文本嵌入，1024维 |
| **omlx** | `Qwen3.5-9B-OptiQ-4bit` | 事实提取 / 冲突检测 |

### 云端模型（可选）

| 服务 | 模型 | 用途 | 触发时机 |
|------|------|------|---------|
| **DeepSeek** | `deepseek-v4-flash` | L1 知识提炼（课程转录稿） | pipeline 脚本 / L1CompletionAgent |
| **DeepSeek** | `deepseek-chat` | 通则提炼 | `atlas_distill` / EVOLVE 24h 扫描 |

**云端模型选型参考：**

| 模型 | 输入/输出（per 1M tokens） | 适合场景 |
|------|--------------------------|---------|
| `deepseek-v4-flash` | $0.14 / $0.28 | L1 批量提炼，1M 上下文，384K 输出 |
| `deepseek-v4-pro` | $1.74 / $3.48 | 高质量提炼，复杂推理 |
| `deepseek-chat` | $0.28 / $0.42 | 通则蒸馏，性价比最优 |

---

## 快速安装

前置要求：OpenClaw 已安装，Qdrant / Ollama / omlx 已启动。

```bash
# 1. 创建插件目录
mkdir -p ~/.openclaw/hooks/atlas-memory

# 2. 克隆本仓库
git clone https://github.com/luogangan7-lgtm/ATLAS-MemoryCore /tmp/ATLAS-MemoryCore

# 3. 复制插件文件
cp /tmp/ATLAS-MemoryCore/openclaw-plugin/index.js ~/.openclaw/hooks/atlas-memory/
cp /tmp/ATLAS-MemoryCore/openclaw-plugin/openclaw.plugin.json ~/.openclaw/hooks/atlas-memory/

# 4. 复制配置模板并填入 API Key
cp /tmp/ATLAS-MemoryCore/setup/openclaw.template.json ~/.openclaw/openclaw.json

# 5. 配置 DeepSeek API Key
export DEEPSEEK_API_KEY=your_key_here

# 6. 启动
openclaw gateway start
```

完整安装指南见 [setup/SETUP.md](setup/SETUP.md)。

---

## Payload 字段（v10.0）

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 记忆/知识内容 |
| `level` | int | 知识层级：0=原料, 1=知识, 2=洞见, 3=框架 |
| `status` | string | active / superseded（版本链） |
| `domain` | string | 知识域（如"情感学"） |
| `topic` | string | 主题（课程名·讲次） |
| `completeness_score` | float | 完整度 0–1.0 |
| `faithfulness_score` | float | 忠实度 0–1.0 |
| `tags` | string[] | 标签列表 |
| `hit_count` | int | 被检索次数 |
| `feedback_score` | float | 反馈分 0–1.0；低于 0.5 不注入 |
| `superseded_by` | string | 指向替换该记忆的新版本 ID |
| `obsidian_path` | string | Obsidian Vault 相对路径 |
| `source` | string | 来源标识（如"course-transcript-v3"） |

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| **v10.0** | 2026-05-05 | 四层知识成熟度(L0-L3) + L1CompletionAgent + 课程转录稿 pipeline(course_to_l1_pipeline.py) + bge-m3(1024dim) + 层级优先注入 |
| v9.5.0 | 2026-05-03 | 反馈回路(atlas_feedback) + 知识提炼(atlas_distill/DeepSeek) + 版本化(superseded) + 主题时间线 + EVOLVE自动提炼 |
| v9.4.0 | 2026-05-01 | Obsidian Bridge + 主题聚类导出 + 每日进化日志 + Dataview仪表盘 |
| v9.3.0 | — | 冲突检测 + 质量评分(≥7) + memory_type分类 + omlx替代Ollama提取 |
