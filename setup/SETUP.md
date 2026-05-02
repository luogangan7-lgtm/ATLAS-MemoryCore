# ATLAS Memory — 安装配置指南

> atlas-memory v9.5.0 | OpenClaw 2026.4.x | 2026-05-03

---

## 一、前置依赖

### 本地服务（必须）

| 依赖 | 安装方式 | 用途 |
|------|----------|------|
| **Qdrant** | `docker run -d -p 6333:6333 --restart unless-stopped qdrant/qdrant` | 向量数据库 |
| **Ollama** | [ollama.com](https://ollama.com) 下载安装 | 文本嵌入服务 |
| **nomic-embed-text** | `ollama pull nomic-embed-text:latest` | 768-dim 向量嵌入（274MB） |
| **omlx** | 按 omlx 文档安装 | 事实提取 / 冲突检测 |
| **Qwen3.5-9B-OptiQ-4bit** | 在 omlx 中加载 | 本地推理，4s/call |

### 云端服务（可选，用于知识提炼）

| 服务 | 获取方式 | 用途 |
|------|----------|------|
| **DeepSeek API Key** | [platform.deepseek.com](https://platform.deepseek.com) | `atlas_distill` 知识合成 |

> `DEEPSEEK_API_KEY` 未配置时，distill 功能自动回退到本地 omlx，所有其他功能不受影响。

启动确认：

```bash
curl http://127.0.0.1:6333/healthz          # Qdrant ✓
curl http://127.0.0.1:11434/api/tags        # Ollama ✓
curl http://127.0.0.1:7749/v1/models        # omlx ✓
```

---

## 二、模型选型参考

### 本地嵌入模型

| 模型 | 维度 | 大小 | 说明 |
|------|------|------|------|
| `nomic-embed-text:latest`（**当前默认**） | 768 | 274MB | 速度快，中英文均可 |
| `mxbai-embed-large` | 1024 | 670MB | 精度更高，需重建 Qdrant collection |

> ⚠️ 切换嵌入模型需同步修改常量 `VECTOR_DIM` 并删除重建 `atlas_memories` collection，否则已有记忆向量失效。

### 本地推理模型（omlx）

| 模型 | 速度 | 说明 |
|------|------|------|
| `Qwen3.5-9B-OptiQ-4bit`（**当前默认**） | 4s/call | thinking模式需关闭（见陷阱7.5） |
| `Qwen2.5-7B-Instruct` | 2–3s/call | 速度更快，提取精度稍低 |

### 云端推理模型（DeepSeek，仅 distill）

| 模型 | 输入/输出（per 1M tokens） | 说明 |
|------|--------------------------|------|
| `deepseek-chat`（**当前默认**） | $0.28 / $0.42 | 知识提炼，性价比最优 |
| `deepseek-v4-flash` | $0.14 / $0.28 | 更快更便宜，适合批量提炼 |
| `deepseek-v4-pro` | $1.74 / $3.48 | 复杂推理，通常不必要 |

---

## 三、哪些操作调用云端模型

| 操作 | 调用模型 | 频率 | 估算费用 |
|------|---------|------|---------|
| INJECT 自动检索 | 本地 Qdrant + Ollama | 每次提问 | $0 |
| CAPTURE 自动捕获 | 本地 omlx | 每次对话结束 | $0 |
| LEARN 网页学习 | 本地 omlx | 每次搜索工具调用 | $0 |
| atlas_recall | 本地 Qdrant + Ollama | 手动调用 | $0 |
| atlas_feedback | 本地 Qdrant（无LLM） | 手动调用 | $0 |
| atlas_merge | 本地 omlx | 手动调用 | $0 |
| **atlas_distill** | **DeepSeek deepseek-chat** | 手动 / EVOLVE 24h 自动（≥5条同标签） | **≈$0.0003/次** |
| EVOLVE 自动提炼 | **DeepSeek deepseek-chat** | 每24h最多3个标签 | **≈$0.001/天** |

**月消耗上限估算：** 正常使用场景 < $0.05/月。

---

## 四、安装 OpenClaw

```bash
npm install -g openclaw
openclaw setup
```

---

## 五、部署 atlas-memory 插件

```bash
# 1. 创建插件目录
mkdir -p ~/.openclaw/hooks/atlas-memory

# 2. 克隆本仓库
git clone https://github.com/luogangan7-lgtm/ATLAS-MemoryCore /tmp/ATLAS-MemoryCore

# 3. 复制插件文件
cp /tmp/ATLAS-MemoryCore/openclaw-plugin/index.js ~/.openclaw/hooks/atlas-memory/
cp /tmp/ATLAS-MemoryCore/openclaw-plugin/openclaw.plugin.json ~/.openclaw/hooks/atlas-memory/

# 4. 复制配置模板
cp /tmp/ATLAS-MemoryCore/setup/openclaw.template.json ~/.openclaw/openclaw.json
```

---

## 六、填写配置

编辑 `~/.openclaw/openclaw.json`，替换以下占位符：

| 占位符 | 替换为 | 是否必须 |
|--------|--------|---------|
| `YOUR_DEEPSEEK_API_KEY` | DeepSeek API Key | 可选（distill回退omlx） |
| `YOUR_ANTHROPIC_API_KEY` | Anthropic API Key | 按需 |
| `YOUR_OMLX_API_KEY` | omlx 本地服务密钥 | 必须 |
| `YOUR_TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 可选 |
| `YOUR_TELEGRAM_USER_ID` | Telegram 用户 ID | 可选 |

> **重要：** `agents.defaults.model.fallbacks` 是合法的路由配置字段。  
> 模型定义（`models.providers.*.models[]`）**不支持** `fallbacks` 字段，否则启动失败。

---

## 七、配置 DeepSeek API Key（可选）

DeepSeek API Key 需要在 OpenClaw gateway **启动前**设置为环境变量：

```bash
# 方式一：在启动脚本或 shell profile 中设置
export DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# 方式二：在 ~/.openclaw/openclaw.json 的 env.vars 中添加
# "DEEPSEEK_API_KEY": "sk-xxxxxxxxxxxxxxxx"
```

> ⚠️ OpenClaw 作为 LaunchAgent 运行时不继承 shell 环境变量，推荐使用方式二写入 openclaw.json。

---

## 八、初始化 Qdrant Collection

首次启动前创建 collection（768维，如已存在可跳过）：

```bash
curl -X PUT http://127.0.0.1:6333/collections/atlas_memories \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": { "size": 768, "distance": "Cosine" },
    "on_disk_payload": true
  }'
```

---

## 九、启动 OpenClaw

```bash
openclaw gateway start
openclaw gateway status
```

验证 atlas-memory 插件已加载并确认工具注册（应看到13个 atlas_* 工具）：

```bash
openclaw gateway status --deep
```

---

## 十、已知配置陷阱

### 10.1 上下文压缩死循环
`compaction.reserveTokensFloor` 必须设为 **8000+**，否则压缩后剩余 token 不足，立即触发再次压缩。

### 10.2 DeepSeek 上下文窗口
DeepSeek V4 Flash/Pro 的 `contextWindow` 必须设为 **1000000**（支持 1M context）。设为 65536 会导致频繁压缩。

### 10.3 omlx thinking mode
omlx Qwen3.5-9B 默认开启 thinking mode，导致每次调用约 60s。**在 omlx 配置中关闭 thinking mode**，降至 4s/call。

### 10.4 Proxy 干扰本地服务
macOS 系统代理（如 127.0.0.1:1082）可能拦截 Qdrant / Ollama / omlx 的 HTTP 请求。atlas-memory 使用 Node.js 原生 `http.request`，已绕过系统代理，无需额外配置。

### 10.5 LaunchAgent 环境变量
OpenClaw 作为 LaunchAgent 运行时不继承 shell 的 `export` 变量。`DEEPSEEK_API_KEY`、`ATLAS_OBSIDIAN_VAULT` 等需写入 `openclaw.json` 的 `env.vars` 节，或在 `service-env/ai.openclaw.gateway.env` 中添加 `export` 语句。

### 10.6 模型切换后向量失效
切换嵌入模型（如从 nomic-embed-text 换为 mxbai-embed-large）后，已有记忆的向量维度不匹配，必须重建 collection 并重新导入（先 `atlas_export` 备份，再删除 collection，重建后 `atlas_import`）。

---

## 十一、可选：Obsidian Bridge

在 `openclaw.json` 的 `env.vars` 中设置 vault 路径：

```json
"ATLAS_OBSIDIAN_VAULT": "/path/to/your/obsidian/vault"
```

重启 OpenClaw 后，每 6 小时自动导出记忆快照到 vault 的 `Atlas_Mirror/` 目录：

- `Atlas_Mirror/_index.md` — Dataview 仪表盘（需安装 Dataview 插件）
- `Atlas_Mirror/_evolution/YYYY-MM-DD.md` — 每日进化日志（CAPTURE / DISTILL / FEEDBACK / PRUNE）
- `Atlas_Mirror/[type] topic.md` — 按 memory_type + 标签聚类的记忆文件

> ⚠️ Atlas_Mirror 是**只读镜像**，下次导出会覆盖手动编辑内容。

---

## 十二、升级到新版本

```bash
cd /tmp/ATLAS-MemoryCore && git pull
cp openclaw-plugin/index.js ~/.openclaw/hooks/atlas-memory/
openclaw gateway restart
```

升级 v9.4.0 → v9.5.0 注意事项：
- 已有记忆（无 `status` / `feedback_score` 字段）自动兼容，INJECT/CAPTURE 正常工作
- 新写入的记忆会携带 `status: 'active'` 和 `feedback_score: 1.0` 字段
- `DEEPSEEK_API_KEY` 未配置时 distill 回退 omlx，无需额外操作

---

## 十三、工具速查

| 工具 | 功能 | 模型 |
|------|------|------|
| `atlas_store` | 手动存储（含冲突检测去重） | omlx |
| `atlas_recall` | 语义检索（时间衰减 + 访问计数） | Ollama embed |
| `atlas_feedback` | 反馈评价（负评累积自动删除） | 无LLM |
| `atlas_distill` | 知识提炼生成通则 | **DeepSeek**（omlx备用） |
| `atlas_timeline` | 标签时间线查询 | 无LLM |
| `atlas_evolve` | 手动触发去重+清理+自动提炼 | omlx / **DeepSeek** |
| `atlas_merge` | 智能合并近重复记忆 | omlx |
| `atlas_delete` | 按语义相似度删除 | Ollama embed |
| `atlas_stats` | 记忆库完整状态 | 无LLM |
| `atlas_web_learn` | URL/文本分块学习 | omlx |
| `atlas_export` | 导出 JSON 备份 | 无LLM |
| `atlas_import` | 从 JSON 备份恢复 | 无LLM |
| `atlas_obsidian_sync` | 手动触发 Obsidian Bridge | 无LLM |
