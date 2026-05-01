# ATLAS Memory — 全新安装配置指南

> atlas-memory v9.4.0 | OpenClaw 2026.4.x | 2026-05-01

---

## 一、前置依赖

| 依赖 | 安装命令 | 用途 |
|------|----------|------|
| Qdrant | `docker run -p 6333:6333 qdrant/qdrant` | 向量数据库 |
| Ollama | [ollama.com](https://ollama.com) | nomic-embed-text 嵌入 |
| nomic-embed-text | `ollama pull nomic-embed-text:latest` | 768-dim 向量嵌入 |
| omlx (本地 LLM) | 按 omlx 文档安装 | 冲突检测 / 提取 / 压缩 |
| Qwen3.5-9B-OptiQ-4bit | 在 omlx 中加载 | 4s/call 推理 |

启动确认：
```bash
curl http://127.0.0.1:6333/healthz          # Qdrant
curl http://127.0.0.1:11434/api/tags        # Ollama
curl http://127.0.0.1:7749/v1/models        # omlx
```

---

## 二、安装 OpenClaw

```bash
npm install -g openclaw
openclaw setup
```

---

## 三、部署 atlas-memory 插件

```bash
# 1. 创建插件目录（默认加载路径）
mkdir -p ~/.openclaw/hooks/atlas-memory

# 2. 克隆本仓库
git clone https://github.com/luogangan7-lgtm/atlas-config-sync /tmp/atlas-config-sync

# 3. 复制插件文件
cp /tmp/atlas-config-sync/atlas-memory/index.js ~/.openclaw/hooks/atlas-memory/
cp /tmp/atlas-config-sync/atlas-memory/openclaw.plugin.json ~/.openclaw/hooks/atlas-memory/

# 4. 复制配置模板
cp /tmp/atlas-config-sync/setup/openclaw.template.json ~/.openclaw/openclaw.json
```

---

## 四、填写配置

编辑 `~/.openclaw/openclaw.json`，替换以下占位符：

| 占位符 | 替换为 |
|--------|--------|
| `YOUR_DEEPSEEK_API_KEY` | DeepSeek API Key |
| `YOUR_ANTHROPIC_API_KEY` | Anthropic API Key |
| `YOUR_OMLX_API_KEY` | omlx API Key (本地服务密钥) |
| `YOUR_TELEGRAM_USER_ID` | Telegram 用户 ID (可选) |
| `~/.openclaw/workspace` | 实际工作区路径 |
| `~/.openclaw/hooks` | 实际插件路径 |

> **注意**：`agents.defaults.model.fallbacks` 字段是合法的路由配置，不是模型定义字段。
> 模型定义（`models.providers.*.models[]`）**不支持** `fallbacks` 字段。

---

## 五、初始化 Qdrant Collection

首次启动前手动创建 collection：

```bash
curl -X PUT http://127.0.0.1:6333/collections/atlas_memories \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 768,
      "distance": "Cosine"
    }
  }'
```

---

## 六、启动 OpenClaw

```bash
openclaw gateway start
openclaw gateway status
```

启动后验证 atlas-memory 插件加载：
```bash
openclaw gateway status --deep
# 应看到 atlas-memory 在插件列表中
```

---

## 七、已知配置陷阱

### 7.1 上下文压缩死循环
`compaction.reserveTokensFloor` 必须设为 **8000+**，否则压缩后剩余 token 不足，下一条消息立即触发再次压缩。

### 7.2 DeepSeek 上下文窗口
DeepSeek V4 Flash/Pro 的 `contextWindow` 必须设为 **1000000**（支持 1M context）。设为 65536 会导致频繁压缩。

### 7.3 LaunchAgent 路径
OpenClaw LaunchAgent plist 中的 `OPENCLAW_STATE_DIR`、`WorkingDirectory`、日志路径必须与实际安装目录一致。如果迁移了数据目录需同步修改：
- `/Users/你的用户名/Library/LaunchAgents/ai.openclaw.gateway.plist`
- `~/.openclaw/service-env/ai.openclaw.gateway.env`

### 7.4 Proxy 干扰 Qdrant
macOS 系统代理（如 127.0.0.1:1082）可能拦截 Qdrant HTTP 请求。atlas-memory 使用 Node.js 原生 `http.request` 绕过代理，无需额外配置。

### 7.5 omlx thinking mode
omlx Qwen3.5-9B 默认开启 thinking mode，导致每次调用约 60s。**在 omlx 配置中关闭 thinking mode**，降至 4s/call。无需在 prompt 中加 `/no_think`。

---

## 八、可选：Obsidian Bridge

在 omlx 或系统环境变量中设置 vault 路径，atlas-memory 会每 6 小时自动导出记忆快照到 `Atlas_Mirror/` 目录：

```bash
# 在 ~/.zshrc 或 ~/.bash_profile 中
export ATLAS_OBSIDIAN_VAULT="/path/to/your/obsidian/vault"
```

重启 OpenClaw 生效。Obsidian 中会出现：
- `Atlas_Mirror/_index.md` — Dataview 仪表盘
- `Atlas_Mirror/_evolution/YYYY-MM-DD.md` — 每日进化日志
- `Atlas_Mirror/[type] topic.md` — 按 memory_type + 标签聚类的记忆文件

> ⚠️ Atlas_Mirror 是**只读镜像**。不要在 Obsidian 中直接编辑这些文件，编辑会在下次导出时被覆盖。

---

## 九、升级

```bash
cd /tmp && git clone https://github.com/luogangan7-lgtm/atlas-config-sync
cp /tmp/atlas-config-sync/atlas-memory/index.js ~/.openclaw/hooks/atlas-memory/
cp /tmp/atlas-config-sync/atlas-memory/openclaw.plugin.json ~/.openclaw/hooks/atlas-memory/
openclaw gateway restart
```

---

## 十、atlas-memory 工具列表

| 工具 | 功能 |
|------|------|
| `atlas_store` | 手动存储记忆（含冲突检测 + 去重） |
| `atlas_recall` | 语义搜索（时间衰减 + 访问计数 + memory_type 显示） |
| `atlas_delete` | 按语义相似性删除 |
| `atlas_stats` | 系统健康：Qdrant + Ollama + omlx + 缓存命中率 + 备份时间 |
| `atlas_evolve` | 去重 + 过期清理（hit_count=0 + 90天 + low importance） |
| `atlas_web_learn` | URL/文本分块学习（≤5块 × 1500字符），质量过滤 |
| `atlas_merge` | 扫描 0.75-0.92 相似度，Qwen3.5 合并近重复为更丰富的事实 |
| `atlas_export` | 全量导出到 `~/.atlas-backups/atlas-backup-YYYY-MM-DD.json` |
| `atlas_import` | 从 JSON 备份恢复（100条/批次） |
| `atlas_obsidian_sync` | 立即触发 Obsidian Bridge 导出 |
