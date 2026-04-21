"""
性能优化器 - Phase 3 核心模块
实现缓存系统、查询优化、批量处理优化
"""

import logging
import time
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from functools import lru_cache
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

# 尝试导入缓存库
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available, using in-memory cache")

@dataclass
class CacheConfig:
    """缓存配置"""
    enabled: bool = True
    ttl_seconds: int = 3600  # 缓存过期时间
    max_size: int = 10000  # 最大缓存条目数
    use_redis: bool = True  # 是否使用Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0

@dataclass
class QueryOptimizationConfig:
    """查询优化配置"""
    enable_query_rewrite: bool = True
    enable_result_caching: bool = True
    enable_prefetch: bool = True
    batch_size: int = 10
    parallel_processing: bool = True
    max_workers: int = 4
    timeout_seconds: int = 30

@dataclass
class PerformanceMetrics:
    """性能指标"""
    query_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    memory_usage_mb: float = 0.0
    compression_ratio: float = 0.0
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        if self.query_count == 0:
            return 0.0
        return self.cache_hits / self.query_count

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.redis_client = None
        self.memory_cache = {}
        self.cache_lock = threading.RLock()
        
        if config.enabled and config.use_redis and REDIS_AVAILABLE:
            self._init_redis()
    
    def _init_redis(self):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                db=self.config.redis_db,
                decode_responses=True
            )
            # 测试连接
            self.redis_client.ping()
            self.logger.info("Redis cache initialized successfully")
        except Exception as e:
            self.logger.warning(f"Failed to connect to Redis: {e}, using in-memory cache")
            self.redis_client = None
    
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """生成缓存键"""
        # 将参数序列化为字符串
        args_str = json.dumps(args, sort_keys=True)
        kwargs_str = json.dumps(kwargs, sort_keys=True)
        
        # 生成哈希
        content = f"{prefix}:{args_str}:{kwargs_str}"
        cache_key = hashlib.md5(content.encode()).hexdigest()
        
        return f"atlas:{prefix}:{cache_key}"
    
    def get(self, prefix: str, *args, **kwargs) -> Optional[Any]:
        """获取缓存值"""
        if not self.config.enabled:
            return None
        
        cache_key = self._generate_cache_key(prefix, *args, **kwargs)
        
        try:
            # 首先尝试Redis
            if self.redis_client:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            
            # 然后尝试内存缓存
            with self.cache_lock:
                if cache_key in self.memory_cache:
                    entry = self.memory_cache[cache_key]
                    # 检查是否过期
                    if datetime.now() < entry['expires']:
                        return entry['value']
                    else:
                        # 删除过期条目
                        del self.memory_cache[cache_key]
        
        except Exception as e:
            self.logger.error(f"Cache get error: {e}")
        
        return None
    
    def set(self, prefix: str, value: Any, *args, **kwargs):
        """设置缓存值"""
        if not self.config.enabled:
            return
        
        cache_key = self._generate_cache_key(prefix, *args, **kwargs)
        expires = datetime.now() + timedelta(seconds=self.config.ttl_seconds)
        
        try:
            # 存储到Redis
            if self.redis_client:
                self.redis_client.setex(
                    cache_key,
                    self.config.ttl_seconds,
                    json.dumps(value)
                )
            
            # 存储到内存缓存
            with self.cache_lock:
                # 检查缓存大小，如果超过限制则清理
                if len(self.memory_cache) >= self.config.max_size:
                    self._cleanup_memory_cache()
                
                self.memory_cache[cache_key] = {
                    'value': value,
                    'expires': expires,
                    'created': datetime.now()
                }
        
        except Exception as e:
            self.logger.error(f"Cache set error: {e}")
    
    def _cleanup_memory_cache(self):
        """清理内存缓存"""
        # 删除过期条目
        now = datetime.now()
        expired_keys = [
            key for key, entry in self.memory_cache.items()
            if entry['expires'] < now
        ]
        
        for key in expired_keys:
            del self.memory_cache[key]
        
        # 如果仍然超过限制，删除最旧的条目
        if len(self.memory_cache) >= self.config.max_size:
            # 按创建时间排序
            sorted_keys = sorted(
                self.memory_cache.keys(),
                key=lambda k: self.memory_cache[k]['created']
            )
            
            # 删除最旧的20%
            to_delete = sorted_keys[:max(1, len(sorted_keys) // 5)]
            for key in to_delete:
                del self.memory_cache[key]
    
    def invalidate(self, prefix: str = None):
        """使缓存失效"""
        try:
            if prefix:
                # 使特定前缀的缓存失效
                pattern = f"atlas:{prefix}:*"
                
                if self.redis_client:
                    # Redis批量删除
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        self.redis_client.delete(*keys)
                
                # 内存缓存删除
                with self.cache_lock:
                    keys_to_delete = [
                        key for key in self.memory_cache.keys()
                        if key.startswith(f"atlas:{prefix}:")
                    ]
                    for key in keys_to_delete:
                        del self.memory_cache[key]
            
            else:
                # 使所有缓存失效
                if self.redis_client:
                    keys = self.redis_client.keys("atlas:*")
                    if keys:
                        self.redis_client.delete(*keys)
                
                with self.cache_lock:
                    self.memory_cache.clear()
        
        except Exception as e:
            self.logger.error(f"Cache invalidation error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            'enabled': self.config.enabled,
            'use_redis': self.config.use_redis and self.redis_client is not None,
            'memory_cache_size': len(self.memory_cache),
            'max_size': self.config.max_size,
            'ttl_seconds': self.config.ttl_seconds
        }
        
        if self.redis_client:
            try:
                redis_info = self.redis_client.info()
                stats['redis_used_memory'] = redis_info.get('used_memory_human', 'N/A')
                stats['redis_connected_clients'] = redis_info.get('connected_clients', 0)
            except:
                stats['redis_info'] = 'unavailable'
        
        return stats

class QueryOptimizer:
    """查询优化器"""
    
    def __init__(self, config: QueryOptimizationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.metrics = PerformanceMetrics()
        self.executor = ThreadPoolExecutor(max_workers=config.max_workers) if config.parallel_processing else None
    
    def optimize_query(self, query: str, context: Optional[Dict] = None) -> str:
        """优化查询文本"""
        if not self.config.enable_query_rewrite or not query:
            return query
        
        context = context or {}
        
        try:
            # 简单的查询重写规则
            optimized = query.lower().strip()
            
            # 移除多余的空白字符
            optimized = ' '.join(optimized.split())
            
            # 扩展缩写
            abbreviations = {
                'w/': 'with',
                'w/o': 'without',
                'e.g.': 'for example',
                'i.e.': 'that is',
                'etc.': 'and so on'
            }
            
            for abbr, full in abbreviations.items():
                optimized = optimized.replace(abbr, full)
            
            # 添加上下文信息
            if context.get('category'):
                # 可以根据类别添加相关关键词
                pass
            
            # 确保查询以句号结束（如果不是问句）
            if not optimized.endswith(('.', '?', '!')):
                optimized += '.'
            
            if optimized != query:
                self.logger.debug(f"Query optimized: '{query}' -> '{optimized}'")
            
            return optimized
        
        except Exception as e:
            self.logger.error(f"Query optimization failed: {e}")
            return query
    
    def batch_process(self, queries: List[str], processor_func, **kwargs) -> List[Any]:
        """批量处理查询"""
        if not self.config.parallel_processing or len(queries) <= 1:
            # 顺序处理
            return [processor_func(q, **kwargs) for q in queries]
        
        # 并行处理
        results = []
        futures = {}
        
        try:
            # 提交任务
            for i, query in enumerate(queries):
                future = self.executor.submit(processor_func, query, **kwargs)
                futures[future] = i
            
            # 收集结果
            temp_results = [None] * len(queries)
            for future in as_completed(futures, timeout=self.config.timeout_seconds):
                idx = futures[future]
                try:
                    temp_results[idx] = future.result()
                except Exception as e:
                    self.logger.error(f"Batch processing failed for query {idx}: {e}")
                    temp_results[idx] = None
            
            results = temp_results
        
        except Exception as e:
            self.logger.error(f"Batch processing failed: {e}")
            # 回退到顺序处理
            results = [processor_func(q, **kwargs) for q in queries]
        
        return results
    
    def prefetch_related(self, query: str, storage_client: Any, limit: int = 5) -> List[Any]:
        """预取相关记忆"""
        if not self.config.enable_prefetch:
            return []
        
        try:
            # 获取主要结果
            main_results = storage_client.search(query=query, limit=limit)
            
            if not main_results:
                return []
            
            # 提取相关关键词进行预取
            all_text = ' '.join([r.get('text', '') for r in main_results])
            words = all_text.lower().split()
            
            # 找出高频词（排除停用词）
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
            word_freq = {}
            for word in words:
                if len(word) > 3 and word not in stop_words:
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            # 取前3个高频词作为预取查询
            top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:3]
            
            prefetch_results = []
            for word, _ in top_words:
                try:
                    prefetched = storage_client.search(query=word, limit=2)
                    prefetch_results.extend(prefetched)
                except:
                    continue
            
            # 去重
            seen_ids = set()
            unique_results = []
            for result in prefetch_results:
                result_id = result.get('id')
                if result_id and result_id not in seen_ids:
                    seen_ids.add(result_id)
                    unique_results.append(result)
            
            return unique_results[:limit]
        
        except Exception as e:
            self.logger.error(f"Prefetch failed: {e}")
            return []
    
    def update_metrics(self, response_time: float, cache_hit: bool = False):
        """更新性能指标"""
        with threading.Lock():
            self.metrics.query_count += 1
            
            if cache_hit:
                self.metrics.cache_hits += 1
            else:
                self.metrics.cache_misses += 1
            
            # 更新平均响应时间（指数移动平均）
            alpha = 0.1  # 平滑因子
            if self.metrics.avg_response_time == 0:
                self.metrics.avg_response_time = response_time
            else:
                self.metrics.avg_response_time = (
                    alpha * response_time + 
                    (1 - alpha) * self.metrics.avg_response_time
                )
            
            # 更新百分位数（简化版本）
            # 在实际应用中应该维护响应时间列表
            if response_time > self.metrics.p95_response_time:
                self.metrics.p95_response_time = response_time * 0.95
            
            if response_time > self.metrics.p99_response_time:
                self.metrics.p99_response_time = response_time * 0.99
            
            self.metrics.last_updated = datetime.now()
    
    def get_metrics(self) -> PerformanceMetrics:
        """获取性能指标"""
        return self.metrics
    
    def reset_metrics(self):
        """重置性能指标"""
        self.metrics = PerformanceMetrics()

class PerformanceOptimizer:
    """性能优化器（主类）"""
    
    def __init__(
        self,
        cache_config: Optional[CacheConfig] = None,
        query_config: Optional[QueryOptimizationConfig] = None
    ):
        self.cache_config = cache_config or CacheConfig()
        self.query_config = query_config or QueryOptimizationConfig()
        
        self.cache_manager = CacheManager(self.cache_config)
        self.query_optimizer = QueryOptimizer(self.query_config)
        self.logger = logging.getLogger(__name__)
    
    def cached_search(
        self,
        storage_client: Any,
        query: str,
        limit: int = 10,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """带缓存的搜索"""
        start_time = time.time()
        
        # 优化查询
        optimized_query = self.query_optimizer.optimize_query(query, kwargs)
        
        # 检查缓存
        cache_key_params = {
            'query': optimized_query,
            'limit': limit,
            **kwargs
        }
        
        cached_results = self.cache_manager.get('search', **cache_key_params)
        
        if cached_results is not None:
            # 缓存命中
            self.query_optimizer.update_metrics(time.time() - start_time, cache_hit=True)
            self.logger.debug(f"Cache hit for query: {optimized_query}")
            return cached_results
        
        # 缓存未命中，执行实际搜索
        try:
            results = storage_client.search(
                query=optimized_query,
                limit=limit,
                **{k: v for k, v in kwargs.items() if k not in ['query', 'limit']}
            )
            
            # 存储到缓存
            self.cache_manager.set('search', results, **cache_key_params)
            
            # 预取相关记忆（异步）
            if self.query_config.enable_prefetch:
                threading.Thread(
                    target=self._async_prefetch,
                    args=(optimized_query, storage_client),
                    daemon=True
                ).start()
            
            response_time = time.time() - start_time
            self.query_optimizer.update_metrics(response_time, cache_hit=False)
            
            return results
        
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            self.query_optimizer.update_metrics(time.time() - start_time, cache_hit=False)
            return []
    
    def _async_prefetch(self, query: str, storage_client: Any):
        """异步预取"""
        try:
            prefetched = self.query_optimizer.prefetch_related(query, storage_client)
            if prefetched:
                # 可以存储预取结果到缓存
                pass
        except Exception as e:
            self.logger.debug(f"Async prefetch failed: {e}")
    
    def batch_cached_search(
        self,
        storage_client: Any,
        queries: List[str],
        limit: int = 10,
        **kwargs
    ) -> List[List[Dict[str, Any]]]:
        """批量带缓存的搜索"""
        if self.query_config.parallel_processing and len(queries) > 1:
            # 并行处理
            return self.query_optimizer.batch_process(
                queries,
                self.cached_search,
                storage_client=storage_client,
                limit=limit,
                **kwargs
            )
        else:
            # 顺序处理
            return [self.cached_search(storage_client, q, limit, **kwargs) for q in