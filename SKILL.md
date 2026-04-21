# atlas-memory

## 功能描述
ATLAS记忆核心系统 - 零Token消耗的智能记忆管理Skill，为OpenClaw提供高效的长时记忆能力。

## 安装要求
- Python 3.12+
- Qdrant向量数据库（本地或Docker）
- OpenClaw 1.0+
- 至少2GB可用内存

## 安装步骤

### 1. 安装Python包
```bash
pip install atlas-memory-core
```

### 2. 启动Qdrant服务
```bash
# 使用Docker（推荐）
docker run -p 6333:6333 qdrant/qdrant

# 或使用本地安装
# 参考：https://qdrant.tech/documentation/quick-start/
```

### 3. 配置OpenClaw
在OpenClaw配置文件（通常为`~/.openclaw/config.yaml`）中添加：

```yaml
skills:
  atlas-memory:
    enabled: true
    qdrant_url: "http://localhost:6333"
    collection_name: "atlas_memories"
    embedding_model: "nomic-ai/nomic-embed-text-v1.5"
    
    # 可选配置
    auto_optimize: true
    optimization_time: "03:00"  # 每天凌晨3点自动优化
    max_memories: 10000  # 最大记忆数量
    similarity_threshold: 0.82  # 检索相似度阈值
```

## 配置说明

### 必需配置
- `qdrant_url`: Qdrant服务地址（默认：http://localhost:6333）
- `collection_name`: 向量集合名称（默认：atlas_memories）

### 可选配置
- `embedding_model`: 嵌入模型名称（默认：nomic-ai/nomic-embed-text-v1.5）
- `auto_optimize`: 是否启用自动优化（默认：true）
- `optimization_time`: 自动优化时间（格式：HH:MM）
- `max_memories`: 最大记忆数量限制
- `similarity_threshold`: 检索相似度阈值（0.0-1.0）
- `cache_size`: 内存缓存大小（默认：1000）
- `log_level`: 日志级别（debug/info/warning/error）

## 命令列表

### 基础命令
- `/memory store <内容>` - 存储新的记忆
- `/memory search <查询>` - 搜索相关记忆
- `/memory stats` - 查看记忆系统统计
- `/memory list [数量]` - 列出最近的记忆

### 管理命令
- `/memory optimize` - 手动运行记忆优化
- `/memory clear [确认码]` - 清空所有记忆（需要确认）
- `/memory export <文件路径>` - 导出记忆到文件
- `/memory import <文件路径>` - 从文件导入记忆

### 调试命令
- `/memory debug info` - 显示调试信息
- `/memory debug test` - 运行系统测试
- `/memory debug reset` - 重置系统状态

## 使用示例

### 存储记忆
```
用户：/memory store 今天学习了Python异步编程，asyncio库很强大
ATLAS：✅ 记忆已存储（ID: mem_abc123，重要性: 0.7）
```

### 搜索记忆
```
用户：/memory search Python异步编程
ATLAS：🔍 找到3条相关记忆：
1. [0.92] 今天学习了Python异步编程，asyncio库很强大
2. [0.85] 上周解决了asyncio的并发问题
3. [0.78] Python协程的最佳实践总结
```

### 查看统计
```
用户：/memory stats
ATLAS：📊 记忆系统统计：
- 总记忆数：1,247
- 今日新增：15
- 平均重要性：0.68
- 检索命中率：89%
- 存储使用：245MB
```

## 高级功能

### 1. 自动分类
系统会自动为记忆添加分类标签，如：
- `category: learning` - 学习内容
- `category: trading` - 交易相关
- `category: code` - 代码片段
- `category: personal` - 个人信息

### 2. 重要性评分
每条记忆都会自动评分（0.0-1.0），基于：
- 内容长度和复杂度
- 关键词重要性
- 用户交互频率
- 时间衰减因素

### 3. 夜间优化
每天凌晨自动运行优化任务：
- 重新计算记忆重要性
- 清理低重要性记忆
- 压缩重复内容
- 更新索引结构

### 4. 上下文感知
在对话中自动检索相关记忆，无需手动搜索。

## 集成API

### Python API
```python
from atlas_memory import AtlasMemory

# 初始化
memory = AtlasMemory(config_path="~/.openclaw/config.yaml")

# 存储记忆
memory_id = memory.store(
    text="重要的项目信息",
    metadata={"category": "project", "importance": 0.9}
)

# 搜索记忆
results = memory.search("项目信息", limit=5)

# 获取统计
stats = memory.get_stats()
```

### REST API（可选）
启动REST服务：
```bash
atlas-memory serve --port 8080
```

API端点：
- `POST /api/v1/memories` - 存储记忆
- `GET /api/v1/memories/search` - 搜索记忆
- `GET /api/v1/memories/stats` - 获取统计
- `POST /api/v1/memories/optimize` - 手动优化

## 故障排除

### 常见问题

1. **Qdrant连接失败**
   ```
   错误：无法连接到Qdrant服务
   解决：确保Qdrant服务正在运行：docker ps | grep qdrant
   ```

2. **嵌入模型下载慢**
   ```
   错误：下载嵌入模型超时
   解决：使用国内镜像或手动下载模型
   ```

3. **内存不足**
   ```
   错误：内存分配失败
   解决：增加系统内存或减少cache_size配置
   ```

### 日志查看
```bash
# 查看OpenClaw日志
openclaw logs --skill atlas-memory

# 查看详细调试日志
openclaw logs --level debug --skill atlas-memory
```

## 性能优化建议

1. **硬件要求**
   - CPU: 4核以上（推荐）
   - 内存: 8GB+（处理大量记忆时）
   - 存储: SSD（提升检索速度）

2. **配置优化**
   - 调整`similarity_threshold`平衡精度和召回率
   - 设置合理的`max_memories`防止内存溢出
   - 启用`auto_optimize`保持系统健康

3. **使用建议**
   - 为重要记忆添加明确的metadata
   - 定期使用`/memory optimize`手动优化
   - 使用分类标签提高检索精度

## 更新日志

### v0.1.0 (2026-04-21)
- 初始版本发布
- 基础记忆存储和检索
- OpenClaw Skill集成
- 自动分类和评分

### 计划功能
- 多模态记忆支持（图像、音频）
- 分布式记忆同步
- 高级分析仪表板
- 移动端应用

## 技术支持

- GitHub Issues: [问题反馈](https://github.com/yourusername/atlas-memory-core/issues)
- 文档: [详细文档](https://yourusername.github.io/atlas-memory-core/)
- 社区: [OpenClaw Discord](https://discord.com/invite/clawd)

## 许可证
MIT License - 详见[LICENSE](https://github.com/yourusername/atlas-memory-core/blob/main/LICENSE)

---

**ATLAS记忆核心** - 让AI记住一切，却不用花费一分Token。