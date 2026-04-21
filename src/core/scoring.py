"""
评分模块 - Scoring Module
实现记忆重要性评分和优化算法
Implements memory importance scoring and optimization algorithms
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

from .storage import MemoryRecord, MemoryMetadata, MemoryCategory
from .config import get_config, OptimizationConfig

logger = logging.getLogger(__name__)


@dataclass
class ScoreFactors:
    """评分因子 - Score Factors"""
    base_importance: float  # 基础重要性 (0-1)
    time_decay: float       # 时间衰减因子 (0-1)
    usage_frequency: float  # 使用频率因子 (0-1)
    outcome_value: float    # 结果价值因子 (0-1)
    semantic_richness: float  # 语义丰富度 (0-1)
    
    def calculate_total(self, weights: Dict[str, float]) -> float:
        """计算总分 - Calculate total score"""
        total = 0.0
        total += self.base_importance * weights.get("base_importance", 0.3)
        total += self.time_decay * weights.get("time_decay", 0.2)
        total += self.usage_frequency * weights.get("usage_frequency", 0.2)
        total += self.outcome_value * weights.get("outcome_value", 0.2)
        total += self.semantic_richness * weights.get("semantic_richness", 0.1)
        
        # 确保在0-1范围内
        return max(0.0, min(1.0, total))


class MemoryScoring:
    """记忆评分器 - Memory Scorer"""
    
    def __init__(self, config: Optional[OptimizationConfig] = None):
        self.config = config or get_config().optimization
        
        # 评分权重配置
        self.score_weights = {
            "base_importance": 0.3,
            "time_decay": 0.2,
            "usage_frequency": 0.2,
            "outcome_value": 0.2,
            "semantic_richness": 0.1,
        }
        
        # 分类特定权重
        self.category_weights = {
            MemoryCategory.TRADING: {
                "base_importance": 0.4,  # 交易记忆更重要
                "outcome_value": 0.3,    # 结果价值权重更高
            },
            MemoryCategory.LEARNING: {
                "semantic_richness": 0.2,  # 学习内容语义更丰富
            },
            MemoryCategory.CODE: {
                "base_importance": 0.35,
                "usage_frequency": 0.25,  # 代码片段使用频繁
            },
        }
        
        logger.info("记忆评分器初始化完成")
    
    def calculate_score(self, memory: MemoryRecord) -> float:
        """
        计算记忆总分 - Calculate total memory score
        
        Args:
            memory: 记忆记录 - Memory record
            
        Returns:
            总分 (0-1) - Total score (0-1)
        """
        try:
            # 计算各个因子
            factors = self._calculate_factors(memory)
            
            # 获取分类特定权重
            weights = self._get_weights_for_category(memory.metadata.category)
            
            # 计算总分
            total_score = factors.calculate_total(weights)
            
            logger.debug(f"记忆评分: ID={memory.id[:8]}, 分数={total_score:.3f}")
            return total_score
        
        except Exception as e:
            logger.error(f"计算评分失败: {e}")
            return memory.metadata.importance  # 返回基础重要性作为后备
    
    def _calculate_factors(self, memory: MemoryRecord) -> ScoreFactors:
        """计算各个评分因子 - Calculate score factors"""
        return ScoreFactors(
            base_importance=self._calculate_base_importance(memory),
            time_decay=self._calculate_time_decay(memory),
            usage_frequency=self._calculate_usage_frequency(memory),
            outcome_value=self._calculate_outcome_value(memory),
            semantic_richness=self._calculate_semantic_richness(memory),
        )
    
    def _calculate_base_importance(self, memory: MemoryRecord) -> float:
        """计算基础重要性 - Calculate base importance"""
        # 使用元数据中的重要性，但可以基于其他因素调整
        base_score = memory.metadata.importance
        
        # 基于分类调整
        category_boost = self._get_category_boost(memory.metadata.category)
        base_score = min(1.0, base_score * (1 + category_boost))
        
        # 基于标签调整（如果有重要标签）
        tag_boost = self._get_tag_boost(memory.metadata.tags)
        base_score = min(1.0, base_score * (1 + tag_boost))
        
        return base_score
    
    def _calculate_time_decay(self, memory: MemoryRecord) -> float:
        """计算时间衰减因子 - Calculate time decay factor"""
        # 使用艾宾浩斯遗忘曲线
        age_days = (datetime.now() - memory.created_at).days
        
        # 衰减公式: decay = e^(-age/half_life)
        half_life = self.config.importance_decay_days
        decay = math.exp(-age_days / half_life)
        
        # 如果最近访问过，衰减减缓
        if memory.last_accessed:
            days_since_access = (datetime.now() - memory.last_accessed).days
            if days_since_access < 7:  # 一周内访问过
                access_boost = 1 - (days_since_access / 7)
                decay = min(1.0, decay * (1 + access_boost * 0.5))
        
        return decay
    
    def _calculate_usage_frequency(self, memory: MemoryRecord) -> float:
        """计算使用频率因子 - Calculate usage frequency factor"""
        if memory.access_count == 0:
            return 0.1  # 最低频率
        
        # 标准化访问次数 (0-1)
        # 使用对数缩放，避免高频记忆主导
        normalized = min(1.0, math.log10(memory.access_count + 1) / 2)
        
        # 考虑访问模式（最近访问更频繁）
        recency_boost = 0.0
        if memory.last_accessed:
            days_since_access = (datetime.now() - memory.last_accessed).days
            if days_since_access < 30:  # 一个月内
                recency_boost = 1 - (days_since_access / 30)
        
        return min(1.0, normalized * (1 + recency_boost * 0.3))
    
    def _calculate_outcome_value(self, memory: MemoryRecord) -> float:
        """计算结果价值因子 - Calculate outcome value factor"""
        # 默认值
        outcome_value = 0.5
        
        # 检查记忆文本中是否包含结果信息
        text = memory.text.lower()
        
        # 成功/积极结果
        success_keywords = ["成功", "完成", "解决", "盈利", "正确", "有效", "good", "success", "profit"]
        for keyword in success_keywords:
            if keyword in text:
                outcome_value = min(1.0, outcome_value + 0.2)
                break
        
        # 失败/消极结果
        failure_keywords = ["失败", "错误", "亏损", "问题", "bug", "error", "fail", "loss"]
        for keyword in failure_keywords:
            if keyword in text:
                outcome_value = max(0.0, outcome_value - 0.1)  # 失败也有学习价值
                break
        
        # 学习/改进结果
        learning_keywords = ["学习", "改进", "优化", "经验", "教训", "learn", "improve", "optimize"]
        for keyword in learning_keywords:
            if keyword in text:
                outcome_value = min(1.0, outcome_value + 0.15)
                break
        
        return outcome_value
    
    def _calculate_semantic_richness(self, memory: MemoryRecord) -> float:
        """计算语义丰富度 - Calculate semantic richness"""
        text = memory.text
        
        # 基于文本长度（适中的长度最好）
        length_score = min(1.0, len(text) / 500)  # 500字符为理想长度
        
        # 基于词汇多样性（简单估算）
        words = text.split()
        unique_words = set(words)
        if len(words) > 0:
            diversity_score = len(unique_words) / len(words)
        else:
            diversity_score = 0.5
        
        # 基于句子结构（简单估算）
        sentences = text.split('。') + text.split('.')
        sentence_count = len([s for s in sentences if len(s.strip()) > 5])
        structure_score = min(1.0, sentence_count / 5)  # 5个句子为理想数量
        
        # 综合分数
        richness = (length_score * 0.4 + diversity_score * 0.3 + structure_score * 0.3)
        
        return richness
    
    def _get_category_boost(self, category: MemoryCategory) -> float:
        """获取分类提升系数 - Get category boost coefficient"""
        boosts = {
            MemoryCategory.TRADING: 0.3,    # 交易记忆 +30%
            MemoryCategory.CODE: 0.2,       # 代码记忆 +20%
            MemoryCategory.PROJECT: 0.15,   # 项目记忆 +15%
            MemoryCategory.LEARNING: 0.1,   # 学习记忆 +10%
            MemoryCategory.WORK: 0.1,       # 工作记忆 +10%
            MemoryCategory.PERSONAL: 0.05,  # 个人记忆 +5%
            MemoryCategory.OTHER: 0.0,      # 其他记忆 无提升
        }
        
        return boosts.get(category, 0.0)
    
    def _get_tag_boost(self, tags: List[str]) -> float:
        """获取标签提升系数 - Get tag boost coefficient"""
        if not tags:
            return 0.0
        
        important_tags = {
            "important": 0.2,
            "critical": 0.3,
            "urgent": 0.25,
            "key": 0.15,
            "essential": 0.2,
            "priority": 0.15,
        }
        
        boost = 0.0
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower in important_tags:
                boost = max(boost, important_tags[tag_lower])
        
        return boost
    
    def _get_weights_for_category(self, category: MemoryCategory) -> Dict[str, float]:
        """获取分类特定权重 - Get category-specific weights"""
        # 基础权重
        weights = self.score_weights.copy()
        
        # 应用分类特定权重
        if category in self.category_weights:
            category_weights = self.category_weights[category]
            for key, value in category_weights.items():
                if key in weights:
                    weights[key] = value
        
        # 确保权重总和为1
        total = sum(weights.values())
        if total != 1.0:
            for key in weights:
                weights[key] /= total
        
        return weights
    
    def batch_score_memories(self, memories: List[MemoryRecord]) -> List[Tuple[str, float]]:
        """批量评分记忆 - Batch score memories"""
        results = []
        
        for memory in memories:
            score = self.calculate_score(memory)
            results.append((memory.id, score))
        
        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"批量评分完成: {len(results)} 条记忆")
        return results
    
    def identify_memories_for_promotion(self, memories: List[MemoryRecord]) -> List[MemoryRecord]:
        """识别需要升级的记忆 - Identify memories for promotion"""
        promotion_threshold = self.config.max_score_to_promote
        
        candidates = []
        for memory in memories:
            score = self.calculate_score(memory)
            if score >= promotion_threshold:
                candidates.append(memory)
        
        logger.info(f"识别到 {len(candidates)} 条需要升级的记忆")
        return candidates
    
    def identify_memories_for_cleanup(self, memories: List[MemoryRecord]) -> List[MemoryRecord]:
        """识别需要清理的记忆 - Identify memories for cleanup"""
        cleanup_threshold = self.config.min_score_to_keep
        max_age_days = self.config.cleanup_age_days
        
        candidates = []
        current_time = datetime.now()
        
        for memory in memories:
            score = self.calculate_score(memory)
            age_days = (current_time - memory.created_at).days
            
            if score < cleanup_threshold and age_days > max_age_days:
                candidates.append(memory)
        
        logger.info(f"识别到 {len(candidates)} 条需要清理的记忆")
        return candidates
    
    def analyze_memory_patterns(self, memories: List[MemoryRecord]) -> Dict[str, Any]:
        """分析记忆模式 - Analyze memory patterns"""
        if not memories:
            return {}
        
        # 按分类统计
        category_stats = {}
        for memory in memories:
            category = memory.metadata.category.value
            if category not in category_stats:
                category_stats[category] = {
                    "count": 0,
                    "avg_importance": 0,
                    "avg_score": 0,
                }
            
            stats = category_stats[category]
            stats["count"] += 1
            stats["avg_importance"] += memory.metadata.importance
            stats["avg_score"] += self.calculate_score(memory)
        
        # 计算平均值
        for stats in category_stats.values():
            if stats["count"] > 0:
                stats["avg_importance"] /= stats["count"]
                stats["avg_score"] /= stats["count"]
        
        # 总体统计
        total_count = len(memories)
        avg_importance = sum(m.metadata.importance for m in memories) / total_count
        avg_score = sum(self.calculate_score(m) for m in memories) / total_count
        
        return {
            "total_memories": total_count,
            "average_importance": avg_importance,
            "average_score": avg_score,
            "category_stats": category_stats,
            "analysis_time": datetime.now().isoformat(),
        }


class ScoreOptimizer:
    """评分优化器 - Score Optimizer"""
    
    def __init__(self, scoring: MemoryScoring):
        self.scoring = scoring
        self.config = scoring.config
        
        # 优化历史
        self.optimization_history: List[Dict[str, Any]] = []
        
        logger.info("评分优化器初始化完成")
    
    def optimize_memory_scores(self, memories: List[MemoryRecord]) -> List[Tuple[str, float, float]]:
        """
        优化记忆分数 - Optimize memory scores
        
        Args:
            memories: 记忆列表 - List of memories
            
        Returns:
            (记忆ID, 旧分数, 新分数) 列表 - List of (memory_id, old_score, new_score)
        """
        results = []
        
        for memory in memories:
            old_score = memory.score
            new_score = self.scoring.calculate_score(memory)
            
            results.append((memory.id, old_score, new_score))
        
        # 记录优化历史
        self._record_optimization(results)
        
        logger.info(f"分数优化完成: {len(results)} 条记忆")
        return results
    
    def _record_optimization(self, results: List[Tuple[str, float, float]]):
        """记录优化历史 - Record optimization history"""
        if not results:
            return
        
        # 计算统计信息
        old_scores = [old for _, old, _ in results]
        new_scores = [new for _, _, new in results]
        
        stats = {
            "timestamp": datetime.now().isoformat(),
            "total_memories": len(results),
            "avg_old_score": np.mean(old_scores) if old_scores else 0,
            "avg_new_score": np.mean(new_scores) if new_scores else 0,
            "max_improvement": max(new - old for _, old, new in results) if results else 0,
            "min_improvement": min(new - old for _, old, new in results) if results else 0,
        }
        
        self.optimization_history.append(stats)
        
        # 保持历史记录大小
        if len(self.optimization_history) > 100:
            self.optimization_history = self.optimization_history[-100:]
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计 - Get optimization statistics"""
        if not self.optimization_history:
            return {"message": "无优化历史"}
        
        latest = self.optimization_history[-1]
        
        return {
            "latest_optimization": latest,
            "total_optimizations": len(self.optimization_history),
            "history_available": len(self.optimization_history),
        }
    
    def suggest_optimization_parameters(self) -> Dict[str, Any]:
        """建议优化参数 - Suggest optimization parameters"""
        # 基于历史数据调整权重
        suggestions = {}
        
        if len(self.optimization_history) >= 5:
            # 分析历史趋势
            recent_improvements = [
                h["avg_new_score"] - h["avg_old_score"]
                for h in self.optimization_history[-5:]
            ]
            
            avg_improvement = np.mean(recent_improvements)
            
            if avg_improvement < 0.01:  # 改进很小
                suggestions["adjust_weights"] = "考虑调整评分权重"
                suggestions["increase_time_decay_weight"] = 0.25  # 增加时间衰减权重
                suggestions["decrease_base_importance_weight"] = 0.25  # 减少基础重要性权重
        
        return suggestions


# 工具函数 - Utility functions
def create_scoring_system(config_path: Optional[str] = None) -> MemoryScoring:
    """创建评分系统 - Create scoring system"""
    from .config import get_config_manager
    
    config_manager = get_config_manager(config_path)
    scoring = MemorySc