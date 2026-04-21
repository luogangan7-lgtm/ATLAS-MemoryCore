#!/bin/bash
# Aegis-Cortex V6.2 生产环境部署脚本
# 版本: 1.0.0
# 使用: ./deploy_production.sh [环境]

set -e  # 遇到错误立即退出

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
        log_error "命令 '$1' 未安装"
        exit 1
    fi
}

# 显示横幅
show_banner() {
    echo -e "${BLUE}"
    echo "================================================"
    echo "   Aegis-Cortex V6.2 生产环境部署"
    echo "   版本: 6.2.0"
    echo "   时间: $(date)"
    echo "================================================"
    echo -e "${NC}"
}

# 检查系统要求
check_system_requirements() {
    log_info "检查系统要求..."
    
    # 检查Python
    check_command python3
    python_version=$(python3 --version | cut -d' ' -f2)
    log_info "Python版本: $python_version"
    
    # 检查Docker
    check_command docker
    docker_version=$(docker --version | cut -d' ' -f3 | sed 's/,//')
    log_info "Docker版本: $docker_version"
    
    # 检查Docker Compose
    check_command docker-compose
    docker_compose_version=$(docker-compose --version | cut -d' ' -f3 | sed 's/,//')
    log_info "Docker Compose版本: $docker_compose_version"
    
    # 检查内存
    total_memory=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$total_memory" -lt 8 ]; then
        log_warning "系统内存不足 (${total_memory}GB)，建议至少8GB"
    else
        log_info "系统内存: ${total_memory}GB"
    fi
    
    # 检查磁盘空间
    disk_space=$(df -h . | awk 'NR==2 {print $4}')
    log_info "可用磁盘空间: $disk_space"
    
    log_success "系统要求检查完成"
}

# 检查依赖
check_dependencies() {
    log_info "检查Python依赖..."
    
    # 检查pip
    check_command pip3
    
    # 检查核心依赖
    required_packages=("numpy" "sentence-transformers" "qdrant-client" "fastapi" "uvicorn" "prometheus-client")
    
    for package in "${required_packages[@]}"; do
        if python3 -c "import $package" 2>/dev/null; then
            log_info "  ✅ $package"
        else
            log_warning "  ⚠️  $package 未安装"
        fi
    done
    
    log_success "依赖检查完成"
}

# 准备环境
prepare_environment() {
    local env=${1:-"production"}
    
    log_info "准备 $env 环境..."
    
    # 创建目录结构
    mkdir -p /data/{qdrant/storage,metadata,embeddings/cache,backups}
    mkdir -p /var/log/atlas-memorycore
    
    # 设置权限
    chmod 755 /data /var/log/atlas-memorycore
    
    # 复制配置文件
    if [ -f "deploy/${env}_config.yaml" ]; then
        cp "deploy/${env}_config.yaml" config/production.yaml
        log_info "配置文件已复制: config/production.yaml"
    else
        log_warning "环境配置文件未找到: deploy/${env}_config.yaml"
    fi
    
    # 创建环境文件
    cat > .env << EOF
# Aegis-Cortex V6.2 环境变量
# 环境: $env
# 生成时间: $(date)

# 系统配置
ENVIRONMENT=$env
LOG_LEVEL=INFO
DEBUG=false

# Qdrant配置
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=atlas_memories_v6_2

# 嵌入模型配置
EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
NOMIC_API_KEY=

# API配置
API_HOST=0.0.0.0
API_PORT=8000
JWT_SECRET=$(openssl rand -hex 32)

# 监控配置
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000

# 备份配置
BACKUP_ENABLED=true
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
EOF
    
    log_success "环境准备完成"
}

# 启动Qdrant服务
start_qdrant() {
    log_info "启动Qdrant向量数据库..."
    
    # 检查Qdrant是否已在运行
    if docker ps | grep -q qdrant; then
        log_info "Qdrant已在运行"
        return 0
    fi
    
    # 启动Qdrant容器
    docker run -d \
        --name qdrant \
        -p 6333:6333 \
        -p 6334:6334 \
        -v /data/qdrant/storage:/qdrant/storage \
        qdrant/qdrant
    
    # 等待Qdrant启动
    log_info "等待Qdrant启动..."
    sleep 10
    
    # 检查Qdrant状态
    if curl -s http://localhost:6333/collections > /dev/null; then
        log_success "Qdrant启动成功"
    else
        log_error "Qdrant启动失败"
        return 1
    fi
}

# 初始化数据库
initialize_database() {
    log_info "初始化数据库..."
    
    # 运行数据库初始化脚本
    if [ -f "scripts/init_database.py" ]; then
        python3 scripts/init_database.py
        log_success "数据库初始化完成"
    else
        log_warning "数据库初始化脚本未找到"
    fi
}

