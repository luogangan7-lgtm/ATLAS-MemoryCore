# ATLAS Memory v9.4.0

> OpenClaw 语义记忆插件 — Qdrant 向量存储 + omlx Qwen3.5 智能提取 + Obsidian Bridge

---

## 简介

ATLAS Memory 是为 [OpenClaw](https://openclaw.ai) 设计的商业级记忆插件。它让 AI Agent 具备持久化的语义记忆能力：自动捕获对话中的关键信息，在需要时检索注入上下文，并随时间自主进化和去重。

**核心理念：** 降低重复沟通成本，AI 记住你说过的一切。

---

## 架构（四层）

```
INJECT  ──  每次提问前从 Qdrant 检索相关记忆注入上下文
            LRU 缓存(200条) + 时间衰减重排 + 2.5s 超时保护

CAPTURE ──  对话结束后自动提取事实存入 Qdrant
            Qwen3.5 质量评分(≥7才存) + 冲突检测 + 批量 upsert
            每5轮对话触发一次中途捕获

LEARN   ──  拦截搜索工具调用，自动学习网页内容
            分块处理(1500字/块, 300字重叠, 最多5块)

EVOLVE  ──  自动进化：每24h去重，每7天备份，每6h导出Obsidian镜像
            清理过期记忆(hit_count=0 + 90天以上 + low importance)
```

---

## 依赖服务

| 服务 | 地址 | 用途 |
|------|------|------|
| Qdrant | `http://127.0.0.1:6333` | 向量数据库（768-dim Cosine） |
| Ollama `nomic-embed-text` | `http://127.0.0.1:11434` | 文本嵌入 |
| omlx `Qwen3.5-9B-OptiQ-4bit` | `http://127.0.0.1:7749/v1` | 提取 / 冲突检测（4s/call） |

---

## 快速安装

**前置：** 安装 OpenClaw、启动 Qdrant、Ollama（含 nomic-embed-text）、omlx（含 Qwen3.5-9B）

```bash
# 1. 创建插件目录
mkdir -p ~/.openclaw/hooks/atlas-memory

# 2. 克隆本仓库
git clone https://github.com/luogangan7-lgtm/ATLAS-MemoryCore /tmp/ATLAS-MemoryCore

# 3. 复制插件文件
cp /tmp/ATLAS-MemoryCore/openclaw-plugin/* ~/.openclaw/hooks/atlas-memory/

# 4. 复制配置模板并填入 API Key
cp /tmp/ATLAS-MemoryCore/setup/openclaw.template.json ~/.openclaw/openclaw.json

# 5. 创建 Qdrant collection
curl -X PUT http://127.0.0.1:6333/collections/atlas_memories \
  -H 'Content-Type: application/json' \
  -d '{"vectors": {"size": 768, "distance": "Cosine"}}'

# 6. 启动
openclaw gateway start
```

完整安装文档（含已知陷阱）→ [setup/SETUP.md](setup/SETUP.md)

---

## 工具列表（10个）

| 工具 | 功能 |
|------|------|
| `atlas_store` | 手动存储记忆（冲突检测 + 去重） |
| `atlas_recall` | 语义搜索（时间衰减 + 访问计数） |
| `atlas_delete` | 按语义相似性删除 |
| `atlas_stats` | 系统健康状态（Qdrant / Ollama / omlx / 缓存命中率） |
| `atlas_evolve` | 手动触发去重 + 过期清理 |
| `atlas_web_learn` | URL/文本分块学习，质量过滤 |
| `atlas_merge` | 扫描近重复记忆，Qwen3.5 智能合并 |
| `atlas_export` | 全量导出到 `~/.atlas-backups/` |
| `atlas_import` | 从 JSON 备份恢复 |
| `atlas_obsidian_sync` | 立即触发 Obsidian Bridge 导出 |

---

## Obsidian Bridge（可选）

设置环境变量后，atlas-memory 每 6 小时自动将记忆导出为 Obsidian 笔记，用于可视化监控 AI 的记忆进化过程。

```bash
# ~/.zshrc
export ATLAS_OBSIDIAN_VAULT="/path/to/your/vault"
```

导出结构（只读镜像，不要直接编辑）：
```
Atlas_Mirror/
├── _index.md              # Dataview 仪表盘
├── _evolution/
│   └── YYYY-MM-DD.md      # 每日进化日志
└── [type] topic.md        # 按 memory_type + 标签聚类的记忆文件
```

---

## 仓库结构

```
ATLAS-MemoryCore/
├── openclaw-plugin/       # OpenClaw 插件（当前主体）
│   ├── index.js           # 插件主文件 v9.4.0
│   ├── openclaw.plugin.json
│   └── README.md
└── setup/
    ├── SETUP.md           # 完整安装文档
    └── openclaw.template.json  # 配置模板（无 API Key）
```

---

## License

MIT
