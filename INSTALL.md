# ATLAS Memory Core 安装指南

## 🚀 快速安装

### 系统要求
- Python 3.12 或更高版本
- 4GB 以上内存
- 5GB 以上磁盘空间
- Docker (用于Qdrant，可选但推荐)

### 一键安装脚本 (Linux/macOS)
```bash
# 下载安装脚本
curl -fsSL https://raw.githubusercontent.com/yourusername/atlas-memory-core/main/scripts/quick_install.sh | bash

# 或手动执行
git clone https://github.com/yourusername/atlas-memory-core.git
cd atlas-memory-core
./scripts/install.sh
```

### Windows 安装
```powershell
# 1. 安装 Python 3.12+
# 从 https://www.python.org/downloads/ 下载安装

# 2. 安装 Git
# 从 https://git-scm.com/download/win 下载安装

# 3. 克隆仓库
git clone https://github.com/yourusername/atlas-memory-core.git
cd atlas-memory-core

# 4. 运行安装脚本
python scripts/install_windows.py
```

## 📦 手动安装步骤

### 1. 安装 Python 依赖
```bash
# 创建虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows

# 安装包
pip install -e .

# 安装开发依赖 (可选)
pip install -e .[dev]
```

### 2. 启动 Qdrant 向量数据库
```bash
# 使用 Docker (推荐)
docker run -d \
  --name atlas-qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# 或使用提供的脚本
./scripts/setup_qdrant.sh
```

### 3. 验证安装
```bash
# 测试系统连接
python -m atlas_memory test

# 或进入交互模式
python -m atlas_memory interactive
```

## 🔧 配置说明

### 默认配置文件位置
- Linux/macOS: `~/.atlas-memory/config.yaml`
- Windows: `%USERPROFILE%\.atlas-memory\config.yaml`

### 生成默认配置
```bash
python -c "from atlas_memory.core.config import ConfigManager; cm = ConfigManager(); cm.create_default_config_file()"
```

### 配置文件示例 (`config.yaml`)
```yaml
version: "0.1.0"

embedding:
  provider: "nomic"
  model_name: "nomic-ai/nomic-embed-text-v1.5"
  device: "cpu"
  normalize: true
  batch_size: 32

local_model:
  enabled: false
  model_type: "qwen2.5-7b"
  device: "cpu"
  quantized: true
  max_tokens: 2048

storage:
  qdrant_url: "http://localhost:6333"
  collection_name: "atlas_memories"
  vector_size: 768
  max_memories: 10000
  persist_dir: "~/.atlas-memory"

retrieval:
  similarity_threshold: 0.82
  max_results: 10
  use_metadata_filter: true
  use_hybrid_search: true
  cache_enabled: true
  cache_size: 1000

optimization:
  auto_optimize: true
  optimization_time: "03:00"
  importance_decay_days: 30
  min_score_to_keep: 0.3
  max_score_to_promote: 0.85

system:
  log_level: "INFO"
  debug_mode: false
  max_workers: 4
```

## 🐳 Docker 部署

### 使用 Docker Compose (推荐)
```bash
# 1. 下载 docker-compose.yml
curl -O https://raw.githubusercontent.com/yourusername/atlas-memory-core/main/docker-compose.yml

# 2. 启动服务
docker-compose up -d

# 3. 查看日志
docker-compose logs -f
```

### Docker Compose 配置示例
```yaml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

  atlas-memory:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - qdrant
    environment:
      - QDRANT_URL=http://qdrant:6333
      - LOG_LEVEL=INFO
    volumes:
      - atlas_data:/app/data
    restart: unless-stopped

volumes:
  qdrant_data:
  atlas_data:
```

## 🔌 集成 OpenClaw

### 作为 Skill 安装
```bash
# 1. 确保 OpenClaw 已安装
openclaw --version

# 2. 安装 ATLAS Memory Skill
openclaw skills install atlas-memory

# 3. 配置 Skill
openclaw config set skills.atlas-memory.enabled true
openclaw config set skills.atlas-memory.qdrant_url "http://localhost:6333"

# 4. 重启 OpenClaw
openclaw restart
```

### Skill 配置示例
```yaml
# ~/.openclaw/config.yaml
skills:
  atlas-memory:
    enabled: true
    qdrant_url: "http://localhost:6333"
    collection_name: "atlas_memories"
    embedding_model: "nomic-ai/nomic-embed-text-v1.5"
    auto_optimize: true
```

## 🧪 测试安装

### 运行单元测试
```bash
pytest tests/ -v
```

### 运行集成测试
```bash
# 需要先启动 Qdrant
./scripts/setup_qdrant.sh
pytest tests/integration/ -v
```

### 性能测试
```bash
python examples/benchmark.py
```

## 🚨 故障排除

### 常见问题

#### 1. Qdrant 连接失败
```
错误: 无法连接到 Qdrant 服务
解决: docker ps | grep qdrant  # 检查是否运行
       docker start atlas-qdrant  # 启动服务
```

#### 2. 嵌入模型下载慢
```
错误: 下载模型超时
解决: 使用国内镜像或手动下载
      export HF_ENDPOINT=https://hf-mirror.com
```

#### 3. 内存不足
```
错误: MemoryError 或 CUDA out of memory
解决: 1. 减少 batch_size
      2. 使用 CPU 模式
      3. 增加系统内存
```

#### 4. Python 版本问题
```
错误: Python 版本不兼容
解决: 确保使用 Python 3.12+
      python --version
```

### 获取帮助
```bash
# 查看日志
tail -f ~/.atlas-memory/atlas_memory.log

# 调试模式
python -m atlas_memory --log-level DEBUG

# 查看帮助
python -m atlas_memory --help
```

## 📈 性能优化

### 硬件建议
- **CPU**: 4核以上 (推荐 8核)
- **内存**: 8GB+ (推荐 16GB)
- **存储**: SSD (提升检索速度)
- **GPU**: 可选 (加速嵌入计算)

### 配置优化
```yaml
# 高性能配置
embedding:
  device: "cuda"  # 如果有 GPU
  batch_size: 64

retrieval:
  cache_size: 5000  # 增大缓存
  cache_ttl_seconds: 7200  # 延长缓存时间

system:
  max_workers: 8  # 增加工作线程
```

## 🔄 更新升级

### 从旧版本升级
```bash
# 1. 备份数据
cp -r ~/.atlas-memory ~/.atlas-memory.backup

# 2. 更新代码
git pull origin main

# 3. 更新依赖
pip install -e . --upgrade

# 4. 迁移数据 (如果需要)
python scripts/migrate.py
```

### 检查更新
```bash
# 查看当前版本
python -c "import atlas_memory; print(atlas_memory.__version__)"

# 检查最新版本
curl -s https://api.github.com/repos/yourusername/atlas-memory-core/releases/latest | grep tag_name
```

## 🎯 下一步

安装完成后，建议：
1. 运行 `python -m atlas_memory create-sample` 创建示例数据
2. 阅读 [快速开始指南](docs/getting-started/quickstart.md)
3. 查看 [API 文档](docs/api/overview.md)
4. 加入 [社区讨论](https://discord.com/invite/clawd)

---

**需要帮助?** 
- GitHub Issues: https://github.com/yourusername/atlas-memory-core/issues
- 文档: https://yourusername.github.io/atlas-memory-core/
- 社区: https://discord.com/invite/clawd