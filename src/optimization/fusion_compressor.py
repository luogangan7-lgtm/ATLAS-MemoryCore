"""
融合压缩引擎 - Phase 2 核心模块
集成Qwen2.5-7B进行本地压缩，实现智能记忆压缩和摘要生成
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import numpy as np
from datetime import datetime, timedelta

# 尝试导入本地LLM
try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
    from transformers import BitsAndBytesConfig
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("Transformers not available, using fallback compression")

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logging.warning("PyTorch not available, using fallback compression")

@dataclass
class CompressionConfig:
    """压缩配置"""
    model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    use_4bit: bool = True
    max_length: int = 2048
    temperature: float = 0.3
    top_p: float = 0.9
    repetition_penalty: float = 1.1
    compression_ratio: float = 0.3  # 目标压缩比例
    min_compression_score: float = 0.7  # 最小压缩质量分数
    batch_size: int = 4
    device: str = "auto"
    
@dataclass
class CompressionResult:
    """压缩结果"""
    original_text: str
    compressed_text: str
    compression_ratio: float
    quality_score: float
    keywords: List[str]
    summary: str
    metadata: Dict[str, Any]
    timestamp: datetime

class FusionCompressor:
    """融合压缩引擎"""
    
    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        self.logger = logging.getLogger(__name__)
        self.model = None
        self.tokenizer = None
        self.pipeline = None
        self._initialize_model()
        
    def _initialize_model(self):
        """初始化压缩模型"""
        try:
            if not TRANSFORMERS_AVAILABLE or not TORCH_AVAILABLE:
                self.logger.warning("Using fallback compression (no LLM)")
                return
                
            self.logger.info(f"Loading compression model: {self.config.model_name}")
            
            # 配置量化
            quantization_config = None
            if self.config.use_4bit and TORCH_AVAILABLE:
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4"
                )
            
            # 加载tokenizer和模型
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name,
                trust_remote_code=True
            )
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.config.model_name,
                quantization_config=quantization_config,
                device_map=self.config.device,
                trust_remote_code=True
            )
            
            # 创建文本生成pipeline
            self.pipeline = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                max_length=self.config.max_length,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                repetition_penalty=self.config.repetition_penalty,
                device_map=self.config.device
            )
            
            self.logger.info("Compression model loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to load compression model: {e}")
            self.model = None
            self.pipeline = None
            
    def compress_memory(self, memory_text: str, metadata: Optional[Dict] = None) -> CompressionResult:
        """
        压缩记忆文本
        
        Args:
            memory_text: 原始记忆文本
            metadata: 附加元数据
            
        Returns:
            CompressionResult: 压缩结果
        """
        metadata = metadata or {}
        
        # 如果模型不可用，使用回退压缩
        if self.pipeline is None:
            return self._fallback_compress(memory_text, metadata)
        
        try:
            # 生成压缩提示
            prompt = self._create_compression_prompt(memory_text)
            
            # 生成压缩文本
            compressed_result = self.pipeline(
                prompt,
                max_new_tokens=512,
                do_sample=True,
                num_return_sequences=1
            )[0]['generated_text']
            
            # 提取压缩后的内容
            compressed_text = self._extract_compressed_text(compressed_result, prompt)
            
            # 计算压缩比例和质量分数
            compression_ratio = len(compressed_text) / len(memory_text) if memory_text else 1.0
            quality_score = self._calculate_quality_score(memory_text, compressed_text)
            
            # 提取关键词和摘要
            keywords = self._extract_keywords(compressed_text)
            summary = self._generate_summary(compressed_text)
            
            return CompressionResult(
                original_text=memory_text,
                compressed_text=compressed_text,
                compression_ratio=compression_ratio,
                quality_score=quality_score,
                keywords=keywords,
                summary=summary,
                metadata=metadata,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Compression failed: {e}")
            return self._fallback_compress(memory_text, metadata)
    
    def _create_compression_prompt(self, text: str) -> str:
        """创建压缩提示"""
        return f"""请将以下文本压缩到原长度的30%左右，保留核心信息和关键细节：

原文：
{text}

压缩要求：
1. 保留所有重要事实、决策和关键信息
2. 去除冗余描述和重复内容
3. 保持逻辑连贯性
4. 使用简洁明了的语言