# 构建Docker镜像
build_docker_images() {
    log_info "构建Docker镜像..."
    
    # 构建主应用镜像
    docker build -t atlas-memorycore:6.2.0 -f Dockerfile .
    
    # 构建监控镜像
    if [ -f "monitoring/Dockerfile" ]; then
        docker build -t atlas-monitoring:1.0.0 -f monitoring/Dockerfile monitoring/
    fi
    
    log_success "Docker镜像构建完成"
}

# 启动Docker Compose服务
start_docker_compose() {
    log_info "启动Docker Compose服务..."
    
    # 检查docker-compose.yml是否存在
    if [ ! -f "docker-compose.yml" ]; then
        log_error "docker-compose.yml 未找到"
        return 1
    fi
    
    # 启动服务
    docker-compose up -d
    
    # 等待服务启动
    log_info "等待服务启动..."
    sleep 15
    
    # 检查服务状态
    if docker-compose ps | grep -q "Up"; then
        log_success "Docker Compose服务启动成功"
    else
        log_error "Docker Compose服务启动失败"
        docker-compose logs
        return 1
    fi
}

# 运行健康检查
run_health_checks() {
    log_info "运行健康检查..."
    
    local max_retries=10
    local retry_count=0
    
    # 检查API服务
    while [ $retry_count -lt $max_retries ]; do
        if curl -s http://localhost:8000/health > /dev/null; then
            log_success "API服务健康"
            break
        fi
        
        retry_count=$((retry_count + 1))
        log_info "等待API服务... ($retry_count/$max_retries)"
        sleep 5
    done
    
    if [ $retry_count -eq $max_retries ]; then
        log_error "API服务健康检查失败"
        return 1
    fi
    
    # 检查Qdrant服务
    if curl -s http://localhost:6333/collections > /dev/null; then
        log_success "Qdrant服务健康"
    else
        log_error "Qdrant服务健康检查失败"
        return 1
    fi
    
    # 检查监控服务
    if curl -s http://localhost:9090/metrics > /dev/null; then
        log_success "Prometheus服务健康"
    else
        log_warning "Prometheus服务健康检查失败"
    fi
    
    log_success "所有健康检查通过"
}

# 运行初始测试
run_initial_tests() {
    log_info "运行初始测试..."
    
    # 运行集成测试
    if [ -f "tests/test_aegis_integration.py" ]; then
        python3 tests/test_aegis_integration.py
        if [ $? -eq 0 ]; then
            log_success "集成测试通过"
        else
            log_error "集成测试失败"
            return 1
        fi
    fi
    
    # 运行性能测试
    if [ -f "benchmark/run_benchmark.py" ]; then
        python3 benchmark/run_benchmark.py
        if [ $? -eq 0 ]; then
            log_success "性能测试通过"
        else
            log_warning "性能测试失败（非关键）"
        fi
    fi
    
    log_success "初始测试完成"
}

# 显示部署信息
show_deployment_info() {
    echo -e "${GREEN}"
    echo "================================================"
    echo "           部署完成！"
    echo "================================================"
    echo -e "${NC}"
    
    echo "服务访问地址:"
    echo "  🔗 API文档:      http://localhost:8000/docs"
    echo "  📊 监控面板:     http://localhost:3000"
    echo "  📈 Prometheus:   http://localhost:9090"
    echo "  🗄️  Qdrant管理:   http://localhost:6333/dashboard"
    
    echo ""
    echo "默认凭据:"
    echo "  Grafana: admin / admin (首次登录后请修改)"
    
    echo ""
    echo "管理命令:"
    echo "  📋 查看日志:     docker-compose logs -f"
    echo "  ⚡ 重启服务:     docker-compose restart"
    echo "  🛑 停止服务:     docker-compose down"
    echo "  🔄 更新部署:     ./deploy_production.sh"
    
    echo ""
    echo "下一步:"
    echo "  1. 访问 http://localhost:3000 配置监控告警"
    echo "  2. 设置环境变量 (NOMIC_API_KEY, JWT_SECRET等)"
    echo "  3. 配置备份策略"
    echo "  4. 设置防火墙规则"
    
    echo -e "${GREEN}"
    echo "================================================"
    echo "   Aegis-Cortex V6.2 已成功部署！"
    echo "================================================"
    echo -e "${NC}"
}

# 主部署函数
main() {
    local environment=${1:-"production"}
    
    show_banner
    
    # 检查当前目录
    if [ ! -f "README.md" ]; then
        log_error "请在项目根目录运行此脚本"
        exit 1
    fi
    
    # 执行部署步骤
    check_system_requirements
    check_dependencies
    prepare_environment "$environment"
    start_qdrant
    initialize_database
    build_docker_images
    start_docker_compose
    run_health_checks
    run_initial_tests
    
    show_deployment_info
}

# 处理命令行参数
case "${1:-}" in
    "help"|"-h"|"--help")
        echo "使用: $0 [环境]"
        echo "环境: production (默认), staging, development"
        exit 0
        ;;
    "production"|"staging"|"development")
        main "$1"
        ;;
    *)
        main "production"
        ;;
esac