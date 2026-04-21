#!/bin/bash

# ATLAS Memory Core - Qdrant 设置脚本
# 用于快速设置 Qdrant 向量数据库

set -e

echo "🚀 ATLAS Memory Core - Qdrant 设置脚本"
echo "========================================"

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    echo "请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查 Docker 是否运行
if ! docker info &> /dev/null; then
    echo "❌ Docker 守护进程未运行"
    echo "请启动 Docker 服务"
    exit 1
fi

echo "✅ Docker 已安装并运行"

# 创建数据目录
DATA_DIR="${HOME}/.atlas-memory/qdrant-data"
mkdir -p "$DATA_DIR"
echo "📁 数据目录: $DATA_DIR"

# 停止已存在的容器（如果存在）
echo "🛑 停止已存在的 Qdrant 容器..."
docker stop atlas-qdrant 2>/dev/null || true
docker rm atlas-qdrant 2>/dev/null || true

# 启动 Qdrant 容器
echo "🚀 启动 Qdrant 容器..."
docker run -d \
  --name atlas-qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v "${DATA_DIR}:/qdrant/storage" \
  qdrant/qdrant

echo "⏳ 等待 Qdrant 启动..."
sleep 5

# 检查服务状态
if curl -s http://localhost:6333/collections > /dev/null; then
    echo "✅ Qdrant 启动成功！"
    echo ""
    echo "📊 服务信息："
    echo "  - 地址: http://localhost:6333"
    echo "  - 管理界面: http://localhost:6333/dashboard"
    echo "  - 数据目录: $DATA_DIR"
    echo ""
    echo "🔧 测试连接："
    echo "  curl http://localhost:6333/collections"
else
    echo "❌ Qdrant 启动失败"
    echo "查看日志：docker logs atlas-qdrant"
    exit 1
fi

# 创建测试集合
echo ""
echo "🧪 创建测试集合..."
curl -X PUT http://localhost:6333/collections/test \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 768,
      "distance": "Cosine"
    }
  }'

echo ""
echo "✅ Qdrant 设置完成！"
echo ""
echo "📝 下一步："
echo "  1. 安装 Python 依赖: pip install -e ."
echo "  2. 运行测试: pytest tests/"
echo "  3. 启动开发: python -m atlas_memory"