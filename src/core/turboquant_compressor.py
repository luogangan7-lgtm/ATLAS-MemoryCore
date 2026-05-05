"""
分组量化压缩模块 - 向量嵌入的 4-bit 分组量化

对 numpy 数组（embedding vectors）做分组 4-bit 量化：
将每 group_size 个元素量化为 4-bit 整数（0-15），保存每组的
scale 和 zero-point，解压时线性还原。压缩比约 25%（4x），
适合在磁盘/内存中存储大量嵌入向量。

注意：这不能减少发送给 LLM 的 token 数，仅减少向量存储开销。
"""

import numpy as np
from typing import Dict, List, Tuple, Any, Optional
import logging
from dataclasses import dataclass
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class TurboQuantConfig:
    """TurboQuant配置"""
    
    # 压缩参数
    compression_ratio: float = 0.25  # 目标压缩率 (25%保留)
    quantization_bits: int = 4       # 量化位数
    group_size: int = 128            # 分组大小
    prune_threshold: float = 0.01    # 剪枝阈值
    
    # 性能参数
    use_gpu: bool = False
    batch_size: int = 32
    cache_enabled: bool = True
    
    # 质量参数
    preserve_attention_patterns: bool = True
    maintain_relative_magnitudes: bool = True


class TurboQuantCompressor:
    """TurboQuant压缩器"""
    
    def __init__(self, config: Optional[TurboQuantConfig] = None):
        self.config = config or TurboQuantConfig()
        self.cache = {} if self.config.cache_enabled else None
        logger.info(f"TurboQuant压缩器初始化完成，目标压缩率: {self.config.compression_ratio}")
    
    def compress_kv_cache(self, kv_cache: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """
        压缩KV缓存
        
        Args:
            kv_cache: 原始KV缓存字典
            
        Returns:
            压缩后的KV缓存
        """
        if not kv_cache:
            return {}
        
        compressed = {}
        total_original_size = 0
        total_compressed_size = 0
        
        for layer_name, kv_tensor in kv_cache.items():
            # 计算原始大小
            original_size = kv_tensor.size * kv_tensor.itemsize
            total_original_size += original_size
            
            # 应用TurboQuant压缩
            compressed_tensor = self._apply_turboquant(kv_tensor)
            
            # 计算压缩后大小
            compressed_size = compressed_tensor['data'].nbytes
            total_compressed_size += compressed_size
            
            compressed[layer_name] = compressed_tensor
            
            compression_ratio = compressed_size / original_size
            logger.debug(f"层 {layer_name}: {original_size:,}B → {compressed_size:,}B (压缩率: {compression_ratio:.2%})")
        
        overall_ratio = total_compressed_size / total_original_size
        logger.info(f"KV缓存压缩完成: {total_original_size:,}B → {total_compressed_size:,}B (压缩率: {overall_ratio:.2%})")
        
        return compressed
    
    def _apply_turboquant(self, tensor: np.ndarray) -> Dict[str, Any]:
        """应用TurboQuant算法到单个张量"""
        
        # 1. 分组量化
        original_shape = tensor.shape
        flattened = tensor.flatten()
        
        # 2. 分组处理
        groups = []
        quantized_data = []
        scales = []
        zeros = []
        
        for i in range(0, len(flattened), self.config.group_size):
            group = flattened[i:i + self.config.group_size]
            groups.append(group)
            
            # 3. 计算组统计量
            group_min = np.min(group)
            group_max = np.max(group)
            group_range = group_max - group_min
            
            if group_range < 1e-8:
                # 常数组特殊处理
                scale = 1.0
                zero = group_min
                quantized = np.zeros_like(group, dtype=np.uint8)
            else:
                # 4. 量化
                scale = group_range / (2 ** self.config.quantization_bits - 1)
                zero = group_min
                quantized = np.round((group - zero) / scale).astype(np.uint8)
            
            scales.append(scale)
            zeros.append(zero)
            quantized_data.append(quantized)
        
        # 5. 合并结果
        compressed = {
            'original_shape': original_shape,
            'quantized_data': np.concatenate(quantized_data) if quantized_data else np.array([], dtype=np.uint8),
            'scales': np.array(scales, dtype=np.float32),
            'zeros': np.array(zeros, dtype=np.float32),
            'group_size': self.config.group_size,
            'quantization_bits': self.config.quantization_bits,
            'compression_algorithm': 'turboquant_v1'
        }
        
        return compressed
    
    def decompress_kv_cache(self, compressed_cache: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """
        解压缩KV缓存
        
        Args:
            compressed_cache: 压缩的KV缓存
            
        Returns:
            解压缩后的KV缓存
        """
        if not compressed_cache:
            return {}
        
        decompressed = {}
        
        for layer_name, compressed_tensor in compressed_cache.items():
            decompressed_tensor = self._decompress_tensor(compressed_tensor)
            decompressed[layer_name] = decompressed_tensor
        
        logger.info(f"KV缓存解压缩完成，恢复 {len(decompressed)} 层")
        return decompressed
    
    def _decompress_tensor(self, compressed: Dict[str, Any]) -> np.ndarray:
        """解压缩单个张量"""
        
        # 检查缓存
        cache_key = None
        if self.cache is not None:
            cache_key = hashlib.md5(str(compressed).encode()).hexdigest()
            if cache_key in self.cache:
                return self.cache[cache_key]
        
        # 1. 提取压缩数据
        quantized_data = compressed['quantized_data']
        scales = compressed['scales']
        zeros = compressed['zeros']
        group_size = compressed['group_size']
        original_shape = compressed['original_shape']
        
        # 2. 反量化
        total_elements = np.prod(original_shape)
        decompressed = np.zeros(total_elements, dtype=np.float32)
        
        group_idx = 0
        for i in range(0, total_elements, group_size):
            end_idx = min(i + group_size, total_elements)
            group_length = end_idx - i
            
            if group_idx < len(scales):
                scale = scales[group_idx]
                zero = zeros[group_idx]
                
                # 提取当前组的量化数据
                group_quantized = quantized_data[i:i + group_length]
                
                # 反量化
                group_decompressed = group_quantized.astype(np.float32) * scale + zero
                decompressed[i:end_idx] = group_decompressed
                
                group_idx += 1
            else:
                # 处理不完整组
                decompressed[i:end_idx] = zeros[-1] if zeros.size > 0 else 0.0
        
        # 3. 恢复原始形状
        result = decompressed.reshape(original_shape)
        
        # 4. 更新缓存
        if self.cache is not None and cache_key is not None:
            self.cache[cache_key] = result
        
        return result
    
    def compress_context(self, context_text: str, max_tokens: int = 1000) -> str:
        """
        压缩文本上下文
        
        Args:
            context_text: 原始上下文文本
            max_tokens: 目标最大token数
            
        Returns:
            压缩后的文本
        """
        if len(context_text.split()) <= max_tokens:
            return context_text
        
        # 简单实现：提取关键句子
        sentences = context_text.split('. ')
        
        if len(sentences) <= 3:
            # 句子太少，使用摘要方法
            return self._summarize_text(context_text, max_tokens)
        
        # 提取重要句子（基于启发式规则）
        important_sentences = []
        for sentence in sentences:
            if self._is_important_sentence(sentence):
                important_sentences.append(sentence)
        
        # 如果重要句子还是太多，进一步筛选
        if len(' '.join(important_sentences).split()) > max_tokens:
            important_sentences = important_sentences[:max(len(important_sentences) // 2, 3)]
        
        compressed = '. '.join(important_sentences) + '.'
        
        original_tokens = len(context_text.split())
        compressed_tokens = len(compressed.split())
        compression_ratio = compressed_tokens / original_tokens
        
        logger.info(f"上下文压缩: {original_tokens} tokens → {compressed_tokens} tokens (压缩率: {compression_ratio:.2%})")
        
        return compressed
    
    def _is_important_sentence(self, sentence: str) -> bool:
        """判断句子是否重要"""
        sentence_lower = sentence.lower()
        
        # 重要性关键词
        important_keywords = [
            'important', '关键', '必须', '需要', '应该',
            'profit', 'loss', 'trade', '交易', '盈亏',
            'error', 'fix', 'bug', '错误', '修复',
            'decision', '决定', '策略', 'plan', '计划'
        ]
        
        # 检查关键词
        for keyword in important_keywords:
            if keyword in sentence_lower:
                return True
        
        # 检查长度（中等长度的句子通常包含更多信息）
        words = sentence.split()
        return 8 <= len(words) <= 30
    
    def _summarize_text(self, text: str, max_tokens: int) -> str:
        """简单文本摘要"""
        sentences = text.split('. ')
        
        if len(sentences) <= 2:
            return text
        
        # 取开头、中间、结尾各一句
        summary_sentences = []
        if sentences:
            summary_sentences.append(sentences[0])  # 开头
        
        middle_idx = len(sentences) // 2
        if 0 < middle_idx < len(sentences):
            summary_sentences.append(sentences[middle_idx])  # 中间
        
        if len(sentences) > 1:
            summary_sentences.append(sentences[-1])  # 结尾
        
        summary = '. '.join(summary_sentences) + '.'
        
        # 确保不超过最大token数
        while len(summary.split()) > max_tokens and len(summary_sentences) > 1:
            summary_sentences = summary_sentences[:-1]
            summary = '. '.join(summary_sentences) + '.'
        
        return summary
    
    def get_compression_stats(self) -> Dict[str, Any]:
        """获取压缩统计信息"""
        if self.cache is None:
            return {"cache_enabled": False}
        
        return {
            "cache_enabled": True,
            "cache_size": len(self.cache),
            "cache_hits": getattr(self, '_cache_hits', 0),
            "cache_misses": getattr(self, '_cache_misses', 0)
        }


# 全局压缩器实例
_global_compressor = None

def get_global_compressor() -> TurboQuantCompressor:
    """获取全局TurboQuant压缩器实例"""
    global _global_compressor
    if _global_compressor is None:
        _global_compressor = TurboQuantCompressor()
    return _global_compressor