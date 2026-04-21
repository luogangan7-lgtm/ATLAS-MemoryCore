# ATLAS-MemoryCore V6.2 Docker镜像
# ATLAS-MemoryCore V6.2 Docker Image
# 基于Python 3.12的轻量级镜像
# Lightweight image based on Python 3.12

FROM python:3.12-slim

# 设置工作目录
# Set working directory
WORKDIR /app

# 设置环境变量
# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# 安装系统依赖
# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
# Copy dependency files
COPY requirements.txt .

# 安装Python依赖
# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
# Copy project files
COPY . .

# 创建必要的目录
# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/config

# 健康检查
# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.path.append('/app/src'); from core.aegis_orchestrator import get_global_orchestrator; orchestrator = get_global_orchestrator(); print('Health check passed')" || exit 1

# 暴露端口
# Expose ports
EXPOSE 8000  # API端口 / API port
EXPOSE 9091  # 监控指标端口 / Metrics port

# 设置默认命令
# Set default command
CMD ["python", "src/api/server.py"]