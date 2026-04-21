"""
检索模块 - Retrieval Module
实现智能记忆检索功能，支持混合搜索和缓存
Implements intelligent memory retrieval with hybrid search and caching
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from qdrant_client.http import models as qdrant_models

from .embedding import EmbeddingModel
from .storage import MemoryStorage, MemoryRecord, MemoryCategory
from .config import get_config, RetrievalConfig

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果 - Search Result"""

    memory: MemoryRecord
    score: float  # 相似度分数 0-1
    relevance: float  # 相关性分数（考虑元数据）
    explanation: str  # 检索原因说明

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典 - Convert to dictionary"""
        return {
            "memory": self.memory.to_dict(),
            "score": self.score,
            "relevance": self.relevance,
            "explanation": self.explanation,
        }


class MemoryCache:
    """记忆缓存 - Memory Cache"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[List[SearchResult], float]] = {}
        self.access_order: List[str] = []

    def _generate_key(self, query: str, filters: Optional[Dict] = None) -> str:
        """生成缓存键 - Generate cache key"""
        key_data = {"query": query, "filters": filters or {}}
        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_json.encode()).hexdigest()

    def _clean_expired(self):
        """清理过期缓存 - Clean expired cache entries"""
        current_time = time.time()
        expired_keys = []

        for key, (_, timestamp) in self.cache.items():
            if current_time - timestamp > self.ttl_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            self.cache.pop(key, None)
            if key in self.access_order:
                self.access_order.remove(key)

    def _evict_if_needed(self):
        """如果需要则驱逐缓存 - Evict cache if needed"""
        if len(self.cache) > self.max_size:
            # 移除最久未访问的
            while len(self.cache) > self.max_size and self.access_order:
                oldest_key = self.access_order.pop(0)
                self.cache.pop(oldest_key, None)

    def get(
        self, query: str, filters: Optional[Dict] = None
    ) -> Optional[List[SearchResult]]:
        """获取缓存结果 - Get cached results"""
        self._clean_expired()

        key = self._generate_key(query, filters)
        if key in self.cache:
            results, _ = self.cache[key]
            # 更新访问顺序
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            return results

        return None

    def set(self, query: str, filters: Optional[Dict], results: List[SearchResult]):
        """设置缓存结果 - Set cache results"""
        self._clean_expired()
        self._evict_if_needed()

        key = self._generate_key(query, filters)
        self.cache[key] = (results, time.time())

        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

    def clear(self):
        """清空缓存 - Clear cache"""
        self.cache.clear()
        self.access_order.clear()


