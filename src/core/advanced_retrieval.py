"""
高级检索功能 - Phase 2 核心模块
实现时间序列分析、情感分析过滤、多维度检索
"""

import logging
import json
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import numpy as np
from enum import Enum

# 尝试导入情感分析库
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    logging.warning("TextBlob not available, sentiment analysis disabled")

class RetrievalMode(Enum):
    """检索模式"""
    SEMANTIC = "semantic"  # 语义检索
    TEMPORAL = "temporal"  # 时间序列
    SENTIMENT = "sentiment"  # 情感过滤
    HYBRID = "hybrid"  # 混合模式
    KEYWORD = "keyword"  # 关键词检索

class TemporalFilter(Enum):
    """时间过滤器"""
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    CUSTOM_RANGE = "custom_range"

@dataclass
class RetrievalConfig:
    """检索配置"""
    mode: RetrievalMode = RetrievalMode.HYBRID
    temporal_filter: Optional[TemporalFilter] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sentiment_threshold: float = 0.0  # 情感阈值 (-1到1)
    min_similarity: float = 0.7  # 最小相似度
    max_results: int = 10
    use_keyword_boost: bool = True
    keyword_boost_factor: float = 1.5
    temporal_decay_factor: float = 0.95  # 时间衰减因子
    hybrid_weights: Dict[str, float] = None  # 混合权重
    
    def __post_init__(self):
        if self.hybrid_weights is None:
            self.hybrid_weights = {
                "semantic": 0.4,
                "temporal": 0.3,
                "sentiment": 0.2,
                "keyword": 0.1
            }

@dataclass
class RetrievalResult:
    """检索结果"""
    memory_id: str
    text: str
    similarity_score: float
    temporal_score: float
    sentiment_score: float
    keyword_score: float
    final_score: float
    metadata: Dict[str, Any]
    timestamp: datetime

