#!/bin/bash

# ATLAS Memory Core 安装脚本
# 一键安装和配置完整的记忆系统

set -e

echo "🏔️ ATLAS Memory Core 安装程序"
echo "================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 未安装"
        return 1
    fi
    return 0
}

# 检查 Python 版本
check_python_version() {
    log_info "检查 Python 版本..."
    if ! check_command python3; then
        log_error "Python3 未安装"
        return 1
    fi
    
    python_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    required_version="3.12"
    
    if [[ $(echo "$python_version >= $required_version" | bc -l) -eq 1 ]]; then
        log_success "Python 版本满足要求: $python_version"
        return 0
    else
        log_error "Python 版本过低: $python_version (需要 $required_version+)"
        return 1
    fi
}

# 检查 Docker
check_docker() {
    log_info "检查 Docker..."
    if check_command docker; then
        if docker info &> /dev/null; then
            log_success "Docker 已安装并运行"
            return 0
        else
            log_warning "Docker 已安装但未运行"
            return 1
        fi
    else
        log_warning "Docker 未安装"
        return 1
    fi
}

# 安装 Python 依赖
install_python_deps() {
    log_info "安装 Python 依赖..."
    
    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv venv
    fi
    
    # 激活虚拟环境
    log_info "激活虚拟环境..."
    source venv/bin/activate
    
    # 升级 pip
    log_info "升级 pip..."
    pip install --upgrade pip
    
    # 安装包
    log_info "安装 ATLAS Memory Core..."
    pip install -e .
    
    # 安装开发依赖（可选）
    read -p "是否安装开发依赖？(y/N): " install_dev
    if [[ $install_dev =~ ^[Yy]$ ]]; then
        log_info "安装开发依赖..."
        pip install -e .[dev]
    fi
    
    log_success "Python 依赖安装完成"
}

# 设置 Qdrant
setup_qdrant() {
    log_info "设置 Qdrant 向量数据库..."
    
    if check_docker; then
        log_info "使用 Docker 启动 Qdrant..."
        
        # 停止已存在的容器
        docker stop atlas-qdrant 2>/dev/null || true
        docker rm atlas-qdrant 2>/dev/null || true
        
        # 启动新容器
        docker run -d \
            --name atlas-qdrant \
            -p 6333:6333 \
            -p 6334:6334 \
            -v qdrant_storage:/qdrant/storage \
            qdrant/qdrant
        
        # 等待服务启动
        log_info "等待 Qdrant 启动..."
        sleep 5
        
        # 测试连接
        if curl -s http://localhost:6333/collections > /dev/null; then
            log_success "Qdrant 启动成功"
        else
            log_error "Qdrant 启动失败"
            return 1
        fi
    else
        log_warning "Docker 不可用，跳过 Qdrant 设置"
        log_info "请手动安装 Qdrant: https://qdrant.tech/documentation/quick-start/"
        return 1
    fi
}

# 创建配置文件
create_config() {
    log_info "创建配置文件..."
    
    config_dir="$HOME/.atlas-memory"
    config_file="$config_dir/config.yaml"
    
    mkdir -p "$config_dir"
    
    # 生成默认配置
    cat > "$config_file" << EOF
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
  persist_dir: "$config_dir"

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
EOF
    
    log_success "配置文件已创建: $config_file"
}

# 测试安装
test_installation() {
    log_info "测试安装..."
    
    source venv/bin/activate
    
    if python -m atlas_memory test --config "$HOME/.atlas-memory/config.yaml"; then
        log_success "安装测试通过"
        return 0
    else
        log_error "安装测试失败"
        return 1
    fi
}

# 创建示例数据
create_sample_data() {
    log_info "创建示例数据..."
    
    read -p "是否创建示例数据？(Y/n): " create_sample
    if [[ ! $create_sample =~ ^[Nn]$ ]]; then
        source venv/bin/activate
        python -m atlas_memory create-sample --config "$HOME/.atlas-memory/config.yaml"
    fi
}

# 显示完成信息
show_completion() {
    echo ""
    echo "🎉 ATLAS Memory Core 安装完成！"
    echo "================================"
    echo ""
    echo "📁 配置文件: $HOME/.atlas-memory/config.yaml"
    echo "🐳 Qdrant 服务: http://localhost:6333"
    echo "📊 管理界面: http://localhost:6333/dashboard"
    echo ""
    echo "🚀 快速开始:"
    echo "  1. 激活虚拟环境: source venv/bin/activate"
    echo "  2. 进入交互模式: python -m atlas_memory interactive"
    echo "  3. 测试搜索: python -m atlas_memory test"
    echo ""
    echo "🔧 常用命令:"
    echo "  - 启动开发环境: ./scripts/start_dev.sh"
    echo "  - 运行测试: pytest tests/"
    echo "  - 查看日志: tail -f ~/.atlas-memory/atlas_memory.log"
    echo ""
    echo "📚 文档:"
    echo "  - 用户指南: docs/guide/"
    echo "  - API 文档: docs/api/"
    echo "  - GitHub: https://github.com/yourusername/atlas-memory-core"
    echo ""
    echo "💬 需要帮助？"
    echo "  - GitHub Issues: https://github.com/yourusername/atlas-memory-core/issues"
    echo "  - Discord: https://discord.com/invite/clawd"
}

# 主安装流程
main() {
    echo "开始安装 ATLAS Memory Core..."
    echo ""
    
    # 检查 Python
    if ! check_python_version; then
        log_error "请先安装 Python 3.12+"
        exit 1
    fi
    
    # 安装 Python 依赖
    install_python_deps
    
    # 设置 Qdrant
    setup_qdrant
    
    # 创建配置文件
    create_config
    
    # 测试安装
    if ! test_installation; then
        log_warning "安装测试失败，但继续安装流程..."
    fi
    
    # 创建示例数据
    create_sample_data
    
    # 显示完成信息
    show_completion
}

# 执行主函数
main "$@"