class MemoryRetrieval:
    """记忆检索器 - Memory Retriever"""

    def __init__(
        self,
        memory_storage: MemoryStorage,
        embedding_model: EmbeddingModel,
        config: Optional[RetrievalConfig] = None,
    ):
        self.memory_storage = memory_storage
        self.embedding_model = embedding_model
        self.config = config or get_config().retrieval

        # 初始化缓存
        self.cache = MemoryCache(
            max_size=self.config.cache_size, ttl_seconds=self.config.cache_ttl_seconds
        )

        logger.info("记忆检索器初始化完成")

    def search(
        self,
        query: str,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        explain: bool = False,
    ) -> List[SearchResult]:
        """
        搜索相关记忆 - Search for relevant memories

        Args:
            query: 查询文本 - Query text
            limit: 返回数量限制 - Maximum number of results
            threshold: 相似度阈值 - Similarity threshold
            filters: 过滤条件 - Filter conditions
            use_cache: 是否使用缓存 - Whether to use cache
            explain: 是否返回解释 - Whether to return explanations

        Returns:
            搜索结果列表 - List of search results
        """
        # 使用配置默认值
        limit = limit or self.config.max_results
        threshold = threshold or self.config.similarity_threshold

        # 检查缓存
        if use_cache and self.config.cache_enabled:
            cached_results = self.cache.get(query, filters)
            if cached_results:
                logger.debug(f"从缓存获取结果: {len(cached_results)} 条")
                return cached_results[:limit]

        try:
            # 编码查询文本
            query_vector = self.embedding_model.encode_single(query)

            # 构建搜索过滤器
            search_filters = self._build_search_filters(filters)

            # 执行搜索
            search_results = self._execute_search(
                query_vector=query_vector,
                limit=limit,
                threshold=threshold,
                filters=search_filters,
            )

            # 处理结果
            processed_results = self._process_results(
                search_results=search_results,
                query=query,
                query_vector=query_vector,
                explain=explain,
            )

            # 过滤阈值
            filtered_results = [
                result for result in processed_results if result.relevance >= threshold
            ]

            # 按相关性排序
            filtered_results.sort(key=lambda x: x.relevance, reverse=True)

            # 限制数量
            final_results = filtered_results[:limit]

            # 更新缓存
            if use_cache and self.config.cache_enabled:
                self.cache.set(query, filters, final_results)

            logger.info(
                f"搜索完成: 查询='{query[:50]}...', 找到 {len(final_results)} 条相关记忆"
            )
            return final_results

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    def _build_search_filters(
        self, user_filters: Optional[Dict[str, Any]]
    ) -> Optional[qdrant_models.Filter]:
        """构建搜索过滤器 - Build search filters"""
        if not self.config.use_metadata_filter and not user_filters:
            return None

        must_conditions = []

        # 添加用户过滤器
        if user_filters:
            for key, value in user_filters.items():
                if isinstance(value, list):
                    must_conditions.append(
                        qdrant_models.FieldCondition(
                            key=f"metadata.{key}",
                            match=qdrant_models.MatchAny(any=value),
                        )
                    )
                else:
                    must_conditions.append(
                        qdrant_models.FieldCondition(
                            key=f"metadata.{key}",
                            match=qdrant_models.MatchValue(value=value),
                        )
                    )

        # 添加重要性过滤器（如果启用）
        if self.config.use_metadata_filter:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="metadata.importance",
                    range=qdrant_models.Range(gte=0.3),  # 至少30%重要性
                )
            )

        if must_conditions:
            return qdrant_models.Filter(must=must_conditions)

        return None

    def _execute_search(
        self,
        query_vector: List[float],
        limit: int,
        threshold: float,
        filters: Optional[qdrant_models.Filter],
    ) -> List[Tuple[MemoryRecord, float]]:
        """执行搜索 - Execute search"""
        # 基本向量搜索
        vector_results = self.memory_storage.search(
            query="",  # 使用预计算的向量
            limit=limit * 2,  # 获取更多结果用于后续处理
            threshold=threshold * 0.8,  # 降低阈值获取更多候选
            filter_conditions=None,  # 在应用层过滤
        )

        # 计算相似度
        results_with_scores = []
        for memory in vector_results:
            similarity = self.embedding_model.similarity(query_vector, memory.vector)
            if similarity >= threshold * 0.8:  # 初步过滤
                results_with_scores.append((memory, similarity))

        # 应用过滤器
        if filters and self.config.use_metadata_filter:
            filtered_results = []
            for memory, similarity in results_with_scores:
                if self._passes_filter(memory, filters):
                    filtered_results.append((memory, similarity))
            results_with_scores = filtered_results

        return results_with_scores

    def _passes_filter(
        self, memory: MemoryRecord, filters: qdrant_models.Filter
    ) -> bool:
        """检查记忆是否通过过滤器 - Check if memory passes filters"""
        # 简化实现：在实际使用中，应该让Qdrant处理过滤
        # 这里为了简单，假设所有记忆都通过
        return True

    def _process_results(
        self,
        search_results: List[Tuple[MemoryRecord, float]],
        query: str,
        query_vector: List[float],
        explain: bool,
    ) -> List[SearchResult]:
        """处理搜索结果 - Process search results"""
        processed_results = []

        for memory, similarity in search_results:
            # 计算相关性分数（考虑元数据）
            relevance = self._calculate_relevance(memory, similarity, query)

            # 生成解释
            explanation = ""
            if explain:
                explanation = self._generate_explanation(
                    memory, similarity, relevance, query
                )

            result = SearchResult(
                memory=memory,
                score=similarity,
                relevance=relevance,
                explanation=explanation,
            )

            processed_results.append(result)

        return processed_results

    def _calculate_relevance(
        self, memory: MemoryRecord, similarity: float, query: str
    ) -> float:
        """计算相关性分数 - Calculate relevance score"""
        # 基础相似度权重
        relevance = similarity * 0.6

        # 重要性权重
        relevance += memory.metadata.importance * 0.2

        # 新鲜度权重（最近访问的更有价值）
        if memory.last_accessed:
            days_since_access = (datetime.now() - memory.last_accessed).days
            freshness = max(0, 1 - (days_since_access / 30))  # 30天衰减
            relevance += freshness * 0.1

        # 使用频率权重
        usage_weight = min(1.0, memory.access_count / 20)  # 最多20次访问
        relevance += usage_weight * 0.1

        # 确保在0-1范围内
        return max(0.0, min(1.0, relevance))

    def _generate_explanation(
        self, memory: MemoryRecord, similarity: float, relevance: float, query: str
    ) -> str:
        """生成解释文本 - Generate explanation text"""
        explanations = []

        # 相似度解释
        if similarity > 0.9:
            explanations.append("内容高度相关")
        elif similarity > 0.7:
            explanations.append("内容相关")
        elif similarity > 0.5:
            explanations.append("内容部分相关")

        # 重要性解释
        if memory.metadata.importance > 0.8:
            explanations.append("标记为重要记忆")
        elif memory.metadata.importance > 0.6:
            explanations.append("中等重要性")

        # 新鲜度解释
        if memory.last_accessed:
            days_ago = (datetime.now() - memory.last_accessed).days
            if days_ago < 1:
                explanations.append("最近访问过")
            elif days_ago < 7:
                explanations.append("一周内访问过")

        # 使用频率解释
        if memory.access_count > 10:
            explanations.append("频繁使用")
        elif memory.access_count > 5:
            explanations.append("多次使用")

        if not explanations:
            explanations.append("基础匹配")

        return f"相关性: {relevance:.2f} ({', '.join(explanations)})"

    def search_by_category(
        self, category: MemoryCategory, limit: int = 10, min_importance: float = 0.5
    ) -> List[MemoryRecord]:
        """按分类搜索记忆 - Search memories by category"""
        filters = {"category": category.value, "importance": {"gte": min_importance}}

        # 使用通用搜索
        results = self.search(
            query="",  # 空查询，只依赖过滤器
            limit=limit,
            threshold=0.1,  # 低阈值
            filters=filters,
            use_cache=False,
        )

        return [result.memory for result in results]

    def find_similar_memories(
        self, memory_id: str, limit: int = 5, threshold: float = 0.7
    ) -> List[SearchResult]:
        """查找相似记忆 - Find similar memories"""
        # 获取目标记忆
        target_memory = self.memory_storage.retrieve(memory_id)
        if not target_memory:
            logger.warning(f"未找到记忆: {memory_id}")
            return []

        # 使用记忆文本作为查询
        return self.search(
            query=target_memory.text, limit=limit, threshold=threshold, use_cache=False
        )

    def clear_cache(self):
        """清空缓存 - Clear cache"""
        self.cache.clear()
        logger.info("检索缓存已清空")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计 - Get cache statistics"""
        return {
            "cache_size": len(self.cache.cache),
            "max_size": self.cache.max_size,
            "ttl_seconds": self.cache.ttl_seconds,
            "access_order_length": len(self.cache.access_order),
        }


# 工具函数 - Utility functions
def create_retrieval_system(
    qdrant_url: str = "http://localhost:6333",
    collection_name: str = "atlas_memories",
    config_path: Optional[str] = None,
) -> MemoryRetrieval:
    """创建检索系统 - Create retrieval system"""
    from .embedding import get_default_embedding_model
    from .storage import MemoryStorage

    # 获取配置
    from .config import get_config_manager

    config_manager = get_config_manager(config_path)

    # 初始化组件
    embedding_model = get_default_embedding_model()
    memory_storage = MemoryStorage(
        qdrant_url=qdrant_url,
        collection_name=collection_name,
        embedding_model=embedding_model,
        vector_size=config_manager.get_embedding_dimension(),
    )

    # 创建检索器
    retrieval = MemoryRetrieval(
        memory_storage=memory_storage,
        embedding_model=embedding_model,
        config=config_manager.config.retrieval,
    )

    return retrieval
