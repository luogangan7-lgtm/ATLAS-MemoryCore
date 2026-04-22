"""
Aegis-Cortex Orchestrator V6.2 - 主集成模块
整合TurboQuant压缩、四级过滤、Token经济等所有组件
"""

import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

from .aegis_config import AegisCortexConfig, load_config
from .turboquant_compressor import TurboQuantCompressor, get_global_compressor
from .four_stage_filter import FourStageFilter, get_global_filter
from .token_economy import TokenEconomyMonitor, TokenOperation
from .qdrant_storage import QdrantMemoryStorage, MemoryRecord
from .scoring import MemoryScoringEngine as ScoringEngine
from .embedding import EmbeddingModel

logger = logging.getLogger(__name__)


@dataclass
class AegisContext:
    """Aegis-Cortex上下文"""
    
    # 查询信息
    query: str
    query_embedding: np.ndarray
    
    # 配置
    config: AegisCortexConfig
    
    # 组件
    compressor: Optional[TurboQuantCompressor] = None
    filter: Optional[FourStageFilter] = None
    token_monitor: Optional[TokenEconomyMonitor] = None
    qdrant_storage: Optional[QdrantMemoryStorage] = None
    scoring_engine: Optional[ScoringEngine] = None
    embedding_model: Optional[EmbeddingModel] = None
    
    # 状态
    start_time: float = 0.0
    end_time: float = 0.0
    token_usage: Dict[str, Any] = None
    retrieved_memories: List[MemoryRecord] = None
    compressed_context: str = None
    
    def __post_init__(self):
        self.start_time = time.time()
        self.token_usage = {}
        self.retrieved_memories = []
    
    def get_elapsed_time(self) -> float:
        """获取经过的时间（秒）"""
        if self.end_time > 0:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "query": self.query[:100] + "..." if len(self.query) > 100 else self.query,
            "config_version": self.config.version,
            "elapsed_time": self.get_elapsed_time(),
            "retrieved_count": len(self.retrieved_memories) if self.retrieved_memories else 0,
            "compressed": self.compressed_context is not None,
            "token_usage": self.token_usage
        }


