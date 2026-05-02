# ATLAS Memory v9.5.0

> OpenClaw 语义记忆插件 — 自动捕获 · 语义检索 · 知识提炼 · 反馈进化

---

## 简介

ATLAS Memory 是为 [OpenClaw](https://openclaw.ai) 设计的商业级记忆插件。它让 AI Agent 具备持久化的语义记忆能力：自动捕获对话中的关键信息，在需要时语义检索注入上下文，并随时间自主进化、提炼知识、淘汰错误记忆。

**核心理念：** 降低重复沟通成本，AI 记住你说过的一切，并越用越准。

---

## 架构（四层）

```
INJECT  ──  每次提问前从 Qdrant 语义检索相关记忆注入上下文
            LRU 嵌入缓存(200条) + 时间衰减重排 + 2.5s 超时保护
            过滤负反馈记忆(feedback_score<0.5) + [通则]优先注入

CAPTURE ──  对话结束后自动提取事实存入 Qdrant
            omlx 质量评分(≥7才存) + 冲突检测 + 版本化(旧版标记superseded)
            每5轮对话触发一次中途捕获，distill写入内容自动去重

LEARN   ──  拦截搜索工具调用，自动学习网页内容
            分块处理(1500字/块, 300字重叠, 最多5块) + omlx提取

EVOLVE  ──  自动进化：每24h去重+过期清理+自动提炼通则
            每7天备份，每6h导出 Obsidian Bridge 镜像
            同标签 ≥5 条记忆自动触发 distill（每次最多3个标签）
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

## 模型依赖

### 本地模型（必须）

所有高频自动操作（INJECT / CAPTURE / LEARN / atlas_recall / atlas_feedback）均使用本地模型，**不产生任何云端费用**。

| 服务 | 模型 | 用途 | 推荐替代 |
|------|------|------|---------|
| **Qdrant** | — | 向量数据库，768-dim Cosine | 无替代，必须 |
| **Ollama** | `nomic-embed-text:latest` | 文本嵌入，768维，274MB | `mxbai-embed-large`（1024维，需重建 collection） |
| **omlx** | `Qwen3.5-9B-OptiQ-4bit` | 事实提取 / 冲突检测，4s/call | `Qwen2.5-7B-Instruct`（速度更快，精度稍低） |

### 云端模型（可选）

**仅 `atlas_distill` 工具和 EVOLVE 自动提炼时调用**，其余所有功能不触及云端。

| 服务 | 模型 | 用途 | 触发时机 |
|------|------|------|---------|
| **DeepSeek** | `deepseek-chat` | 知识提炼，从多条经验合成通则 | 手动调用 `atlas_distill` 或 EVOLVE 24h 扫描触发 |

> 若未配置 `DEEPSEEK_API_KEY`，distill 自动回退到本地 omlx，功能不受影响，仅质量稍低。

**云端模型选型参考：**

| 模型 | 输入/输出（per 1M tokens） | 适合场景 |
|------|--------------------------|---------|
| `deepseek-chat`（当前默认） | $0.28 / $0.42 | 知识提炼，性价比最优 |
| `deepseek-v4-flash` | $0.14 / $0.28 | 批量提炼场景，更快更便宜 |
| `deepseek-v4-pro` | $1.74 / $3.48 | 复杂推理，通常不必要 |

**典型月消耗：** 每次提炼约 $0.0003，正常使用场景下 **< $0.05/月**。

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

# 5. 配置 DeepSeek API Key（可选，用于知识提炼）
export DEEPSEEK_API_KEY=your_key_here

# 6. 启动
openclaw gateway start
```

完整安装指南见 [setup/SETUP.md](setup/SETUP.md)。

---

## Payload 字段（v9.5.0）

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 记忆内容 |
| `category` | string | personal / work / project / system / learning |
| `importance` | string | low / medium / high / critical（随访问自动升级） |
| `memory_type` | string | preference / fact / skill / project / constraint / event |
| `tags` | string[] | 标签列表，`[distilled]` 表示提炼通则 |
| `hit_count` | int | 被检索次数 |
| `feedback_score` | float | 反馈分 0–1.0，默认 1.0；低于 0.5 不注入，低于 0.2 删除 |
| `status` | string | active / superseded（版本链，旧版本保留不物理删除） |
| `superseded_by` | string | 指向替换该记忆的新版本 ID |
| `distill_basis` | int | 通则基于多少条原始记忆提炼 |

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| **v9.5.0** | 2026-05-03 | 反馈回路(atlas_feedback) + 知识提炼(atlas_distill/DeepSeek) + 版本化(superseded) + 主题时间线(atlas_timeline) + EVOLVE自动提炼 |
| v9.4.0 | 2026-05-01 | Obsidian Bridge + 主题聚类导出 + 每日进化日志 + Dataview仪表盘 |
| v9.3.0 | — | 冲突检测 + 质量评分(≥7) + memory_type分类 + omlx替代Ollama提取 |