压缩后的文本："""
    
    def _extract_compressed_text(self, generated_text: str, prompt: str) -> str:
        """从生成文本中提取压缩内容"""
        # 移除提示部分
        if generated_text.startswith(prompt):
            compressed = generated_text[len(prompt):].strip()
        else:
            compressed = generated_text.strip()
        
        # 清理可能的标记
        compressed = compressed.replace("压缩后的文本：", "").strip()
        compressed = compressed.replace("压缩文本：", "").strip()
        
        return compressed
    
    def _calculate_quality_score(self, original: str, compressed: str) -> float:
        """计算压缩质量分数"""
        if not original or not compressed:
            return 0.0
        
        # 基础分数：压缩比例合适性
        target_ratio = self.config.compression_ratio
        actual_ratio = len(compressed) / len(original)
        ratio_score = 1.0 - min(abs(actual_ratio - target_ratio) / target_ratio, 1.0)
        
        # 内容覆盖分数（简单版本）
        # 在实际应用中可以使用更复杂的语义相似度计算
        original_words = set(original.lower().split())
        compressed_words = set(compressed.lower().split())
        if original_words:
            overlap = len(original_words.intersection(compressed_words)) / len(original_words)
            content_score = min(overlap * 2, 1.0)  # 缩放
        else:
            content_score = 0.5
        
        # 综合分数
        quality_score = 0.6 * ratio_score + 0.4 * content_score
        
        return min(max(quality_score, 0.0), 1.0)
    
    def _extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """提取关键词（简化版本）"""
        # 在实际应用中可以使用更复杂的关键词提取算法
        words = text.lower().split()
        word_freq = {}
        for word in words:
            if len(word) > 3:  # 忽略短词
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 按频率排序
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        keywords = [word for word, _ in sorted_words[:max_keywords]]
        
        return keywords
    
    def _generate_summary(self, text: str, max_length: int = 100) -> str:
        """生成摘要（简化版本）"""
        sentences = text.split('.')
        if len(sentences) <= 3:
            return text[:max_length]
        
        # 取前几个句子作为摘要
        summary = '. '.join(sentences[:3]) + '.'
        if len(summary) > max_length:
            summary = summary[:max_length-3] + '...'
        
        return summary
    
    def _fallback_compress(self, text: str, metadata: Dict) -> CompressionResult:
        """回退压缩方法（当LLM不可用时）"""
        # 简单的基于规则的压缩
        sentences = text.split('.')
        if len(sentences) > 5:
            # 保留前3句和后2句
            compressed_sentences = sentences[:3] + ['...'] + sentences[-2:]
            compressed_text = '. '.join(compressed_sentences)
        else:
            compressed_text = text
        
        # 确保压缩比例
        target_length = int(len(text) * self.config.compression_ratio)
        if len(compressed_text) > target_length:
            compressed_text = compressed_text[:target_length] + '...'
        
        compression_ratio = len(compressed_text) / len(text) if text else 1.0
        
        return CompressionResult(
            original_text=text,
            compressed_text=compressed_text,
            compression_ratio=compression_ratio,
            quality_score=0.6,  # 回退质量分数
            keywords=self._extract_keywords(compressed_text),
            summary=self._generate_summary(compressed_text),
            metadata=metadata,
            timestamp=datetime.now()
        )
    
    def batch_compress(self, memories: List[Tuple[str, Dict]]) -> List[CompressionResult]:
        """批量压缩记忆"""
        results = []
        
        for i in range(0, len(memories), self.config.batch_size):
            batch = memories[i:i + self.config.batch_size]
            
            for memory_text, metadata in batch:
                try:
                    result = self.compress_memory(memory_text, metadata)
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Batch compression failed for memory: {e}")
                    # 添加回退结果
                    results.append(self._fallback_compress(memory_text, metadata))
        
        return results
    
    def should_compress(self, memory_text: str, access_frequency: float = 1.0) -> bool:
        """
        判断是否应该压缩记忆
        
        Args:
            memory_text: 记忆文本
            access_frequency: 访问频率（次/天）
            
        Returns:
            bool: 是否应该压缩
        """
        if not memory_text:
            return False
        
        # 基于文本长度和访问频率的决策
        text_length = len(memory_text)
        
        # 长文本且低访问频率 -> 应该压缩
        if text_length > 1000 and access_frequency < 0.5:
            return True
        
        # 中等长度文本且中等访问频率 -> 根据配置决定
        if text_length > 500 and access_frequency < 1.0:
            return True
        
        # 短文本或高访问频率 -> 不压缩
        return False
    
    def get_compression_stats(self) -> Dict[str, Any]:
        """获取压缩统计信息"""
        return {
            "model_loaded": self.pipeline is not None,
            "model_name": self.config.model_name,
            "use_4bit": self.config.use_4bit,
            "compression_ratio_target": self.config.compression_ratio,
            "min_quality_score": self.config.min_compression_score,
            "device": self.config.device if TORCH_AVAILABLE else "cpu"
        }


# 工具函数
def create_compression_pipeline(config: Optional[CompressionConfig] = None) -> FusionCompressor:
    """创建压缩管道"""
    return FusionCompressor(config)

def compress_memory_batch(
    memories: List[Dict[str, Any]],
    compressor: Optional[FusionCompressor] = None
) -> List[Dict[str, Any]]:
    """
    批量压缩记忆的便捷函数
    
    Args:
        memories: 记忆列表，每个记忆包含text和metadata
        compressor: 压缩器实例
        
    Returns:
        压缩后的记忆列表
    """
    compressor = compressor or create_compression_pipeline()
    
    # 准备输入
    memory_inputs = []
    for mem in memories:
        text = mem.get('text', '')
        metadata = mem.get('metadata', {})
        memory_inputs.append((text, metadata))
    
    # 执行压缩
    results = compressor.batch_compress(memory_inputs)
    
    # 转换为字典格式
    compressed_memories = []
    for result in results:
        compressed_memories.append({
            'original_text': result.original_text,
            'compressed_text': result.compressed_text,
            'compression_ratio': result.compression_ratio,
            'quality_score': result.quality_score,
            'keywords': result.keywords,
            'summary': result.summary,
            'metadata': result.metadata,
            'timestamp': result.timestamp.isoformat()
        })
    
    return compressed_memories