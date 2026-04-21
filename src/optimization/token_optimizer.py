"""
Token优化引擎 - 核心目标：减少云端模型Token消耗
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from .optimized_token_estimator import OptimizedTokenEstimator, EfficientCompressor

logger = logging.getLogger(__name__)


@dataclass
class TokenOptimizationConfig:
    """Token优化配置"""
    max_context_tokens: int = 4000  # 最大上下文Token数
    target_compression_ratio: float = 0.6  # 目标压缩率
    min_relevance_threshold: float = 0.3  # 最小相关性阈值
    deduplication_threshold: float = 0.8  # 去重阈值
    importance_weight: float = 0.7  # 重要性权重
    recency_weight: float = 0.3  # 时间衰减权重


class TokenOptimizer:
    """Token优化引擎"""
    
    def __init__(self, config: Optional[TokenOptimizationConfig] = None):
        self.config = config or TokenOptimizationConfig()
        self.token_estimator = OptimizedTokenEstimator()
        self.compressor = EfficientCompressor(target_compression_ratio=self.config.target_compression_ratio)
        self.optimization_stats = {
            "total_tokens_saved": 0,
            "total_optimizations": 0,
            "average_compression_ratio": 0.0,
            "last_optimization": None
        }
    
    async def optimize_context(self, 
                              query: str,
                              memories: List[Dict[str, Any]],
                              max_tokens: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
        """
        优化上下文 - 核心函数
        返回: (优化后的上下文, 统计信息)
        """
        max_tokens = max_tokens or self.config.max_context_tokens
        
        logger.info(f"开始Token优化: 查询='{query[:50]}...', 记忆数={len(memories)}, 目标Token数={max_tokens}")
        
        # 1. 计算记忆重要性分数
        scored_memories = await self._score_memories(query, memories)
        
        # 2. 智能选择记忆
        selected_memories = await self._select_memories(scored_memories, max_tokens)
        
        # 3. 压缩记忆内容
        compressed_memories = await self._compress_memories(selected_memories)
        
        # 4. 构建优化上下文
        optimized_context = self._build_context(query, compressed_memories)
        
        # 5. 验证Token数量
        token_count = self._estimate_tokens(optimized_context)
        
        # 6. 如果仍然超出限制，进行二次压缩
        if token_count > max_tokens:
            optimized_context = await self._secondary_compression(optimized_context, max_tokens)
            token_count = self._estimate_tokens(optimized_context)
        
        # 7. 更新统计信息
        stats = self._update_stats(memories, compressed_memories, token_count)
        
        logger.info(f"Token优化完成: 原始记忆={len(memories)}, 选择={len(selected_memories)}, "
                   f"压缩={len(compressed_memories)}, 最终Token数={token_count}, "
                   f"节省={stats['tokens_saved']} tokens")
        
        return optimized_context, stats
    
    async def _score_memories(self, query: str, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """计算记忆重要性分数"""
        scored = []
        
        for memory in memories:
            score = await self._calculate_memory_score(memory, query)
            memory["optimization_score"] = score
            scored.append(memory)
        
        # 按分数排序
        scored.sort(key=lambda x: x.get("optimization_score", 0), reverse=True)
        return scored
    
    async def _calculate_memory_score(self, memory: Dict[str, Any], query: str) -> float:
        """计算记忆优化分数"""
        score = 0.0
        
        # 1. 相关性分数
        relevance = memory.get("relevance_score", 0.0)
        if relevance < self.config.min_relevance_threshold:
            return 0.0
        
        score += relevance * 0.4
        
        # 2. 重要性分数
        importance = memory.get("metadata", {}).get("importance", 0.5)
        score += importance * self.config.importance_weight * 0.3
        
        # 3. 时间衰减分数
        recency_score = self._calculate_recency_score(memory)
        score += recency_score * self.config.recency_weight * 0.2
        
        # 4. 使用频率分数
        access_count = memory.get("metadata", {}).get("access_count", 0)
        frequency_score = min(access_count / 10, 1.0)  # 归一化
        score += frequency_score * 0.1
        
        return min(score, 1.0)
    
    def _calculate_recency_score(self, memory: Dict[str, Any]) -> float:
        """计算时间衰减分数"""
        last_accessed_str = memory.get("metadata", {}).get("last_accessed")
        if not last_accessed_str:
            return 0.5
        
        try:
            last_accessed = datetime.fromisoformat(last_accessed_str.replace('Z', '+00:00'))
            now = datetime.now()
            
            # 计算小时差
            hours_diff = (now - last_accessed).total_seconds() / 3600
            
            # 指数衰减: 24小时内为1.0，7天后为0.1
            if hours_diff <= 24:
                return 1.0
            elif hours_diff <= 168:  # 7天
                return 0.5
            else:
                return 0.1
        except:
            return 0.5
    
    async def _select_memories(self, scored_memories: List[Dict[str, Any]], 
                              max_tokens: int) -> List[Dict[str, Any]]:
        """智能选择记忆 - 最大化Token节省"""
        selected = []
        current_tokens = 0
        
        # 极简选择：只选最重要的1-2条记忆
        max_memories = 2
        
        for memory in scored_memories[:max_memories]:  # 只考虑前N条
            memory_text = memory.get("text", "")
            memory_tokens = self._estimate_tokens(memory_text)
            
            # 严格限制：记忆总Token不超过max_tokens的30%
            memory_budget = max_tokens * 0.3
            
            if current_tokens + memory_tokens <= memory_budget:
                selected.append(memory)
                current_tokens += memory_tokens
            else:
                # 如果这条记忆太长，尝试压缩后再检查
                compressed_memory = self.compressor.compress_memory(memory)
                compressed_text = compressed_memory.get("text", "")
                compressed_tokens = self._estimate_tokens(compressed_text)
                
                if current_tokens + compressed_tokens <= memory_budget:
                    selected.append(compressed_memory)
                    current_tokens += compressed_tokens
                else:
                    # 跳过这条记忆
                    continue
        
        return selected
    
    async def _compress_memories(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """压缩记忆内容"""
        compressed = []
        
        for memory in memories:
            compressed_memory = self.compressor.compress_memory(memory)
            compressed.append(compressed_memory)
        
        return compressed
    
    async def _compress_text(self, text: str) -> str:
        """压缩文本"""
        if len(text) <= 200:
            return text
        
        # 1. 移除多余空白
        compressed = re.sub(r'\s+', ' ', text.strip())
        
        # 2. 提取关键句子
        sentences = re.split(r'[.!?。！？]+', compressed)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= 3:
            return compressed[:300] + "..." if len(compressed) > 300 else compressed
        
        # 3. 保留开头、中间关键句、结尾
        selected_sentences = []
        
        # 开头句
        if sentences:
            selected_sentences.append(sentences[0])
        
        # 中间关键句（包含关键词）
        keywords = ["重要", "关键", "必须", "需要", "建议", "注意", "警告", "错误"]
        middle_sentences = sentences[1:-1] if len(sentences) > 2 else []
        
        for sentence in middle_sentences:
            if any(keyword in sentence for keyword in keywords):
                selected_sentences.append(sentence)
                if len(selected_sentences) >= 3:  # 最多3句
                    break
        
        # 如果还不够，添加中间句
        if len(selected_sentences) < 3 and middle_sentences:
            selected_sentences.append(middle_sentences[len(middle_sentences)//2])
        
        # 结尾句
        if len(sentences) > 1:
            selected_sentences.append(sentences[-1])
        
        # 4. 构建压缩文本
        compressed_text = "。".join(selected_sentences) + "。"
        
        # 5. 应用目标压缩率
        target_length = int(len(text) * self.config.target_compression_ratio)
        if target_length < 50:  # 确保最小长度
            target_length = 50
            
        if len(compressed_text) > target_length:
            compressed_text = compressed_text[:target_length] + "..."
        
        return compressed_text
    
    def _build_context(self, query: str, memories: List[Dict[str, Any]]) -> str:
        """构建优化上下文 - 最小化Token版本"""
        
        # 极简上下文构建，最大化Token节省
        context_lines = []
        
        # 1. 极简查询
        context_lines.append(f"Q: {query}")
        
        # 2. 极简记忆
        if memories:
            # 只选择最重要的1-2条记忆
            important_memories = memories[:2]
            
            for i, memory in enumerate(important_memories, 1):
                memory_text = memory.get("text", "")
                # 移除所有元信息，只保留核心内容
                context_lines.append(f"M{i}: {memory_text}")
        
        # 3. 极简指令
        context_lines.append("A:")
        
        return "\n".join(context_lines)
    
    async def _secondary_compression(self, context: str, max_tokens: int) -> str:
        """二次压缩（如果仍然超出限制）"""
        current_tokens = self._estimate_tokens(context)
        
        if current_tokens <= max_tokens:
            return context
        
        # 计算需要压缩的比例
        compression_needed = max_tokens / current_tokens
        
        # 分割上下文
        lines = context.split('\n')
        
        # 保留关键部分
        essential_parts = []
        
        # 总是保留查询
        if lines:
            essential_parts.append(lines[0])
        
        # 选择性保留记忆
        memory_lines = [line for line in lines if line.startswith(('1.', '2.', '3.', '4.', '5.'))]
        
        # 按重要性选择记忆行
        for line in memory_lines[:3]:  # 最多保留3条最重要的记忆
            essential_parts.append(line)
        
        # 添加上下文指令
        essential_parts.append(lines[-1] if lines else "请基于记忆回答查询。")
        
        # 构建压缩上下文
        compressed_context = "\n".join(essential_parts)
        
        # 如果仍然太长，进行文本截断
        if self._estimate_tokens(compressed_context) > max_tokens:
            # 计算需要保留的字符数
            chars_per_token = 4  # 近似值
            max_chars = max_tokens * chars_per_token
            
            compressed_context = compressed_context[:max_chars] + "..."
        
        return compressed_context
    
    def _estimate_tokens(self, text: str) -> int:
        """估算Token数量"""
        return OptimizedTokenEstimator.estimate_tokens(text)
    
    def _content_hash(self, text: str) -> str:
        """生成内容哈希（用于去重）"""
        # 取前100字符 + 长度 + 首尾各10字符
        if len(text) <= 50:
            return text
        
        return f"{text[:50]}_{len(text)}_{text[-20:]}"
    
    def _content_similarity(self, hash1: str, hash2: str) -> float:
        """计算内容相似度（基于哈希）"""
        if hash1 == hash2:
            return 1.0
        
        # 简单相似度计算
        words1 = set(hash1.split('_'))
        words2 = set(hash2.split('_'))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def _update_stats(self, original_memories: List[Dict[str, Any]],
                     compressed_memories: List[Dict[str, Any]],
                     final_token_count: int) -> Dict[str, Any]:
        """更新统计信息"""
        # 计算原始Token数
        original_tokens = 0
        for memory in original_memories:
            original_tokens += self._estimate_tokens(memory.get("text", ""))
        
        # 计算压缩后Token数
        compressed_tokens = 0
        for memory in compressed_memories:
            compressed_tokens += self._estimate_tokens(memory.get("text", ""))
        
        # 计算节省的Token数
        tokens_saved = original_tokens - final_token_count
        
        # 计算压缩率
        compression_ratio = final_token_count / original_tokens if original_tokens > 0 else 1.0
        
        # 更新全局统计
        self.optimization_stats["total_tokens_saved"] += tokens_saved
        self.optimization_stats["total_optimizations"] += 1
        
        # 更新平均压缩率
        current_avg = self.optimization_stats["average_compression_ratio"]
        new_avg = (current_avg * (self.optimization_stats["total_optimizations"] - 1) + compression_ratio) / self.optimization_stats["total_optimizations"]
        self.optimization_stats["average_compression_ratio"] = new_avg
        
        self.optimization_stats["last_optimization"] = datetime.now().isoformat()
        
        return {
            "original_memories": len(original_memories),
            "selected_memories": len(compressed_memories),
            "original_tokens": original_tokens,
            "final_tokens": final_token_count,
            "tokens_saved": tokens_saved,
            "compression_ratio": compression_ratio,
            "optimization_efficiency": tokens_saved / original_tokens if original_tokens > 0 else 0.0
        }
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        return self.optimization_stats.copy()


# 全局实例
_token_optimizer = None

def get_token_optimizer() -> TokenOptimizer:
    """获取Token优化器实例"""
    global _token_optimizer
    if _token_optimizer is None:
        _token_optimizer = TokenOptimizer()
    return _token_optimizer