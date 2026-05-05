# Changelog

All notable changes to ATLAS Memory are documented here.

---

## [v12.0.0] — 2026-05-05

### Added

- **实体注册层**：`upsertEntity` — 以 `stableId(canonical_name+'_entity')` 为 Qdrant point ID，保证同名实体幂等写入；支持 aliases、domains、definition 合并更新
- **关系图**：`upsertRelation` — 7种关系类型（supports / contradicts / extends / depends_on / used_in / evolved_from / cross_domain），stableId 保证幂等
- **atlas_intake 统一录入入口**：接受任意内容，自动检测分片信号（`第N/M部分`、`Part N of M`、`(续)`、`[N/M]`、`待续`等），立即写入 L0 并触发后台提炼，无需等待
- **RECORD_TYPES 三元分类**：knowledge / entity / relation，qdrantSearch 默认只返回知识节点，排除实体和关系记录
- **confidence 自动演化**：`calcConfidence(hitCount) = 1 - 0.4 × 0.85^hitCount`，每次检索命中自动更新，初始 0.60，随使用趋近 0.99
- **5 个新知识域**：短视频生产、自动化工具、人际沟通、交易投资、新闻热点（总计 14 个域）
- **extractL1Content 重写**：DeepSeek only（移除 omlx），支持多节点输出（一个 L0 → 多个 L1），同时提取实体和关系，按 content_type 生成类型特定字段（video_script / trading_signal / sop）
- **runOrganizeAgent 重写**：nodes[0] 复用原 L0 ID，nodes[1+] 新建 point，自动调用 upsertEntity + upsertRelation，更新 entity_ids / relation_ids 反向索引
- **qdrantSearch 实体扩展**：`expand_entities=true` 时，基于命中节点的 entity_ids 进行 scroll 扩展，召回更多关联节点
- **atlas_recall 新参数**：`min_confidence`（置信度过滤）、`expand_entities`（实体扩展）、`intent`（relevant/latest）
- **atlas_stats v12**：返回 entity_count / relation_count / knowledge_count 分类统计
- **EMBED_SAFE_CHARS = 6000**：bge-m3 8192 token ≈ 6000 中文字安全截断常量

### Changed

- **DeepSeek 模型**：统一使用 `deepseek-v4-flash`，移除 omlx（本地算力不足）
- **atlas_store**：`additionalProperties: true`，支持任意额外字段透传
- **intakeToL0**：新增参数 `group_id / chunk_index / group_total / content_type / source_meta`，payload 新增 `record_type / confidence / entity_ids / relation_ids`

### Removed

- omlx/本地模型依赖（所有 LLM 提炼统一走 DeepSeek）
- 手动 `atlas_feedback` 驱动的 confidence 提升（已被 hit_count 自动演化取代，feedback 保留为辅助工具）

---

## [v11.0.0] — 2026-05-04

### Added

- `source_type` 字段：区分 mcp / plugin / agent_end / llm_output 等来源
- TTL 支持：`expires_at` 字段 + 搜索时自动过滤过期记录
- 意图检索：`intent=latest` 时时间衰减权重加大，`intent=relevant` 为默认语义相关
- MCP Server 迁移至端口 8766，collection 升级为 `atlas_memories_v2`（bge-m3 1024维）
- `freshness_score` + `decay_rate`：基于域和来源推断的自然衰减速率

### Changed

- Embed 模型：nomic-embed-text（768维）→ bge-m3（1024维），collection 需重建
- MCP 端口：8765 → 8766

---

## [v10.0.0] — 2026-05-01

### Added

- 四层知识成熟度：L0 原料 → L1 知识 → L2 洞见 → L3 框架
- `L1CompletionAgent`：后台自动将 L0 提炼为 L1
- 分层注入：L3→L2→L1→L0 优先级注入上下文
- `atlas_feedback`：correct / wrong / outdated 评分
- `atlas_distill`：手动多节点归纳
- `atlas_evolve`：域结构重组（合并/分裂）
- Obsidian Bridge：L1/L2/L3 分层导出
- LRU Embed 缓存（200条）

### Changed

- 首个稳定生产版本，从 v9.x 重构

---

## [v0.1.0] — 2026-05-05 *(初始公开版本)*

- 首次将 openclaw-plugin 发布到 GitHub
- 包含 v10 插件主文件和基准测试脚本
