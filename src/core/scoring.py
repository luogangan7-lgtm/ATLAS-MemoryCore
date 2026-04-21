"""
记忆评分引擎 - 基于艾宾浩斯遗忘曲线的智能评分系统
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)


@dataclass
class ScoringConfig:
    """评分配置"""
    # 基础权重
    relevance_weight: float = 0.3
    recency_weight: float = 0.25
    frequency_weight: float = 0.2
    outcome_weight: float = 0.15
    complexity_weight: float = 0.1
    
    # 时间衰减参数 (艾宾浩斯曲线)
    half_life_days: float = 1.0  # 半衰期1天
    decay_rate: float = 0.5
    
    # 阈值
    upgrade_threshold: float = 0.85  # 升级到QMD的阈值
    forget_threshold: float = 0.3    # 遗忘阈值
    high_importance_threshold: float = 0.7
    
    # 关键词权重
    keyword_weights: Dict[str, float] = None
    
    def __post_init__(self):
        if self.keyword_weights is None:
            self.keyword_weights = {
                "profit": 0.3,
                "loss": 0.3,
                "trade": 0.25,
                "error": 0.2,
                "fix": 0.2,
                "learn": 0.15,
                "important": 0.25,
                "urgent": 0.3,
                "decision": 0.2,
                "strategy": 0.2,
                "code": 0.15,
                "api": 0.15,
                "security": 0.25,
                "password": 0.3,
                "token": 0.3,
            }


class MemoryScoringEngine:
    """记忆评分引擎"""
    
    def __init__(self, config: Optional[ScoringConfig] = None):
        self.config = config or ScoringConfig()
    
    def calculate_score(self, memory_data: Dict[str, Any]) -> float:
        """
        计算记忆综合评分
        
        Args:
            memory_data: 记忆数据，包含文本、元数据、使用历史
            
        Returns:
            综合评分 (0.0-1.0)
        """
        try:
            text = memory_data.get("text", "")
            metadata = memory_data.get("metadata", {})
            usage_history = memory_data.get("usage_history", [])
            
            # 1. 相关性评分
            relevance_score = self._calculate_relevance_score(text, metadata)
            
            # 2. 时间衰减评分
            recency_score = self._calculate_recency_score(metadata, usage_history)
            
            # 3. 使用频率评分
            frequency_score = self._calculate_frequency_score(usage_history)
            
            # 4. 结果价值评分
            outcome_score = self._calculate_outcome_score(metadata)
            
            # 5. 复杂度评分
            complexity_score = self._calculate_complexity_score(text)
            
            # 加权综合评分
            total_score = (
                relevance_score * self.config.relevance_weight +
                recency_score * self.config.recency_weight +
                frequency_score * self.config.frequency_weight +
                outcome_score * self.config.outcome_weight +
                complexity_score * self.config.complexity_weight
            )
            
            # 应用时间衰减
            if "created_at" in metadata:
                age_days = self._get_age_in_days(metadata["created_at"])
                decay_factor = self._calculate_decay_factor(age_days)
                total_score *= decay_factor
            
            return min(max(total_score, 0.0), 1.0)
            
        except Exception as e:
            logger.error(f"评分计算失败: {e}")
            return 0.5  # 默认中等评分
    
    def _calculate_relevance_score(self, text: str, metadata: Dict[str, Any]) -> float:
        """计算相关性评分"""
        score = 0.5  # 基础分
        
        # 关键词匹配
        text_lower = text.lower()
        for keyword, weight in self.config.keyword_weights.items():
            if keyword in text_lower:
                score += weight
        
        # 类别权重
        category = metadata.get("category", "")
        if category in ["trading", "security", "code"]:
            score += 0.1
        elif category in ["learning", "project"]:
            score += 0.05
        
        # 长度权重 (适中的长度更有价值)
        text_length = len(text)
        if 50 <= text_length <= 500:
            score += 0.1
        elif text_length > 500:
            score += 0.05
        
        return min(max(score, 0.0), 1.0)
    
    def _calculate_recency_score(self, metadata: Dict[str, Any], 
                                usage_history: List[Dict[str, Any]]) -> float:
        """计算时间衰减评分"""
        if not usage_history:
            return 0.5
        
        # 获取最近使用时间
        latest_use = None
        for usage in usage_history:
            use_time = usage.get("timestamp")
            if use_time:
                if latest_use is None or use_time > latest_use:
                    latest_use = use_time
        
        if latest_use:
            age_days = self._get_age_in_days(latest_use)
            decay = self._calculate_decay_factor(age_days)
            return decay
        
        return 0.5
    
    def _calculate_frequency_score(self, usage_history: List[Dict[str, Any]]) -> float:
        """计算使用频率评分"""
        if not usage_history:
            return 0.3
        
        # 最近7天的使用次数
        week_ago = datetime.now() - timedelta(days=7)
        recent_uses = 0
        
        for usage in usage_history:
            use_time = usage.get("timestamp")
            if use_time and use_time >= week_ago:
                recent_uses += 1
        
        # 归一化到0-1
        if recent_uses == 0:
            return 0.3
        elif recent_uses <= 3:
            return 0.5
        elif recent_uses <= 10:
            return 0.7
        else:
            return 0.9
    
    def _calculate_outcome_score(self, metadata: Dict[str, Any]) -> float:
        """计算结果价值评分"""
        score = 0.5
        
        # 结果标记
        outcome = metadata.get("outcome", "")
        if outcome == "success":
            score += 0.2
        elif outcome == "failure":
            score += 0.1  # 失败也有学习价值
        
        # 重要性标记
        importance = metadata.get("importance", 0.5)
        score += (importance - 0.5) * 0.3
        
        return min(max(score, 0.0), 1.0)
    
    def _calculate_complexity_score(self, text: str) -> float:
        """计算复杂度评分"""
        # 简单启发式：代码、技术内容更有价值
        score = 0.5
        
        # 检测代码片段
        code_patterns = [
            r"def\s+\w+\s*\(",
            r"class\s+\w+",
            r"import\s+\w+",
            r"from\s+\w+\s+import",
            r"\w+\.\w+\s*=",
            r"if\s+.*:",
            r"for\s+.*:",
            r"while\s+.*:",
            r"try:",
            r"except\s+.*:",
        ]
        
        for pattern in code_patterns:
            if re.search(pattern, text):
                score += 0.1
        
        # 检测技术术语
        tech_terms = ["api", "endpoint", "database", "server", "client", 
                     "protocol", "algorithm", "architecture", "framework"]
        
        for term in tech_terms:
            if term in text.lower():
                score += 0.05
        
        return min(max(score, 0.0), 1.0)
    
    def _get_age_in_days(self, timestamp: str) -> float:
        """计算时间差（天）"""
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                dt = timestamp
            
            age = datetime.now() - dt
            return age.total_seconds() / (24 * 3600)
        except:
            return 7.0  # 默认一周
    
    def _calculate_decay_factor(self, age_days: float) -> float:
        """计算时间衰减因子（艾宾浩斯曲线）"""
        # 指数衰减: decay = base^(age/half_life)
        decay = math.pow(self.config.decay_rate, age_days / self.config.half_life_days)
        return max(decay, 0.1)  # 最低保留10%
    
    def should_upgrade_to_qmd(self, score: float) -> bool:
        """判断是否应该升级到QMD"""
        return score >= self.config.upgrade_threshold
    
    def should_forget(self, score: float) -> bool:
        """判断是否应该遗忘"""
        return score <= self.config.forget_threshold
    
    def is_high_importance(self, score: float) -> bool:
        """判断是否为高重要性记忆"""
        return score >= self.config.high_importance_threshold


def get_default_scoring_engine() -> MemoryScoringEngine:
    """获取默认评分引擎"""
    return MemoryScoringEngine()