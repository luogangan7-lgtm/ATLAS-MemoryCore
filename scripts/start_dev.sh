#!/bin/bash

# ATLAS Memory Core - 开发环境启动脚本

set -e

echo "🏔️ ATLAS Memory Core 开发环境"
echo "================================"

# 激活虚拟环境
if [ -d "venv" ]; then
    echo "🔧 激活虚拟环境..."
    source venv/bin/activate
else
    echo "📦 创建虚拟环境..."
    python -m venv venv
    source venv/bin/activate
    
    echo "📥 安装依赖..."
    pip install -e .[dev]
fi

# 检查 Qdrant
echo "🔍 检查 Qdrant 服务..."
if ! curl -s http://localhost:6333/collections > /dev/null; then
    echo "⚠️  Qdrant 未运行，正在启动..."
    
    # 尝试使用 Docker 启动
    if command -v docker &> /dev/null && docker info &> /dev/null; then
        ./scripts/setup_qdrant.sh
    else
        echo "❌ 无法启动 Qdrant，请手动启动："
        echo "   docker run -p 6333:6333 qdrant/qdrant"
        echo "或安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
else
    echo "✅ Qdrant 正在运行"
fi

# 运行测试
echo ""
echo "🧪 运行测试..."
pytest tests/ -v

# 启动示例
echo ""
echo "🚀 启动示例程序..."
echo ""
echo "选择要运行的示例："
echo "  1. 基础示例 (basic_example.py)"
echo "  2. 高级示例 (advanced_example.py)"
echo "  3. 性能测试 (benchmark.py)"
echo "  4. 全部运行"
echo "  5. 退出"
echo ""

read -p "请输入选择 (1-5): " choice

case $choice in
    1)
        python examples/basic_example.py
        ;;
    2)
        python examples/advanced_example.py
        ;;
    3)
        python examples/benchmark.py
        ;;
    4)
        echo "运行全部示例..."
        for example in examples/*.py; do
            echo ""
            echo "运行: $(basename $example)"
            python "$example"
        done
        ;;
    5)
        echo "退出"
        exit 0
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo ""
echo "✅ 开发环境准备完成！"
echo ""
echo "📝 可用命令："
echo "  - pytest tests/           # 运行测试"
echo "  - python -m atlas_memory  # 启动主程序"
echo "  - ./scripts/setup_qdrant.sh  # 重新设置 Qdrant"
echo ""
echo "🏔️ ATLAS Memory Core 开发愉快！"