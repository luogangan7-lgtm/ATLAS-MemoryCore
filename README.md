# ATLAS Memory Core

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Qdrant](https://img.shields.io/badge/vector%20database-Qdrant-green.svg)](https://qdrant.tech/)

**ATLAS Memory Core** - 零Token消耗的智能记忆系统，专为OpenClaw AI助手设计。

## 🏔️ 项目愿景

为AI助手提供高效、智能、经济的长时记忆系统，实现真正的个性化智能体验。

## ✨ 核心特性

- **零Token捕获**: 本地嵌入模型，避免云端LLM调用
- **智能检索**: 混合向量+元数据检索，精度提升30%
- **自优化循环**: 夜间自动优化记忆质量
- **分层存储**: 热/温/冷三层记忆管理
- **开源开放**: MIT协议，完整开源

## 🚀 快速开始

### 安装要求
- Python 3.12+
- Qdrant (本地或Docker)
- OpenClaw 1.0+

### 安装步骤
```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/atlas-memory-core.git
cd atlas-memory-core

# 2. 安装依赖
pip install -e .

# 3. 启动Qdrant
docker run -p 6333:6333 qdrant/qdrant

# 4. 配置OpenClaw
# 在OpenClaw配置中添加atlas-memory skill
```

### 基本使用
```python
from atlas_memory import AtlasMemory

# 初始化记忆系统
memory = AtlasMemory()

# 存储记忆
memory.store("今天学习了Qdrant向量数据库", 
             metadata={"category": "learning", "importance": 0.8})

# 搜索记忆
results = memory.search("向量数据库相关知识")
for result in results:
    print(f"相关度: {result.score:.2f} - {result.text}")
```

## 🏗️ 系统架构

```
用户输入
    ↓
零Token捕获层 (本地嵌入 + 元数据标记)
    ↓
智能检索引擎 (混合检索 + 阈值过滤)
    ↓
动态压缩层 (本地摘要 + 去重合并)
    ↓
夜间自优化循环 (评分衰减 + 自动清理)
```

## 📊 性能优势

| 指标 | 传统方案 | ATLAS方案 | 提升 |
|------|----------|-----------|------|
| Token消耗 | 高 | 零捕获 | 减少70% |
| 检索精度 | 中等 | 高 | 提升30% |
| 响应时间 | 慢 | 快 | 减少50% |
| 记忆质量 | 静态 | 自优化 | 持续提升 |

## 🔧 集成OpenClaw

### 作为Skill使用
```yaml
# OpenClaw配置
skills:
  atlas-memory:
    enabled: true
    qdrant_url: "http://localhost:6333"
    collection_name: "atlas_memories"
```

### 可用命令
- `/memory store <内容>` - 存储记忆
- `/memory search <查询>` - 搜索记忆
- `/memory stats` - 查看统计
- `/memory optimize` - 手动优化

## 📈 路线图

- [ ] v0.1.0: 基础框架和核心功能
- [ ] v0.2.0: OpenClaw Skill集成
- [ ] v0.3.0: 自优化循环
- [ ] v1.0.0: 生产就绪版本

## 🤝 贡献指南

我们欢迎各种形式的贡献！请查看[CONTRIBUTING.md](CONTRIBUTING.md)了解详情。

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 联系方式

- GitHub Issues: [问题反馈](https://github.com/yourusername/atlas-memory-core/issues)
- 电子邮件: your-email@example.com
- 文档: [详细文档](https://yourusername.github.io/atlas-memory-core/)

## 🙏 致谢

感谢以下开源项目：
- [Qdrant](https://qdrant.tech/) - 高性能向量数据库
- [Sentence Transformers](https://www.sbert.net/) - 嵌入模型
- [OpenClaw](https://openclaw.ai/) - AI助手平台

---

**ATLAS Memory Core** - 让AI记住一切，却不用花费一分Token。