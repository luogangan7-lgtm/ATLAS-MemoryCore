#!/bin/bash
# ATLAS-MemoryCore V6.2 部署脚本
# ATLAS-MemoryCore V6.2 Deployment Script

set -e  # 遇到错误时退出

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
        log_error "命令 '$1' 未找到，请先安装"
        exit 1
    fi
}

# 显示横幅
show_banner() {
    echo -e "${BLUE}"
    echo "=========================================="
    echo "   ATLAS-MemoryCore V6.2 部署工具"
    echo "   ATLAS-MemoryCore V6.2 Deployment Tool"
    echo "=========================================="
    echo -e "${NC}"
}

# 检查依赖
check_dependencies() {
    log_info "检查系统依赖..."
    log_info "Checking system dependencies..."
    
    check_command docker
    check_command docker-compose
    check_command python3
    check_command curl
    
    log_success "所有依赖已安装"
    log_success "All dependencies installed"
}

# 检查Python依赖
check_python_deps() {
    log_info "检查Python依赖..."
    log_info "Checking Python dependencies..."
    
    if [ ! -f "requirements.txt" ]; then
        log_error "requirements.txt 文件未找到"
        exit 1
    fi
    
    # 检查是否已安装
    if python3 -c "import sentence_transformers, qdrant_client, numpy" &> /dev/null; then
        log_success "Python依赖已安装"
        log_success "Python dependencies installed"
    else
        log_warning "Python依赖未完全安装，正在安装..."
        log_warning "Python dependencies not fully installed, installing..."
        pip3 install -r requirements.txt
        log_success "Python依赖安装完成"
        log_success "Python dependencies installation completed"
    fi
}

# 启动Qdrant服务
start_qdrant() {
    log_info "启动Qdrant向量数据库..."
    log_info "Starting Qdrant vector database..."
    
    if docker ps | grep -q "atlas-qdrant"; then
        log_warning "Qdrant服务已在运行"
        log_warning "Qdrant service already running"
    else
        docker run -d \
            --name atlas-qdrant \
            -p 6333:6333 \
            -p 6334:6334 \
            -v qdrant_data:/qdrant/storage \
            qdrant/qdrant:latest
        
        # 等待服务启动
        sleep 5
        if curl -s http://localhost:6333/health | grep -q "ok"; then
            log_success "Qdrant服务启动成功"
            log_success "Qdrant service started successfully"
        else
            log_error "Qdrant服务启动失败"
            exit 1
        fi
    fi
}

# 构建Docker镜像
build_docker_image() {
    log_info "构建Aegis-Cortex Docker镜像..."
    log_info "Building Aegis-Cortex Docker image..."
    
    if [ -f "Dockerfile" ]; then
        docker build -t atlas-aegis-cortex:v6.2 .
        log_success "Docker镜像构建完成"
        log_success "Docker image built successfully"
    else
        log_error "Dockerfile 未找到"
        exit 1
    fi
}

# 使用Docker Compose部署
deploy_with_compose() {
    log_info "使用Docker Compose部署..."
    log_info "Deploying with Docker Compose..."
    
    if [ -f "docker-compose.yml" ]; then
        docker-compose up -d
        
        log_info "等待服务启动..."
        log_info "Waiting for services to start..."
        sleep 10
        
        # 检查服务状态
        if docker-compose ps | grep -q "Up"; then
            log_success "所有服务已启动"
            log_success "All services started"
            
            # 显示服务状态
            echo ""
            docker-compose ps
            echo ""
            
            log_info "服务访问信息:"
            log_info "Service access information:"
            echo "  Aegis-Cortex API: http://localhost:8000"
            echo "  API文档: http://localhost:8000/docs"
            echo "  Qdrant管理界面: http://localhost:6333/dashboard"
            echo "  Prometheus: http://localhost:9090"
            echo "  Grafana: http://localhost:3000 (admin/admin)"
        else
            log_error "服务启动失败"
            docker-compose logs
            exit 1
        fi
    else
        log_error "docker-compose.yml 未找到"
        exit 1
    fi
}

# 手动部署（不使用Docker Compose）
deploy_manually() {
    log_info "手动部署Aegis-Cortex..."
    log_info "Manual deployment of Aegis-Cortex..."
    
    # 创建必要的目录
    mkdir -p data logs config
    
    # 复制配置文件
    if [ -f "config/aegis_config.yaml" ]; then
        cp config/aegis_config.yaml config/
    else
        log_warning "配置文件未找到，使用默认配置"
        log_warning "Config file not found, using default configuration"
    fi
    
    # 创建环境文件
    if [ ! -f ".env" ]; then
        cat > .env << EOF
# Aegis-Cortex环境变量
QDRANT_HOST=localhost
QDRANT_PORT=6333
LOG_LEVEL=INFO
CONFIG_PATH=./config/aegis_config.yaml
PORT=8000
HOST=0.0.0.0
EOF
        log_success "环境文件创建完成"
        log_success "Environment file created"
    fi
    
    # 启动API服务器
    log_info "启动Aegis-Cortex API服务器..."
    log_info "Starting Aegis-Cortex API server..."
    
    python3 src/api/server.py &
    SERVER_PID=$!
    
    # 等待服务器启动
    sleep 5
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        log_success "API服务器启动成功 (PID: $SERVER_PID)"
        log_success "API server started successfully (PID: $SERVER_PID)"
        
        log_info "服务访问信息:"
        log_info "Service access information:"
        echo "  API端点: http://localhost:8000"
        echo "  API文档: http://localhost:8000/docs"
        echo "  健康检查: http://localhost:8000/health"
        
        # 保存PID到文件
        echo $SERVER_PID > .server.pid
        log_info "服务器PID已保存到 .server.pid"
        log_info "Server PID saved to .server.pid"
    else
        log_error "API服务器启动失败"
        exit 1
    fi
}

