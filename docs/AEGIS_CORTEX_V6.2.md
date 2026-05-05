# Aegis-Cortex V6.2 架构文档

## 🏗️ 架构概述

Aegis-Cortex V6.2 是 ATLAS-MemoryCore 的实验性架构分支，围绕向量嵌入压缩与多级检索过滤两个核心问题展开探索。

> **注意**：本分支的性能数据来自开发过程中的合成测试，尚未经过与 baseline RAG 的系统对比，数值仅供参考。

### 核心组件

1. **分组量化压缩** - 4-bit 分组量化（group_size=128），减少向量存储占用约 75%
2. **四级过滤检索系统** - 元数据 → 向量 → 重要性 → 时间衰减
3. **Token 经济模型** - 实时成本监控和自动降级
4. **夜间净化循环** - 基于艾宾浩斯遗忘曲线的智能记忆管理

## 📊 性能指标

> 以下数据来自开发过程中的合成基准（mock Qdrant + 随机向量），**不代表真实场景性能**。
> 真实场景对比见 `benchmark/retrieval_comparison.py`。

| 指标 | 朴素向量搜索 | 四级过滤检索 | 说明 |
|------|------------|------------|------|
| 压缩后存储占用 | 100% | ~25% | 4-bit 量化，解压时有精度损失 |
| 检索延迟（本地 Qdrant） | ~5ms | ~8ms | 多级过滤增加约 3ms 开销 |
| 上下文精度 | 未测量 | 未测量 | 缺乏标注数据集，待补充 |

## 🧩 核心组件

### 1. 分组量化压缩器 (`turboquant_compressor.py`)

```python
# 实现：分组 4-bit 量化
- 将向量按 group_size=128 分组
- 每组独立计算 scale 和 zero-point
- 量化到 4-bit 整数（0-15），减少约 75% 存储空间
- 解压通过线性变换还原：x = q * scale + zero
# 注意：仅减少向量存储开销，不能减少 LLM token 消耗
```

### 2. 四级过滤检索 (`four_stage_filter.py`)

```python
# 四个过滤阶段
1. 元数据预过滤 - 基于 category/urgency/domain
2. 向量相似度过滤 - 余弦相似度 > 0.82
3. 重要性分数过滤 - score > 0.5 + 分层阈值
4. 时间衰减调整 - 艾宾浩斯遗忘曲线加权
```

### 3. Token 经济监控 (`token_economy.py`)

```python
# 核心功能
- 实时 Token 消耗统计
- 成本预测和预警
- 自动降级策略
- 每日/每周报告
```

### 4. Aegis 协调器 (`aegis_orchestrator.py`)

```python
# 统一管理
- 组件初始化和管理
- 查询处理流程协调
- 系统状态监控
- 夜间任务调度
```

## ⚙️ 配置系统

### 配置文件 (`config/aegis_config.yaml`)

```yaml
# 关键配置项
turboquant:
  enabled: true
  compression_ratio: 0.25  # 25% 保留
  quantization_bits: 4     # 4位量化

four_stage_filter:
  similarity_threshold: 0.82
  importance_threshold: 0.5
  use_ebbinghaus_decay: true

token_economy:
  max_tokens_per_query: 1000
  token_cost_warning_threshold: 50.0

nocturnal_optimization:
  optimization_time: "03:00"  # 凌晨3点
  forget_threshold: 0.3
  upgrade_threshold: 0.85
```

## 🚀 快速开始

### 安装依赖

```bash
# 基础依赖
pip install numpy sentence-transformers qdrant-client

# 启动 Qdrant
docker run -p 6333:6333 qdrant/qdrant
```

### 基本使用

```python
from core.aegis_orchestrator import get_global_orchestrator
from core.qdrant_storage import QdrantMemoryStorage
from core.scoring import MemoryScoringEngine
from core.embedding import EmbeddingModel

# 初始化
orchestrator = get_global_orchestrator()
qdrant_storage = QdrantMemoryStorage()
scoring_engine = MemoryScoringEngine()
embedding_model = EmbeddingModel()

# 处理查询
context = orchestrator.create_context(
    query="用户查询",
    qdrant_storage=qdrant_storage,
    scoring_engine=scoring_engine,
    embedding_model=embedding_model
)

result = orchestrator.process_query(context)
print(f"压缩后上下文: {result.compressed_context}")
print(f"Token 消耗: {result.token_usage}")
```

## 🐳 Docker 部署

### 使用 Docker Compose