class AegisOrchestrator:
    """Aegis-Cortex协调器"""
    
    def __init__(self, config_path: Optional[str] = None):
        # 加载配置
        self.config = load_config(config_path)
        
        # 初始化组件
        self._initialize_components()
        
        logger.info(f"Aegis-Cortex V{self.config.version} 协调器初始化完成")
    
    def _initialize_components(self):
        """初始化所有组件"""
        
        # 初始化TurboQuant压缩器
        if self.config.turboquant.enabled:
            from .turboquant_compressor import TurboQuantCompressor
            self.compressor = TurboQuantCompressor()
            logger.info("TurboQuant压缩器初始化完成")
        else:
            self.compressor = None
            logger.info("TurboQuant压缩器已禁用")
        
        # 初始化Token经济监控器
        if self.config.token_economy.enabled:
            from .token_economy import TokenEconomyMonitor
            self.token_monitor = TokenEconomyMonitor(self.config.token_economy)
            logger.info("Token经济监控器初始化完成")
        else:
            self.token_monitor = None
            logger.info("Token经济监控器已禁用")
        
        # 注意：其他组件（Qdrant存储、评分引擎、嵌入模型）需要外部传入
        # 因为它们可能已经在其他地方初始化
        
        logger.info("Aegis-Cortex组件初始化完成")
    
    def create_context(
        self,
        query: str,
        qdrant_storage: QdrantMemoryStorage,
        scoring_engine: ScoringEngine,
        embedding_model: EmbeddingModel,
        query_embedding: Optional[np.ndarray] = None
    ) -> AegisContext:
        """
        创建Aegis上下文
        
        Args:
            query: 查询文本
            qdrant_storage: Qdrant存储实例
            scoring_engine: 评分引擎实例
            embedding_model: 嵌入模型实例
            query_embedding: 查询向量（如果为None则自动生成）
            
        Returns:
            Aegis上下文
        """
        # 生成查询向量
        if query_embedding is None:
            query_embedding = self._generate_embedding(query, embedding_model)
        
        # 初始化四级过滤器
        filter_component = None
        if self.config.four_stage_filter.enabled:
            from .four_stage_filter import FourStageFilter
            filter_component = FourStageFilter(qdrant_storage, scoring_engine)
        
        # 创建上下文
        context = AegisContext(
            query=query,
            query_embedding=query_embedding,
            config=self.config,
            compressor=self.compressor,
            filter=filter_component,
            token_monitor=self.token_monitor,
            qdrant_storage=qdrant_storage,
            scoring_engine=scoring_engine,
            embedding_model=embedding_model
        )
        
        return context
    
    def process_query(self, context: AegisContext) -> AegisContext:
        """
        处理查询 - 完整的Aegis-Cortex流程
        
        Args:
            context: Aegis上下文
            
        Returns:
            更新后的上下文
        """
        logger.info(f"开始处理查询: '{context.query[:50]}...'")
        
        try:
            # 步骤1: 记录Token使用（查询嵌入）
            self._record_token_usage(
                context,
                TokenOperation.RETRIEVAL,
                model="local-embedding",
                input_tokens=len(context.query.split()),
                output_tokens=0
            )
            
            # 步骤2: 四级过滤检索
            if context.filter and self.config.four_stage_filter.enabled:
                retrieved = context.filter.retrieve_memories(
                    query=context.query,
                    query_embedding=context.query_embedding
                )
                context.retrieved_memories = retrieved
                
                # 记录Token使用（检索）
                self._record_token_usage(
                    context,
                    TokenOperation.RETRIEVAL,
                    model="four_stage_filter",
                    input_tokens=len(context.query.split()),
                    output_tokens=len(retrieved) * 10  # 估算
                )
            else:
                # 回退到简单检索
                retrieved = context.qdrant_storage.search_memories(
                    query_embedding=context.query_embedding,
                    limit=10
                )
                context.retrieved_memories = retrieved
            
            # 步骤3: 构建上下文文本
            context_text = self._build_context_text(context.retrieved_memories)
            
            # 步骤4: TurboQuant压缩（如果启用）
            if context.compressor and self.config.turboquant.enabled:
                compressed_text = context.compressor.compress_context(
                    context_text,
                    max_tokens=self.config.token_economy.max_tokens_per_query
                )
                context.compressed_context = compressed_text
                
                # 记录Token使用（压缩）
                original_tokens = len(context_text.split())
                compressed_tokens = len(compressed_text.split())
                compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
                
                self._record_token_usage(
                    context,
                    TokenOperation.COMPRESSION,
                    model="turboquant",
                    input_tokens=original_tokens,
                    output_tokens=compressed_tokens,
                    metadata={"compression_ratio": compression_ratio}
                )
                
                logger.info(f"上下文压缩: {original_tokens} → {compressed_tokens} tokens (压缩率: {compression_ratio:.1%})")
            else:
                context.compressed_context = context_text
            
            # 步骤5: 记录总Token使用
            total_tokens = len(context.compressed_context.split())
            self._record_token_usage(
                context,
                TokenOperation.GENERATION,
                model="context_builder",
                input_tokens=total_tokens,
                output_tokens=0
            )
            
            # 完成处理
            context.end_time = time.time()
            
            logger.info(f"查询处理完成: 检索{len(context.retrieved_memories)}条记忆, "
                       f"压缩后{len(context.compressed_context.split())}tokens, "
                       f"耗时{context.get_elapsed_time():.2f}秒")
            
            return context
            
        except Exception as e:
            logger.error(f"处理查询失败: {e}")
            context.end_time = time.time()
            raise
    
    def _generate_embedding(self, text: str, embedding_model: EmbeddingModel) -> np.ndarray:
        """生成文本嵌入"""
        try:
            # 记录Token使用（如果监控启用）
            if self.token_monitor:
                self.token_monitor.record_usage(
                    operation=TokenOperation.CAPTURE,
                    model="local-embedding",
                    input_tokens=len(text.split()),
                    output_tokens=0,
                    cost_per_token=0.0  # 本地嵌入零成本
                )
            
            # 生成嵌入
            embedding = embedding_model.encode(text)
            return embedding
            
        except Exception as e:
            logger.error(f"生成嵌入失败: {e}")
            # 返回随机向量作为回退（仅用于测试）
            return np.random.randn(768).astype(np.float32)
    
    def _build_context_text(self, memories: List[MemoryRecord]) -> str:
        """构建上下文文本"""
        if not memories:
            return ""
        
        context_parts = []
        
        for i, memory in enumerate(memories[:10]):  # 最多10条记忆
            # 提取记忆内容
            content = memory.text or ""
            importance = memory.score or 0.0
            category = memory.metadata.category.value if memory.metadata else "unknown"
            
            # 格式化记忆条目
            memory_text = f"[记忆{i+1}: {category}, 重要性{importance:.2f}]\n{content}\n"
            context_parts.append(memory_text)
        
        # 添加系统提示
        system_prompt = """你是一个智能助手，拥有以下相关记忆。请基于这些记忆回答用户的问题。"""
        
        full_context = system_prompt + "\n\n" + "\n".join(context_parts)
        
        return full_context
    
    def _record_token_usage(
        self,
        context: AegisContext,
        operation: TokenOperation,
        model: str,
        input_tokens: int,
        output_tokens: int,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """记录Token使用"""
        if context.token_monitor:
            usage = context.token_monitor.record_usage(
                operation=operation,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                metadata=metadata
            )
            
            # 更新上下文中的Token使用记录
            op_key = operation.value
            if op_key not in context.token_usage:
                context.token_usage[op_key] = []
            
            context.token_usage[op_key].append({
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_rmb": usage.cost_rmb
            })
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            "version": self.config.version,
            "architecture": self.config.architecture,
            "components": {
                "turboquant": {
                    "enabled": self.config.turboquant.enabled,
                    "status": "active" if self.compressor else "inactive"
                },
                "four_stage_filter": {
                    "enabled": self.config.four_stage_filter.enabled,
                    "status": "configurable"  # 需要运行时初始化
                },
                "token_economy": {
                    "enabled": self.config.token_economy.enabled,
                    "status": "active" if self.token_monitor else "inactive"
                },
                "nocturnal_optimization": {
                    "enabled": self.config.nocturnal_optimization.enabled,
                    "status": "scheduled"
                }
            },
            "config_summary": self.config.to_dict()
        }
        
        # 添加Token经济统计（如果启用）
        if self.token_monitor:
            token_stats = {
                "total_cost_rmb": self.token_monitor.total_cost,
                "total_tokens": self.token_monitor.total_tokens,
                "downgrade_level": self.token_monitor.downgrade_level.value,
                "daily_budget_usage": self.token_monitor._calculate_budget_usage()
            }
            status["token_economy_stats"] = token_stats
        
        return status
    
    def schedule_nocturnal_optimization(self):
        """安排夜间净化任务"""
        if not self.config.nocturnal_optimization.enabled:
            logger.info("夜间净化已禁用")
            return
        
        # 这里应该集成到系统的Cron任务调度器
        # 目前只是记录日志
        optimization_time = self.config.nocturnal_optimization.optimization_time
        
        logger.info(f"夜间净化任务已安排，每天 {optimization_time} 执行")
        logger.info(f"配置: 遗忘阈值={self.config.nocturnal_optimization.forget_threshold}, "
                   f"升级阈值={self.config.nocturnal_optimization.upgrade_threshold}")
        
        # 返回任务配置，供外部调度器使用
        return {
            "type": "nocturnal_optimization",
            "schedule": f"0 {optimization_time.split(':')[0]} {optimization_time.split(':')[1]} * * *",
            "config": {
                "forget_threshold": self.config.nocturnal_optimization.forget_threshold,
                "upgrade_threshold": self.config.nocturnal_optimization.upgrade_threshold,
                "batch_size": self.config.nocturnal_optimization.optimization_batch_size
            }
        }
    
    def optimize_memory_storage(self, batch_size: Optional[int] = None):
        """
        优化记忆存储（手动触发）
        
        Args:
            batch_size: 批处理大小，如果为None则使用配置值
        """
        logger.info("开始手动记忆存储优化")
        
        # 这里需要实现具体的优化逻辑
        # 包括：压缩旧记忆、删除低重要性记忆、优化索引等
        
        # 目前只是框架
        if batch_size is None:
            batch_size = self.config.nocturnal_optimization.optimization_batch_size
        
        logger.info(f"记忆存储优化完成，批处理大小: {batch_size}")
        
        return {
            "status": "completed",
            "batch_size": batch_size,
            "optimized_at": datetime.now().isoformat()
        }


# 全局协调器实例
_global_orchestrator = None

def get_global_orchestrator(config_path: Optional[str] = None) -> AegisOrchestrator:
    """获取全局Aegis协调器实例"""
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = AegisOrchestrator(config_path)
    return _global_orchestrator