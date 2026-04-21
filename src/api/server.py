#!/usr/bin/env python3
"""
Aegis-Cortex V6.2 API服务器
Aegis-Cortex V6.2 API Server
提供REST API接口和监控端点
Provides REST API interface and monitoring endpoints
"""

import os
import sys
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from core.aegis_orchestrator import get_global_orchestrator, AegisOrchestrator
from core.qdrant_storage import QdrantMemoryStorage
from core.scoring import MemoryScoringEngine as ScoringEngine
from core.embedding import EmbeddingModel

# 配置日志
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="Aegis-Cortex V6.2 API",
    description="ATLAS-MemoryCore智能记忆系统API",
    version="6.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局组件
orchestrator: Optional[AegisOrchestrator] = None
qdrant_storage: Optional[QdrantMemoryStorage] = None
scoring_engine: Optional[ScoringEngine] = None
embedding_model: Optional[EmbeddingModel] = None


@app.on_event("startup")
async def startup_event():
    """应用启动事件 - Application startup event"""
    global orchestrator, qdrant_storage, scoring_engine, embedding_model
    
    logger.info("启动Aegis-Cortex V6.2 API服务器...")
    logger.info("Starting Aegis-Cortex V6.2 API server...")
    
    try:
        # 初始化组件
        config_path = os.getenv("CONFIG_PATH")
        orchestrator = get_global_orchestrator(config_path)
        
        # 初始化存储和模型
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        
        qdrant_storage = QdrantMemoryStorage(
            host=qdrant_host,
            port=qdrant_port
        )
        
        scoring_engine = ScoringEngine()
        embedding_model = EmbeddingModel()
        
        logger.info("组件初始化完成")
        logger.info("Component initialization completed")
        
        # 获取系统状态
        status = orchestrator.get_system_status()
        logger.info(f"系统状态: {status['version']} - {status['architecture']}")
        logger.info(f"System status: {status['version']} - {status['architecture']}")
        
    except Exception as e:
        logger.error(f"启动失败: {e}")
        logger.error(f"Startup failed: {e}")
        raise


