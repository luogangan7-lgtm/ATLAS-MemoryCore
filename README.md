# ATLAS Memory v12

> OpenClaw 语义记忆插件 — 多域知识库 · 实体注册 · 关系图 · 置信度演化 · DeepSeek 提炼

---

## 简介

ATLAS Memory 是为 [OpenClaw](https://openclaw.ai) 设计的持久化知识系统。v12 在原有四层知识成熟度体系的基础上，引入**实体注册层**和**关系图**，让知识节点之间形成有向图结构，支持跨域关联与语义扩展检索。

**核心能力：**
- 任意内容一键录入（`atlas_intake`），自动识别分片、自动提炼
- bge-m3（1024维）向量检索，DeepSeek deepseek-v4-flash 知识提炼
- 实体去重注册（`upsertEntity`）+ 关系图（`upsertRelation`）
- 命中次数自动驱动 confidence 演化，无需用户手动反馈
- 14 个知识域自动分类，支持域的自动创建与合并
- MCP Server 端口 8766，兼容所有 MCP 客户端

---

## 架构

### 三种记录类型（RECORD_TYPES）

| 类型 | 说明 | Qdrant 存储方式 |
|------|------|----------------|
| `knowledge` | 知识节点（L0 原料 / L1 提炼） | 向量 + payload |
| `entity` | 实体注册（跨域可复用概念） | 向量 + payload，stableId 幂等 |
| `relation` | 节点间有向关系 | 向量 + payload，stableId 幂等 |

### 七种关系类型（RELATION_TYPES）

`supports` · `contradicts` · `extends` · `depends_on` · `used_in` · `evolved_from` · `cross_domain`

### 知识成熟度（Level）

```
L0  原料      — 原始录入，待提炼
L1  知识节点  — DeepSeek 提炼，结构化，confidence 可演化
L2  洞见      — 多节点归纳（自动）
L3  框架      — 域级方法论（自动）
```

### Confidence 演化

```
初始 confidence = 0.6
每次被检索命中：confidence = 1 - 0.4 × 0.85^hit_count
```

| hit_count | confidence |
|-----------|-----------|
| 0 | 0.60 |
| 1 | 0.66 |
| 5 | 0.82 |
| 10 | 0.92 |
| 20 | 0.98 |
| 50 | 0.99 |

---

## 知识域（14个）

| 域 | 关键词 |
|----|--------|
| 短视频生产 | 脚本 剪辑 钩子 开场 爆款 完播率 |
| 自动化工具 | 自动化 脚本 工作流 OpenClaw MCP |
| 人际沟通 | 微信聊天 话术 谈判 说服 客户沟通 |
| 交易投资 | 加密货币 比特币 交易信号 止损 止盈 |
| 新闻热点 | 热搜 突发 今日热点 实时资讯 |
| 营销策略 | 转化漏斗 增长黑客 用户画像 |
| 产品设计 | 用户故事 MVP 原型 |
| 技术架构 | 微服务 数据库 API 设计 |
| 认知学习 | 学习方法 记忆 思维模型 |
| 健康生活 | 运动 营养 睡眠 |
| 创业商业 | 商业模式 融资 团队 |
| 内容创作 | 写作 文案 选题 |
| 职场效率 | GTD 时间管理 |
| 个人财务 | 预算 记账 理财 |

域支持自动创建（相似度 < 0.88 时）和自动合并（凝聚度 < 0.55 时）。

---

## MCP 工具

### `atlas_intake` — 统一录入入口（推荐）

任意内容录入，自动检测分片信号，立即写 L0，触发后台提炼。

```json
{
  "content": "短视频钩子句写法：痛点切入型、好奇心型、利益承诺型...",
  "content_type": "video_script",
  "domain": "短视频生产",
  "tags": ["钩子句", "开场"],
  "importance": "high"
}
```

**分片信号自动检测：** `第1/3部分`、`Part 1 of 3`、`(续)`、`[2/4]`、`待续` 等，自动分配 `group_id` 关联同源分片。

### `atlas_store` — 直接存储

适合 Agent 已处理好的结构化内容，支持任意额外字段（`additionalProperties: true`）。

### `atlas_recall` — 语义检索

```json
{
  "query": "短视频钩子句怎么写",
  "limit": 5,
  "domain": "短视频生产",
  "min_confidence": 0.7,
  "expand_entities": true,
  "intent": "relevant"
}
```

`expand_entities=true` 会基于命中节点的实体 ID 扩展搜索范围，召回相关联的知识节点。

### `atlas_stats` — 统计信息

返回：`total_points` / `entity_count` / `relation_count` / `knowledge_count` / `version`

### 其他工具

| 工具 | 说明 |
|------|------|
| `atlas_search` | 带分类/域过滤的向量检索 |
| `atlas_update` | 修正知识内容 |
| `atlas_feedback` | 手动标记质量（补充自动演化） |
| `atlas_distill` | 手动触发多节点归纳 |
| `atlas_evolve` | 手动触发域结构重组 |
| `atlas_export` | 导出到 Obsidian |

---

## 安装

### 前置要求

- [OpenClaw](https://openclaw.ai) >= 2026.4
- [Qdrant](https://qdrant.tech) 本地运行（默认 `http://127.0.0.1:6333`）
- [Ollama](https://ollama.ai) + `bge-m3` 模型（1024维 Embed）
- DeepSeek API Key（用于知识提炼）

```bash
# 安装 bge-m3
ollama pull bge-m3

# 启动 Qdrant（Docker）
docker run -p 6333:6333 qdrant/qdrant
```

### 插件安装

将 `openclaw-plugin/` 目录内容复制到 OpenClaw 的 `hooks/atlas-memory/` 路径下，重启 OpenClaw 生效。

在 `openclaw.json` 的 `plugins.entries` 中配置：

```json
{
  "plugins": {
    "entries": {
      "atlas-memory": {
        "enabled": true,
        "config": {
          "qdrant_url": "http://127.0.0.1:6333",
          "collection": "atlas_memories_v2",
          "ollama_url": "http://127.0.0.1:11434",
          "embed_model": "bge-m3"
        }
      }
    }
  },
  "env": {
    "vars": {
      "DEEPSEEK_API_KEY": "sk-..."
    }
  }
}
```

### 从 v10/v11 迁移

collection 名称已变更：`atlas_memories` → `atlas_memories_v2`（bge-m3 1024维向量，不兼容旧 768维数据）。

迁移脚本：`scripts/migrate_v1_to_v2.js`

---

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `qdrant_url` | `http://127.0.0.1:6333` | Qdrant 服务地址 |
| `collection` | `atlas_memories_v2` | Qdrant collection 名 |
| `ollama_url` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `embed_model` | `bge-m3` | 嵌入模型（1024维） |
| `deepseek_url` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `mcp_port` | `8766` | MCP Server 端口 |

环境变量：`DEEPSEEK_API_KEY`、`ATLAS_MCP_PORT`、`ATLAS_QDRANT_URL`、`ATLAS_COLLECTION`

---

## 测试

```bash
# 集成测试（需要 Qdrant + bge-m3 + DeepSeek）
DEEPSEEK_API_KEY=sk-... node tests/integration_test.mjs
```

集成测试覆盖：Qdrant 连通性、bge-m3 Embed、DeepSeek 提炼、实体/关系写入读回、qdrantSearch 过滤、confidence 演化、数据完整性（自动清理测试数据）。

---

## 版本历史

见 [CHANGELOG.md](CHANGELOG.md)。

---

## License

MIT
