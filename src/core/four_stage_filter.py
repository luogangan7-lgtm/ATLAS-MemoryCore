"""
四级过滤检索系统 - Aegis-Cortex V6.2核心组件
实现元数据预过滤 → 向量相似度 → 重要性分数 → 时间衰减调整
"""

import numpy as np
from typing import Dict, List, Tuple, Any, Optional, Set
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from .scoring import MemoryScoringEngine as ScoringEngine, ScoringConfig
from .qdrant_storage import QdrantMemoryStorage, MemoryRecord

logger = logging.getLogger(__name__)


@dataclass
class FourStageFilterConfig:
    """四级过滤配置"""
    
    # 阶段1: 元数据预过滤
    metadata_filters: Dict[str, Any] = None
    require_all_metadata: bool = False
    
    # 阶段2: 向量相似度过滤
    similarity_threshold: float = 0.82
    max_candidates_per_stage: int = 1000
    
    # 阶段3: 重要性分数过滤
    importance_threshold: float = 0.5
    min_importance_for_recall: Dict[str, float] = None  # 按类别的最小重要性
    
    # 阶段4: 时间衰减调整
    use_ebbinghaus_decay: bool = True
    half_life_days: float = 1.0
    recency_weight: float = 0.25
    
    # 分层记忆参数
    working_memory_limit: int = 10
    short_term_days: int = 1
    medium_term_days: int = 7
    long_term_all: bool = True
    
    # 性能参数
    enable_caching: bool = True
    cache_ttl_seconds: int = 300
    
    def __post_init__(self):
        if self.metadata_filters is None:
            self.metadata_filters = {}
        if self.min_importance_for_recall is None:
            self.min_importance_for_recall = {
                "working": 0.0,      # 工作记忆：全部召回
                "short_term": 0.3,   # 短期记忆：重要性>0.3
                "medium_term": 0.5,  # 中期记忆：重要性>0.5
                "long_term": 0.7     # 长期记忆：重要性>0.7
            }