@app.get("/")
async def root():
    """根端点 - Root endpoint"""
    return {
        "service": "Aegis-Cortex V6.2 API",
        "version": "6.2.0",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """健康检查端点 - Health check endpoint"""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        status = orchestrator.get_system_status()
        return {
            "status": "healthy",
            "version": status["version"],
            "components": status["components"],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")


@app.get("/api/v1/status")
async def get_status():
    """获取系统状态 - Get system status"""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    status = orchestrator.get_system_status()
    return status


@app.post("/api/v1/query")
async def process_query(
    query: str = Body(..., description="查询文本"),
    context: Optional[Dict[str, Any]] = Body(None, description="上下文信息")
):
    """
    处理查询 - Process query
    
    Args:
        query: 查询文本
        context: 上下文信息
        
    Returns:
        处理结果
    """
    if orchestrator is None or qdrant_storage is None or scoring_engine is None or embedding_model is None:
        raise HTTPException(status_code=503, detail="Service components not ready")
    
    try:
        logger.info(f"处理查询: '{query[:50]}...'")
        logger.info(f"Processing query: '{query[:50]}...'")
        
        # 创建上下文
        aegis_context = orchestrator.create_context(
            query=query,
            qdrant_storage=qdrant_storage,
            scoring_engine=scoring_engine,
            embedding_model=embedding_model
        )
        
        # 处理查询
        result = orchestrator.process_query(aegis_context)
        
        # 构建响应
        response = {
            "query": query,
            "retrieved_memories": len(result.retrieved_memories),
            "compressed": result.compressed_context is not None,
            "processing_time": result.get_elapsed_time(),
            "token_usage": result.token_usage,
            "context": result.compressed_context or "",
            "timestamp": datetime.now().isoformat()
        }
        
        # 添加记忆摘要
        if result.retrieved_memories:
            memories_summary = []
            for i, memory in enumerate(result.retrieved_memories[:5]):  # 最多5条
                memories_summary.append({
                    "id": memory.id,
                    "content_preview": memory.content[:100] + "..." if len(memory.content) > 100 else memory.content,
                    "importance": memory.importance_score,
                    "category": memory.metadata.get("category", "unknown") if memory.metadata else "unknown"
                })
            response["memories_summary"] = memories_summary
        
        logger.info(f"查询处理完成: {len(result.retrieved_memories)}条记忆, {result.get_elapsed_time():.2f}秒")
        logger.info(f"Query processing completed: {len(result.retrieved_memories)} memories, {result.get_elapsed_time():.2f} seconds")
        
        return response
        
    except Exception as e:
        logger.error(f"查询处理失败: {e}")
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {e}")


@app.get("/api/v1/token-economy/report")
async def get_token_report(
    report_type: str = Query("daily", description="报告类型: daily, weekly"),
    date: Optional[str] = Query(None, description="日期 (YYYY-MM-DD格式)")
):
    """
    获取Token经济报告 - Get token economy report
    
    Args:
        report_type: 报告类型
        date: 日期
        
    Returns:
        Token经济报告
    """
    if orchestrator is None or orchestrator.token_monitor is None:
        raise HTTPException(status_code=503, detail="Token economy monitor not available")
    
    try:
        monitor = orchestrator.token_monitor
        
        if report_type == "daily":
            report = monitor.get_daily_report(date)
        elif report_type == "weekly":
            report = monitor.get_weekly_report()
        else:
            raise HTTPException(status_code=400, detail="Invalid report type")
        
        return report
        
    except Exception as e:
        logger.error(f"获取Token报告失败: {e}")
        logger.error(f"Failed to get token report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get token report: {e}")


@app.post("/api/v1/optimize")
async def trigger_optimization(
    batch_size: Optional[int] = Body(1000, description="批处理大小")
):
    """
    触发记忆优化 - Trigger memory optimization
    
    Args:
        batch_size: 批处理大小
        
    Returns:
        优化结果
    """
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        logger.info("触发记忆优化...")
        logger.info("Triggering memory optimization...")
        
        result = orchestrator.optimize_memory_storage(batch_size)
        
        logger.info("记忆优化完成")
        logger.info("Memory optimization completed")
        
        return result
        
    except Exception as e:
        logger.error(f"记忆优化失败: {e}")
        logger.error(f"Memory optimization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Memory optimization failed: {e}")


@app.get("/api/v1/metrics")
async def get_metrics():
    """获取监控指标 - Get monitoring metrics"""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        status = orchestrator.get_system_status()
        
        # 基础指标
        metrics = {
            "version": status["version"],
            "uptime": datetime.now().isoformat(),  # 实际应该计算启动时间
            "components": {
                name: info["status"]
                for name, info in status["components"].items()
            },
            "config": status["config_summary"]
        }
        
        # Token经济指标
        if orchestrator.token_monitor:
            token_metrics = {
                "total_cost": orchestrator.token_monitor.total_cost,
                "total_tokens": orchestrator.token_monitor.total_tokens,
                "downgrade_level": orchestrator.token_monitor.downgrade_level.value
            }
            metrics["token_economy"] = token_metrics
        
        return metrics
        
    except Exception as e:
        logger.error(f"获取指标失败: {e}")
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {e}")


@app.get("/api/v1/config")
async def get_configuration():
    """获取当前配置 - Get current configuration"""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        status = orchestrator.get_system_status()
        return status["config_summary"]
        
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        logger.error(f"Failed to get configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get configuration: {e}")


# 错误处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理 - Global exception handler"""
    logger.error(f"未处理的异常: {exc}")
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


if __name__ == "__main__":
    # 启动服务器
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"启动服务器在 {host}:{port}")
    logger.info(f"Starting server at {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )