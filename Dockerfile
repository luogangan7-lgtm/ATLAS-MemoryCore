# ATLAS-MemoryCore V6.0 Docker容器化部署
# Phase 2: 生产环境部署

FROM python:3.11-slim as builder

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY . .

# 创建虚拟环境并安装依赖
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装Python依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 安装Qdrant客户端
RUN pip install qdrant-client

# 安装可选依赖（情感分析）
RUN pip install textblob

# 安装开发依赖（可选）
RUN pip install pytest pytest-cov black isort

# 第二阶段：运行环境
FROM python:3.11-slim

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从builder复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 创建非root用户
RUN useradd -m -u 1000 atlas && \
    chown -R atlas:atlas /app

# 设置工作目录
WORKDIR /app
USER atlas

# 复制项目文件
COPY --chown=atlas:atlas . .

# 创建必要的目录
RUN mkdir -p data/qdrant_storage data/logs data/backups

# 环境变量
ENV PYTHONPATH=/app
ENV QDRANT_HOST=localhost
ENV QDRANT_PORT=6333
ENV QDRANT_STORAGE_PATH=/app/data/qdrant_storage
ENV LOG_LEVEL=INFO
ENV MODEL_CACHE_DIR=/app/data/models

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.path.append('/app'); from src.core.qdrant_storage import QdrantStorage; storage = QdrantStorage(); print('Health check passed') if storage.client else exit(1)"

# 暴露端口
EXPOSE 6333 8000

# 默认命令：启动Qdrant和ATLAS服务
COPY --chown=atlas:atlas docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# 备用命令：直接运行Python模块
CMD ["python", "-m", "src", "serve", "--host", "0.0.0.0", "--port", "8000"]