#!/bin/bash
# ATLAS-MemoryCore Docker入口脚本

set -e

echo "🚀 Starting ATLAS-MemoryCore V6.0..."

# 检查必要的目录
mkdir -p data/qdrant_storage data/logs data/backups data/models

# 设置环境变量
export QDRANT_STORAGE_PATH=${QDRANT_STORAGE_PATH:-/app/data/qdrant_storage}
export LOG_LEVEL=${LOG_LEVEL:-INFO}

# 启动Qdrant向量数据库（如果使用本地模式）
if [ "${QDRANT_MODE}" = "local" ] || [ -z "${QDRANT_URL}" ]; then
    echo "📦 Starting Qdrant in local mode..."
    
    # 检查Qdrant是否已安装
    if ! command -v qdrant &> /dev/null; then
        echo "⚠️ Qdrant not found, downloading..."
        curl -L https://github.com/qdrant/qdrant/releases/download/v1.7.4/qdrant-x86_64-unknown-linux-gnu.tar.gz | tar -xz
        chmod +x qdrant
        mv qdrant /usr/local/bin/
    fi
    
    # 启动Qdrant
    qdrant --storage-path "${QDRANT_STORAGE_PATH}" &
    QDRANT_PID=$!
    
    # 等待Qdrant启动
    echo "⏳ Waiting for Qdrant to start..."
    sleep 5
    
    # 检查Qdrant是否运行
    if ! curl -s http://localhost:6333/readyz > /dev/null; then
        echo "❌ Qdrant failed to start"
        exit 1
    fi
    
    echo "✅ Qdrant started successfully (PID: $QDRANT_PID)"
    
    # 设置Qdrant环境变量
    export QDRANT_HOST=localhost
    export QDRANT_PORT=6333
else
    echo "🔗 Using external Qdrant: ${QDRANT_URL}"
    export QDRANT_HOST=$(echo $QDRANT_URL | cut -d':' -f1)
    export QDRANT_PORT=$(echo $QDRANT_URL | cut -d':' -f2)
fi

# 初始化ATLAS存储
echo "🔄 Initializing ATLAS storage..."
python -c "
import sys
sys.path.append('/app')
from src.core.qdrant_storage import QdrantStorage
storage = QdrantStorage()
print('✅ Storage initialized:', 'ready' if storage.client else 'failed')
"

# 运行数据库迁移（如果有）
if [ -f "scripts/migrate.py" ]; then
    echo "🔄 Running database migrations..."
    python scripts/migrate.py
fi

# 根据命令执行不同的操作
if [ "$1" = "serve" ]; then
    # 启动HTTP服务
    echo "🌐 Starting HTTP server..."
    exec python -m src serve --host 0.0.0.0 --port ${PORT:-8000}
    
elif [ "$1" = "cli" ]; then
    # 进入CLI模式
    echo "💻 Starting CLI mode..."
    exec python -m src "${@:2}"
    
elif [ "$1" = "test" ]; then
    # 运行测试
    echo "🧪 Running tests..."
    exec python -m pytest tests/ -v
    
elif [ "$1" = "optimize" ]; then
    # 运行优化循环
    echo "⚡ Running optimization cycle..."
    exec python -m src optimize --full
    
elif [ "$1" = "shell" ]; then
    # 进入Python shell
    echo "🐍 Starting Python shell..."
    exec python
    
else
    # 默认：显示帮助信息
    echo "📖 ATLAS-MemoryCore V6.0"
    echo ""
    echo "Available commands:"
    echo "  serve     - Start HTTP server"
    echo "  cli       - Start CLI interface"
    echo "  test      - Run tests"
    echo "  optimize  - Run optimization cycle"
    echo "  shell     - Start Python shell"
    echo ""
    echo "Environment variables:"
    echo "  QDRANT_URL      - External Qdrant URL (e.g., localhost:6333)"
    echo "  QDRANT_MODE     - 'local' to start embedded Qdrant"
    echo "  LOG_LEVEL       - Logging level (DEBUG, INFO, WARNING, ERROR)"
    echo "  PORT            - HTTP server port (default: 8000)"
    echo ""
    
    # 保持容器运行
    echo "🔄 Container is running in idle mode..."
    echo "Use 'docker exec -it <container> /app/docker-entrypoint.sh cli' to access CLI"
    
    # 等待信号
    trap 'echo "👋 Shutting down..."; kill $QDRANT_PID 2>/dev/null; exit 0' SIGTERM SIGINT
    wait $QDRANT_PID 2>/dev/null || true
fi