# 运行测试
run_tests() {
    log_info "运行集成测试..."
    log_info "Running integration tests..."
    
    if [ -f "test_basic.py" ]; then
        python3 test_basic.py
        if [ $? -eq 0 ]; then
            log_success "集成测试通过"
            log_success "Integration tests passed"
        else
            log_error "集成测试失败"
            exit 1
        fi
    else
        log_warning "测试文件未找到，跳过测试"
        log_warning "Test file not found, skipping tests"
    fi
}

# 显示使用帮助
show_usage() {
    echo "用法: $0 [选项]"
    echo "Usage: $0 [option]"
    echo ""
    echo "选项:"
    echo "Options:"
    echo "  check     检查依赖"
    echo "            Check dependencies"
    echo "  qdrant    启动Qdrant服务"
    echo "            Start Qdrant service"
    echo "  build     构建Docker镜像"
    echo "            Build Docker image"
    echo "  compose   使用Docker Compose部署"
    echo "            Deploy with Docker Compose"
    echo "  manual    手动部署"
    echo "            Manual deployment"
    echo "  test      运行测试"
    echo "            Run tests"
    echo "  all       完整部署流程"
    echo "            Complete deployment process"
    echo "  stop      停止所有服务"
    echo "            Stop all services"
    echo "  status    查看服务状态"
    echo "            Check service status"
    echo "  help      显示帮助信息"
    echo "            Show this help message"
    echo ""
}

# 停止服务
stop_services() {
    log_info "停止所有服务..."
    log_info "Stopping all services..."
    
    # 停止Docker Compose服务
    if [ -f "docker-compose.yml" ]; then
        docker-compose down
    fi
    
    # 停止手动启动的服务
    if [ -f ".server.pid" ]; then
        SERVER_PID=$(cat .server.pid)
        if kill -0 $SERVER_PID 2>/dev/null; then
            kill $SERVER_PID
            log_success "API服务器已停止 (PID: $SERVER_PID)"
            log_success "API server stopped (PID: $SERVER_PID)"
            rm .server.pid
        fi
    fi
    
    # 停止Qdrant
    if docker ps | grep -q "atlas-qdrant"; then
        docker stop atlas-qdrant
        docker rm atlas-qdrant
        log_success "Qdrant服务已停止"
        log_success "Qdrant service stopped"
    fi
    
    log_success "所有服务已停止"
    log_success "All services stopped"
}

# 查看服务状态
check_status() {
    log_info "服务状态检查..."
    log_info "Service status check..."
    
    echo ""
    echo "Docker容器状态:"
    echo "Docker container status:"
    docker ps --filter "name=atlas-*" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    echo ""
    echo "API服务状态:"
    echo "API service status:"
    if curl -s http://localhost:8000/health 2>/dev/null | grep -q "healthy"; then
        echo "  ✅ Aegis-Cortex API: 运行正常"
        echo "  ✅ Aegis-Cortex API: Running normally"
    else
        echo "  ❌ Aegis-Cortex API: 未运行"
        echo "  ❌ Aegis-Cortex API: Not running"
    fi
    
    if curl -s http://localhost:6333/health 2>/dev/null | grep -q "ok"; then
        echo "  ✅ Qdrant数据库: 运行正常"
        echo "  ✅ Qdrant database: Running normally"
    else
        echo "  ❌ Qdrant数据库: 未运行"
        echo "  ❌ Qdrant database: Not running"
    fi
    
    echo ""
}

# 主函数
main() {
    show_banner
    
    case "$1" in
        check)
            check_dependencies
            check_python_deps
            ;;
        qdrant)
            start_qdrant
            ;;
        build)
            build_docker_image
            ;;
        compose)
            check_dependencies
            start_qdrant
            build_docker_image
            deploy_with_compose
            ;;
        manual)
            check_dependencies
            check_python_deps
            start_qdrant
            run_tests
            deploy_manually
            ;;
        test)
            run_tests
            ;;
        all)
            check_dependencies
            check_python_deps
            start_qdrant
            run_tests
            build_docker_image
            deploy_with_compose
            ;;
        stop)
            stop_services
            ;;
        status)
            check_status
            ;;
        help|*)
            show_usage
            ;;
    esac
}

# 执行主函数
main "$@"