class FourStageFilter:
    """四级过滤检索器"""
    
    def __init__(
        self,
        qdrant_storage: QdrantMemoryStorage,
        scoring_engine: ScoringEngine,
        config: Optional[FourStageFilterConfig] = None
    ):
        self.qdrant_storage = qdrant_storage
        self.scoring_engine = scoring_engine
        self.config = config or FourStageFilterConfig()
        
        # 缓存
        self.cache = {} if self.config.enable_caching else None
        self.cache_timestamps = {}
        
        logger.info("四级过滤检索系统初始化完成")
    
    def retrieve_memories(
        self,
        query: str,
        query_embedding: np.ndarray,
        context: Dict[str, Any] = None
    ) -> List[MemoryRecord]:
        """
        四级过滤检索
        
        Args:
            query: 查询文本
            query_embedding: 查询向量
            context: 上下文信息
            
        Returns:
            过滤后的记忆记录
        """
        context = context or {}
        
        # 检查缓存
        cache_key = self._generate_cache_key(query, query_embedding, context)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            logger.debug(f"从缓存获取检索结果: {len(cached_result)} 条记录")
            return cached_result
        
        logger.info(f"开始四级过滤检索: '{query[:50]}...'")
        
        # 阶段0: 获取所有候选记忆
        all_candidates = self._get_all_candidates(context)
        logger.debug(f"阶段0: 获取 {len(all_candidates)} 个候选记忆")
        
        if not all_candidates:
            return []
        
        # 阶段1: 元数据预过滤
        stage1_results = self._stage1_metadata_filter(all_candidates, context)
        logger.debug(f"阶段1: 元数据过滤后剩余 {len(stage1_results)} 个")
        
        if not stage1_results:
            return []
        
        # 阶段2: 向量相似度过滤
        stage2_results = self._stage2_similarity_filter(stage1_results, query_embedding)
        logger.debug(f"阶段2: 相似度过滤后剩余 {len(stage2_results)} 个")
        
        if not stage2_results:
            return []
        
        # 阶段3: 重要性分数过滤
        stage3_results = self._stage3_importance_filter(stage2_results)
        logger.debug(f"阶段3: 重要性过滤后剩余 {len(stage3_results)} 个")
        
        if not stage3_results:
            return []
        
        # 阶段4: 时间衰减调整和最终排序
        final_results = self._stage4_time_decay_adjustment(stage3_results)
        logger.debug(f"阶段4: 时间衰减调整后得到 {len(final_results)} 个最终结果")
        
        # 更新缓存
        self._update_cache(cache_key, final_results)
        
        return final_results
    
    def _get_all_candidates(self, context: Dict[str, Any]) -> List[MemoryRecord]:
        """获取所有候选记忆"""
        try:
            # 根据上下文决定检索策略
            limit = self.config.max_candidates_per_stage
            
            # 如果有特定类别过滤，使用类别检索
            if "category" in context:
                category = context["category"]
                return self.qdrant_storage.search_by_category(
                    category=category,
                    limit=limit
                )
            
            # 否则获取最近记忆
            return self.qdrant_storage.get_recent_memories(limit=limit)
        
        except Exception as e:
            logger.error(f"获取候选记忆失败: {e}")
            return []
    
    def _stage1_metadata_filter(
        self,
        candidates: List[MemoryRecord],
        context: Dict[str, Any]
    ) -> List[MemoryRecord]:
        """阶段1: 元数据预过滤"""
        if not self.config.metadata_filters and not context.get("metadata_filters"):
            return candidates
        
        filters = {**self.config.metadata_filters, **context.get("metadata_filters", {})}
        if not filters:
            return candidates
        
        filtered = []
        
        for record in candidates:
            if self._matches_metadata_filters(record, filters):
                filtered.append(record)
        
        return filtered
    
    def _matches_metadata_filters(
        self,
        record: MemoryRecord,
        filters: Dict[str, Any]
    ) -> bool:
        """检查记录是否匹配元数据过滤器"""
        
        if not filters:
            return True
        
        metadata = record.metadata or {}
        
        if self.config.require_all_metadata:
            # 必须匹配所有过滤器
            for key, expected_value in filters.items():
                if key not in metadata:
                    return False
                if metadata[key] != expected_value:
                    return False
            return True
        else:
            # 匹配任意过滤器即可
            for key, expected_value in filters.items():
                if key in metadata and metadata[key] == expected_value:
                    return True
            return False
    
    def _stage2_similarity_filter(
        self,
        candidates: List[MemoryRecord],
        query_embedding: np.ndarray
    ) -> List[Tuple[MemoryRecord, float]]:
        """阶段2: 向量相似度过滤"""
        if not candidates:
            return []
        
        results = []
        
        for record in candidates:
            if record.embedding is None:
                continue
            
            # 计算余弦相似度
            similarity = self._cosine_similarity(query_embedding, record.embedding)
            
            if similarity >= self.config.similarity_threshold:
                results.append((record, similarity))
        
        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        # 限制数量
        max_results = min(len(results), self.config.max_candidates_per_stage // 2)
        return results[:max_results]
    
    def _stage3_importance_filter(
        self,
        candidates: List[Tuple[MemoryRecord, float]]
    ) -> List[Tuple[MemoryRecord, float, float]]:
        """阶段3: 重要性分数过滤"""
        if not candidates:
            return []
        
        results = []
        
        for record, similarity in candidates:
            # 获取重要性分数
            importance_score = record.importance_score or 0.0
            
            # 检查是否达到最小重要性阈值
            memory_age = self._get_memory_age(record)
            memory_layer = self._determine_memory_layer(memory_age)
            
            min_importance = self.config.min_importance_for_recall.get(memory_layer, 0.0)
            
            if importance_score >= min_importance:
                # 计算综合分数：相似度 × 重要性
                combined_score = similarity * (0.7 + 0.3 * importance_score)
                results.append((record, similarity, combined_score))
        
        # 按综合分数排序
        results.sort(key=lambda x: x[2], reverse=True)
        
        # 限制数量
        max_results = min(len(results), self.config.max_candidates_per_stage // 4)
        return results[:max_results]
    
    def _stage4_time_decay_adjustment(
        self,
        candidates: List[Tuple[MemoryRecord, float, float]]
    ) -> List[MemoryRecord]:
        """阶段4: 时间衰减调整和最终排序"""
        if not candidates:
            return []
        
        adjusted_results = []
        
        for record, similarity, combined_score in candidates:
            # 应用时间衰减
            if self.config.use_ebbinghaus_decay:
                decay_factor = self._calculate_ebbinghaus_decay(record)
                adjusted_score = combined_score * decay_factor
            else:
                adjusted_score = combined_score
            
            # 添加调整后的分数
            record.adjusted_score = adjusted_score
            adjusted_results.append((record, adjusted_score))
        
        # 按调整后分数排序
        adjusted_results.sort(key=lambda x: x[1], reverse=True)
        
        # 提取记录
        final_records = [record for record, _ in adjusted_results]
        
        # 分层限制
        final_records = self._apply_layer_limits(final_records)
        
        return final_records
    
    def _apply_layer_limits(self, records: List[MemoryRecord]) -> List[MemoryRecord]:
        """应用分层记忆限制"""
        working_memories = []
        short_term_memories = []
        medium_term_memories = []
        long_term_memories = []
        
        for record in records:
            memory_age = self._get_memory_age(record)
            layer = self._determine_memory_layer(memory_age)
            
            if layer == "working":
                working_memories.append(record)
            elif layer == "short_term":
                short_term_memories.append(record)
            elif layer == "medium_term":
                medium_term_memories.append(record)
            else:
                long_term_memories.append(record)
        
        # 应用各层限制
        working_memories = working_memories[:self.config.working_memory_limit]
        short_term_memories = short_term_memories[:self.config.max_candidates_per_stage // 4]
        medium_term_memories = medium_term_memories[:self.config.max_candidates_per_stage // 8]
        long_term_memories = long_term_memories[:self.config.max_candidates_per_stage // 16]
        
        # 合并结果（工作记忆优先）
        final_records = working_memories + short_term_memories + medium_term_memories + long_term_memories
        
        return final_records
    
    def _get_memory_age(self, record: MemoryRecord) -> float:
        """获取记忆年龄（天）"""
        if not record.created_at:
            return 0.0
        
        try:
            if isinstance(record.created_at, str):
                created_dt = datetime.fromisoformat(record.created_at.replace('Z', '+00:00'))
            else:
                created_dt = record.created_at
            
            age_delta = datetime.now() - created_dt
            return age_delta.total_seconds() / (24 * 3600)  # 转换为天
        
        except Exception as e:
            logger.warning(f"计算记忆年龄失败: {e}")
            return 0.0
    
    def _determine_memory_layer(self, age_days: float) -> str:
        """确定记忆层级"""
        if age_days < 0.1:  # 2.4小时内
            return "working"
        elif age_days <= self.config.short_term_days:
            return "short_term"
        elif age_days <= self.config.medium_term_days:
            return "medium_term"
        else:
            return "long_term"
    
    def _calculate_ebbinghaus_decay(self, record: MemoryRecord) -> float:
        """计算艾宾浩斯衰减因子"""
        age_days = self._get_memory_age(record)
        
        if age_days <= 0:
            return 1.0
        
        # 艾宾浩斯遗忘曲线公式: R = e^(-t/S)
        # 其中S是半衰期
        decay_factor = np.exp(-age_days / self.config.half_life_days)
        
        # 应用重要性权重
        importance = record.importance_score or 0.5
        importance_weight = 0.3 + 0.7 * importance  # 重要性越高，衰减越慢
        
        adjusted_decay = decay_factor * importance_weight
        
        return min(max(adjusted_decay, 0.1), 1.0)  # 限制在0.1-1.0之间
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        if vec1 is None or vec2 is None:
            return 0.0
        
        try:
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
        
        except Exception as e:
            logger.warning(f"计算余弦相似度失败: {e}")
            return 0.0
    
    def _generate_cache_key(
        self,
        query: str,
        query_embedding: np.ndarray,
        context: Dict[str, Any]
    ) -> str:
        """生成缓存键"""
        import hashlib
        import json
        
        # 简化查询文本
        query_hash = hashlib.md5(query.encode()).hexdigest()
        
        # 简化向量（取前10个元素和统计量）
        if query_embedding is not None:
            vec_summary = f"{query_embedding[:10].sum():.6f}_{query_embedding.mean():.6f}"
        else:
            vec_summary = "none"
        
        # 简化上下文
        context_str = json.dumps(context, sort_keys=True) if context else "none"
        context_hash = hashlib.md5(context_str.encode()).hexdigest()
        
        return f"{query_hash}_{vec_summary}_{context_hash}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[List[MemoryRecord]]:
        """从缓存获取结果"""
        if self.cache is None:
            return None
        
        if cache_key in self.cache:
            timestamp = self.cache_timestamps.get(cache_key, 0)
            current_time = datetime.now().timestamp()
            
            if current_time - timestamp <= self.config.cache_ttl_seconds:
                return self.cache[cache_key]
            else:
                # 缓存过期
                del self.cache[cache_key]
                del self.cache_timestamps[cache_key]
        
        return None
    
    def _update_cache(self, cache_key: str, results: List[MemoryRecord]):
        """更新缓存"""
        if self.cache is not None:
            self.cache[cache_key] = results
            self.cache_timestamps[cache_key] = datetime.now().timestamp()
    
    def clear_cache(self):
        """清空缓存"""
        if self.cache is not None:
            self.cache.clear()
            self.cache_timestamps.clear()
            logger.info("四级过滤缓存已清空")
    
    def get_filter_stats(self) -> Dict[str, Any]:
        """获取过滤统计信息"""
        return {
            "cache_enabled": self.config.enable_caching,
            "cache_size": len(self.cache) if self.cache else 0,
            "similarity_threshold": self.config.similarity_threshold,
            "importance_threshold": self.config.importance_threshold,
            "use_ebbinghaus_decay": self.config.use_ebbinghaus_decay
        }


# 全局过滤器实例
_global_filter = None

def get_global_filter(
    qdrant_storage: Optional[QdrantMemoryStorage] = None,
    scoring_engine: Optional[ScoringEngine] = None
) -> FourStageFilter:
    """获取全局四级过滤器实例"""
    global _global_filter
    if _global_filter is None and qdrant_storage and scoring_engine:
        _global_filter = FourStageFilter(qdrant_storage, scoring_engine)
    return _global_filter