class AdvancedRetrieval:
    """高级检索引擎"""
    
    def __init__(self, storage_client: Any, config: Optional[RetrievalConfig] = None):
        self.storage = storage_client
        self.config = config or RetrievalConfig()
        self.logger = logging.getLogger(__name__)
        
    def retrieve(self, query: str, **kwargs) -> List[RetrievalResult]:
        """
        高级检索
        
        Args:
            query: 查询文本
            **kwargs: 覆盖配置参数
            
        Returns:
            List[RetrievalResult]: 检索结果
        """
        # 合并配置
        config = self._merge_config(kwargs)
        
        # 执行检索
        if config.mode == RetrievalMode.SEMANTIC:
            results = self._semantic_retrieval(query, config)
        elif config.mode == RetrievalMode.TEMPORAL:
            results = self._temporal_retrieval(query, config)
        elif config.mode == RetrievalMode.SENTIMENT:
            results = self._sentiment_retrieval(query, config)
        elif config.mode == RetrievalMode.KEYWORD:
            results = self._keyword_retrieval(query, config)
        else:  # HYBRID
            results = self._hybrid_retrieval(query, config)
        
        # 排序并限制结果数量
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results[:config.max_results]
    
    def _semantic_retrieval(self, query: str, config: RetrievalConfig) -> List[RetrievalResult]:
        """语义检索"""
        # 使用存储客户端的语义搜索
        try:
            search_results = self.storage.search(
                query=query,
                limit=config.max_results * 2,  # 获取更多结果用于后续过滤
                score_threshold=config.min_similarity
            )
        except Exception as e:
            self.logger.error(f"Semantic search failed: {e}")
            return []
        
        results = []
        for result in search_results:
            memory_id = result.get('id', '')
            text = result.get('text', '')
            similarity = result.get('score', 0.0)
            metadata = result.get('metadata', {})
            timestamp_str = metadata.get('timestamp', '')
            
            # 解析时间戳
            try:
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
            except:
                timestamp = datetime.now()
            
            # 计算时间分数
            temporal_score = self._calculate_temporal_score(timestamp, config)
            
            # 计算情感分数
            sentiment_score = self._calculate_sentiment_score(text)
            
            # 计算关键词分数
            keyword_score = self._calculate_keyword_score(query, text)
            
            # 最终分数
            final_score = similarity
            
            results.append(RetrievalResult(
                memory_id=memory_id,
                text=text,
                similarity_score=similarity,
                temporal_score=temporal_score,
                sentiment_score=sentiment_score,
                keyword_score=keyword_score,
                final_score=final_score,
                metadata=metadata,
                timestamp=timestamp
            ))
        
        return results
    
    def _temporal_retrieval(self, query: str, config: RetrievalConfig) -> List[RetrievalResult]:
        """时间序列检索"""
        # 首先进行语义检索
        semantic_results = self._semantic_retrieval(query, config)
        
        # 应用时间过滤
        filtered_results = []
        for result in semantic_results:
            # 检查时间过滤器
            if self._apply_temporal_filter(result.timestamp, config):
                # 重新计算分数，强调时间因素
                time_decay = self._calculate_time_decay(result.timestamp)
                temporal_boost = 1.0 / (1.0 + time_decay)
                
                result.temporal_score = temporal_boost
                result.final_score = result.similarity_score * 0.7 + temporal_boost * 0.3
                
                filtered_results.append(result)
        
        return filtered_results
    
    def _sentiment_retrieval(self, query: str, config: RetrievalConfig) -> List[RetrievalResult]:
        """情感分析检索"""
        if not TEXTBLOB_AVAILABLE:
            self.logger.warning("TextBlob not available, falling back to semantic retrieval")
            return self._semantic_retrieval(query, config)
        
        # 首先进行语义检索
        semantic_results = self._semantic_retrieval(query, config)
        
        # 分析查询的情感
        query_sentiment = self._analyze_sentiment(query)
        
        filtered_results = []
        for result in semantic_results:
            # 计算记忆的情感
            memory_sentiment = self._analyze_sentiment(result.text)
            
            # 计算情感相似度
            sentiment_similarity = 1.0 - abs(query_sentiment - memory_sentiment) / 2.0
            
            # 应用情感阈值
            if sentiment_similarity >= config.sentiment_threshold:
                result.sentiment_score = sentiment_similarity
                result.final_score = result.similarity_score * 0.6 + sentiment_similarity * 0.4
                
                filtered_results.append(result)
        
        return filtered_results
    
    def _keyword_retrieval(self, query: str, config: RetrievalConfig) -> List[RetrievalResult]:
        """关键词检索"""
        # 提取查询关键词
        query_keywords = self._extract_keywords(query)
        
        # 首先进行语义检索
        semantic_results = self._semantic_retrieval(query, config)
        
        boosted_results = []
        for result in semantic_results:
            # 提取记忆关键词
            memory_keywords = self._extract_keywords(result.text)
            
            # 计算关键词匹配度
            if query_keywords and memory_keywords:
                common_keywords = set(query_keywords).intersection(set(memory_keywords))
                keyword_score = len(common_keywords) / len(query_keywords)
            else:
                keyword_score = 0.0
            
            # 应用关键词增强
            if config.use_keyword_boost and keyword_score > 0:
                boost = 1.0 + (keyword_score * config.keyword_boost_factor)
                final_score = result.similarity_score * boost
            else:
                final_score = result.similarity_score
            
            result.keyword_score = keyword_score
            result.final_score = final_score
            
            boosted_results.append(result)
        
        return boosted_results
    
    def _hybrid_retrieval(self, query: str, config: RetrievalConfig) -> List[RetrievalResult]:
        """混合检索"""
        # 获取各种检索模式的结果
        semantic_results = self._semantic_retrieval(query, config)
        
        results = []
        for result in semantic_results:
            # 计算各维度分数
            temporal_score = self._calculate_temporal_score(result.timestamp, config)
            sentiment_score = self._calculate_sentiment_score(result.text)
            keyword_score = self._calculate_keyword_score(query, result.text)
            
            # 应用混合权重
            weights = config.hybrid_weights
            final_score = (
                result.similarity_score * weights.get("semantic", 0.4) +
                temporal_score * weights.get("temporal", 0.3) +
                sentiment_score * weights.get("sentiment", 0.2) +
                keyword_score * weights.get("keyword", 0.1)
            )
            
            result.temporal_score = temporal_score
            result.sentiment_score = sentiment_score
            result.keyword_score = keyword_score
            result.final_score = final_score
            
            results.append(result)
        
        return results
    
    def _calculate_temporal_score(self, timestamp: datetime, config: RetrievalConfig) -> float:
        """计算时间分数"""
        if config.temporal_filter:
            # 检查是否在时间过滤范围内
            if not self._apply_temporal_filter(timestamp, config):
                return 0.0
        
        # 计算时间衰减
        time_decay = self._calculate_time_decay(timestamp)
        temporal_score = 1.0 / (1.0 + time_decay)
        
        return temporal_score
    
    def _calculate_time_decay(self, timestamp: datetime) -> float:
        """计算时间衰减"""
        now = datetime.now()
        time_diff = now - timestamp
        
        # 以天为单位计算衰减
        days_diff = time_diff.total_seconds() / (24 * 3600)
        
        # 指数衰减
        decay = np.exp(-self.config.temporal_decay_factor * days_diff)
        
        return 1.0 - decay
    
    def _apply_temporal_filter(self, timestamp: datetime, config: RetrievalConfig) -> bool:
        """应用时间过滤器"""
        if not config.temporal_filter:
            return True
        
        now = datetime.now()
        
        if config.temporal_filter == TemporalFilter.TODAY:
            return timestamp.date() == now.date()
        elif config.temporal_filter == TemporalFilter.YESTERDAY:
            yesterday = now - timedelta(days=1)
            return timestamp.date() == yesterday.date()
        elif config.temporal_filter == TemporalFilter.THIS_WEEK:
            start_of_week = now - timedelta(days=now.weekday())
            return timestamp >= start_of_week
        elif config.temporal_filter == TemporalFilter.LAST_WEEK:
            start_of_last_week = now - timedelta(days=now.weekday() + 7)
            end_of_last_week = start_of_last_week + timedelta(days=6)
            return start_of_last_week <= timestamp <= end_of_last_week
        elif config.temporal_filter == TemporalFilter.THIS_MONTH:
            start_of_month = datetime(now.year, now.month, 1)
            return timestamp >= start_of_month
        elif config.temporal_filter == TemporalFilter.LAST_MONTH:
            if now.month == 1:
                last_month = 12
                last_year = now.year - 1
            else:
                last_month = now.month - 1
                last_year = now.year
            start_of_last_month = datetime(last_year, last_month, 1)
            end_of_last_month = datetime(now.year, now.month, 1) - timedelta(days=1)
            return start_of_last_month <= timestamp <= end_of_last_month
        elif config.temporal_filter == TemporalFilter.CUSTOM_RANGE:
            if config.start_date and config.end_date:
                return config.start_date <= timestamp <= config.end_date
        
        return True
    
    def _calculate_sentiment_score(self, text: str) -> float:
        """计算情感分数"""
        if not TEXTBLOB_AVAILABLE or not text:
            return 0.5  # 中性分数
        
        try:
            sentiment = self._analyze_sentiment(text)
            # 将-1到1的范围映射到0到1
            normalized_score = (sentiment + 1) / 2
            return normalized_score
        except:
            return 0.5
    
    def _analyze_sentiment(self, text: str) -> float:
        """分析文本情感"""
        if not TEXTBLOB_AVAILABLE:
            return 0.0
        
        blob = TextBlob(text)
        return blob.sentiment.polarity  # -1到1
    
    def _calculate_keyword_score(self, query: str, text: str) -> float:
        """计算关键词分数"""
        query_keywords = self._extract_keywords(query)
        text_keywords = self._extract_keywords(text)
        
        if not query_keywords or not text_keywords:
            return 0.0
        
        common_keywords = set(query_keywords).intersection(set(text_keywords))
        score = len(common_keywords) / len(query_keywords)
        
        return min(score, 1.0)
    
    def _extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """提取关键词"""
        if not text:
            return []
        
        # 简单的关键词提取（在实际应用中可以使用更复杂的算法）
        words = text.lower().split()
        
        # 过滤停用词和短词
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        keywords = [word for word in words if len(word) > 3 and word not in stop_words]
        
        # 去重并限制数量
        unique_keywords = list(dict.fromkeys(keywords))
        return unique_keywords[:max_keywords]
    
    def _merge_config(self, kwargs: Dict) -> RetrievalConfig:
        """合并配置参数"""
        config_dict = asdict(self.config)
        
        for key, value in kwargs.items():
            if key in config_dict:
                if key == 'mode' and isinstance(value, str):
                    config_dict[key] = RetrievalMode(value)
                elif key == 'temporal_filter' and isinstance(value, str):
                    config_dict[key] = TemporalFilter(value)
                else:
                    config_dict[key] = value
        
        return RetrievalConfig(**config_dict)
    
    def get_temporal_analysis(self, days: int = 30) -> Dict[str, Any]:
        """
        获取时间序列分析
        
        Args:
            days: 分析的天数
            
        Returns:
            时间序列分析结果
        """
        try:
            # 获取最近的所有记忆
            all_memories = self.storage.get_all_memories(limit=1000)
            
            # 按天分组
            daily_counts = {}
            for memory in all_memories:
                metadata = memory.get('metadata', {})
                timestamp_str = metadata.get('timestamp', '')
                
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    date_key = timestamp.date().isoformat()
                    daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
                except:
                    continue
            
            # 排序并限制天数
            sorted_dates = sorted(daily_counts.keys(), reverse=True)[:days]
            
            return {
                "daily_counts": {date: daily_counts[date] for date in sorted_dates},
                "total_memories": len(all_memories),
                "analysis_period_days": days,
                "average_per_day": len(all_memories) / days if days > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Temporal analysis failed: {e}")
            return {
                "daily_counts": {},
                "total_memories": 0,
                "analysis_period_days": days,
                "average_per_day": 0
            }
    
    def get_sentiment_analysis(self) -> Dict[str, Any]:
        """
        获取情感分析统计
        
        Returns:
            情感分析结果
        """
        if not TEXTBLOB_AVAILABLE:
            return {"available": False, "message": "TextBlob not installed"}
        
        try:
            all_memories = self.storage.get_all_memories(limit=500)
            
            sentiments = []
            for memory in all_memories:
                text = memory.get('text', '')
                if text:
                    sentiment = self._analyze_sentiment(text)
                    sentiments.append(sentiment)
            
            if not sentiments:
                return {
                    "available": True,
                    "total_analyzed": 0,
                    "average_sentiment