```bash
# 完整部署
./deploy.sh compose

# 或手动部署
docker-compose up -d
```

### 服务访问

- **API 服务**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **Qdrant 管理**: http://localhost:6333/dashboard
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

## 📈 监控和运维

### 健康检查

```bash
# API 健康检查
curl http://localhost:8000/health

# 系统状态
curl http://localhost:8000/api/v1/status

# Token 报告
curl http://localhost:8000/api/v1/token-economy/report?report_type=daily
```

### 性能监控

1. **Prometheus**: 收集系统指标
2. **Grafana**: 可视化监控面板
3. **Token 经济仪表板**: 实时成本监控
4. **记忆系统仪表板**: 检索性能和记忆状态

## 🔧 故障排除

### 常见问题

1. **Qdrant 连接失败**
   ```bash
   # 检查 Qdrant 服务
   curl http://localhost:6333/health
   
   # 重启服务
   docker restart atlas-qdrant
   ```

2. **Token 成本过高**
   ```yaml
   # 调整配置
   token_economy:
     max_tokens_per_query: 500  # 降低限制
     auto_downgrade_enabled: true
   ```

3. **检索精度下降**
   ```yaml
   # 调整过滤阈值
   four_stage_filter:
     similarity_threshold: 0.75  # 降低阈值
     importance_threshold: 0.4   # 降低重要性要求
   ```

### 日志查看

```bash
# Docker 日志
docker-compose logs -f aegis-cortex

# 应用日志
tail -f logs/aegis_cortex.log
```

## 🔄 升级和维护

### 定期维护任务

1. **夜间净化** (自动)
   - 时间: 每天 03:00
   - 任务: 记忆清理、压缩、优化

2. **Token 报告** (自动)
   - 每日报告: 00:00
   - 每周报告: 周日 00:00

3. **备份任务** (建议)
   ```bash
   # 备份 Qdrant 数据
   docker exec atlas-qdrant qdrant backup --output-dir /backup
   ```

### 版本升级

```bash
# 拉取最新代码
git pull origin main

# 重建 Docker 镜像
./deploy.sh build

# 重启服务
docker-compose down
docker-compose up -d
```

## 📚 API 参考

### 主要端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/query` | POST | 处理查询 |
| `/api/v1/status` | GET | 系统状态 |
| `/api/v1/token-economy/report` | GET | Token 报告 |
| `/api/v1/optimize` | POST | 触发优化 |
| `/api/v1/metrics` | GET | 监控指标 |
| `/api/v1/config` | GET | 当前配置 |

### 查询示例

```bash
# 处理查询
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "用户的咖啡偏好是什么？"}'

# 获取 Token 报告
curl "http://localhost:8000/api/v1/token-economy/report?report_type=daily"
```

## 🎯 最佳实践

### 配置优化

1. **生产环境配置**
   ```yaml
   turboquant:
     use_gpu: true  # 如果有 GPU
     batch_size: 64  # 增加批处理大小
   
   four_stage_filter:
     cache_ttl_seconds: 600  # 增加缓存时间
   ```

2. **Token 成本控制**
   ```yaml
   token_economy:
     daily_token_budget: 100.0  # 设置每日预算
     downgrade_thresholds:
       critical: 0.8  # 提前降级
   ```

3. **性能调优**
   ```yaml
   nocturnal_optimization:
     optimization_batch_size: 2000  # 增加批处理
     compression_batch_size: 500
   ```

### 监控建议

1. **关键指标监控**
   - Token 成本/查询
   - 检索精度
   - 系统响应时间
   - 记忆存储使用率

2. **告警设置**
   - Token 成本超过阈值
   - 系统健康状态异常
   - 存储空间不足
   - 检索性能下降

## 📞 支持和贡献

### 获取帮助

1. **文档**: 查看本项目文档
2. **问题跟踪**: GitHub Issues
3. **社区**: Discord 社区

### 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 创建 Pull Request

### 开发环境设置

```bash
# 克隆项目
git clone https://github.com/luogangan7-lgtm/ATLAS-MemoryCore.git

# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest tests/

# 代码格式化
black src/
isort src/
```

## 📄 许可证

MIT License - 详见 LICENSE 文件

## 🙏 致谢

- Qdrant 向量数据库团队
- Sentence Transformers 项目
- 所有贡献者和用户

---

**版本**: 6.2.0  
**最后更新**: 2026-04-21  
**维护者**: ATLAS (Eidos.β) 团队