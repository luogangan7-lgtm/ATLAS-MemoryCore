"""
压缩模块 - Compression Module
实现记忆压缩和去重功能
Implements memory compression and deduplication functionality
"""

import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    """压缩结果 - Compression Result"""
    original_text: str
    compressed_text: str
    compression_ratio: float  # 压缩率 (0-1)
    key_points: List[str]     # 关键点
    removed_content: List[str]  # 被移除的内容
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典 - Convert to dictionary"""
        return {
            "original_text": self.original_text,
            "compressed_text": self.compressed_text,
            "compression_ratio": self.compression_ratio,
            "key_points": self.key_points,
            "removed_content": self.removed_content,
        }


class MemoryCompressor:
    """记忆压缩器 - Memory Compressor"""
    
    def __init__(self, min_length: int = 100, max_ratio: float = 0.5):
        """
        初始化压缩器 - Initialize compressor
        
        Args:
            min_length: 最小文本长度才进行压缩 - Minimum text length for compression
            max_ratio: 最大压缩比例 (0-1) - Maximum compression ratio (0-1)
        """
        self.min_length = min_length
        self.max_ratio = max_ratio
        
        # 停用词列表 (中文和英文)
        self.stop_words = {
            # 中文停用词
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
            "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
            "这", "那", "她", "他", "它", "我们", "你们", "他们", "这个", "那个", "这些",
            "那些", "什么", "为什么", "怎么", "怎么样", "多少", "几", "谁", "哪里", "何时",
            
            # 英文停用词
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
            "with", "by", "about", "as", "into", "like", "through", "after", "over",
            "between", "out", "from", "up", "down", "off", "above", "below", "i", "you",
            "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "my",
            "your", "his", "her", "its", "our", "their", "mine", "yours", "hers",
            "ours", "theirs", "this", "that", "these", "those", "am", "is", "are",
            "was", "were", "be", "been", "being", "have", "has", "had", "having",
            "do", "does", "did", "doing", "will", "would", "shall", "should", "may",
            "might", "must", "can", "could", "ought", "need", "dare", "used"
        }
        
        # 冗余模式
        self.redundant_patterns = [
            r"换句话说", r"也就是说", r"换言之", r"简而言之", r"总的来说",
            r"in other words", r"that is to say", r"in short", r"in summary",
            r"basically", r"essentially", r"fundamentally"
        ]
        
        logger.info(f"记忆压缩器初始化完成 (min_length={min_length}, max_ratio={max_ratio})")
    
    def compress(self, text: str, aggressive: bool = False) -> CompressionResult:
        """
        压缩文本 - Compress text
        
        Args:
            text: 输入文本 - Input text
            aggressive: 是否使用激进压缩 - Whether to use aggressive compression
            
        Returns:
            压缩结果 - Compression result
        """
        if len(text) < self.min_length:
            # 文本太短，不压缩
            return CompressionResult(
                original_text=text,
                compressed_text=text,
                compression_ratio=1.0,
                key_points=[text],
                removed_content=[]
            )
        
        original_text = text
        removed_content = []
        
        try:
            # 1. 移除冗余短语
            text = self._remove_redundant_phrases(text, removed_content)
            
            # 2. 简化句子结构
            text = self._simplify_sentences(text, removed_content)
            
            # 3. 移除重复内容
            text = self._remove_duplicates(text, removed_content)
            
            # 4. 提取关键点
            key_points = self._extract_key_points(original_text)
            
            # 5. 如果使用激进压缩，进一步处理
            if aggressive:
                text = self._aggressive_compression(text, removed_content)
            
            # 6. 确保压缩比例不超过限制
            text = self._enforce_compression_ratio(original_text, text)
            
            # 计算压缩率
            if len(original_text) > 0:
                compression_ratio = len(text) / len(original_text)
            else:
                compression_ratio = 1.0
            
            # 确保压缩率在合理范围内
            compression_ratio = max(self.max_ratio, min(1.0, compression_ratio))
            
            result = CompressionResult(
                original_text=original_text,
                compressed_text=text,
                compression_ratio=compression_ratio,
                key_points=key_points,
                removed_content=removed_content
            )
            
            logger.debug(f"文本压缩完成: {len(original_text)} → {len(text)} 字符, 压缩率: {compression_ratio:.2f}")
            return result
        
        except Exception as e:
            logger.error(f"压缩失败: {e}")
            # 返回原始文本作为后备
            return CompressionResult(
                original_text=original_text,
                compressed_text=original_text,
                compression_ratio=1.0,
                key_points=[original_text],
                removed_content=[]
            )
    
    def _remove_redundant_phrases(self, text: str, removed: List[str]) -> str:
        """移除冗余短语 - Remove redundant phrases"""
        for pattern in self.redundant_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                removed.append(match.group())
                text = text.replace(match.group(), "")
        
        # 移除多余的空白
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _simplify_sentences(self, text: str, removed: List[str]) -> str:
        """简化句子结构 - Simplify sentence structures"""
        # 分割句子
        sentences = re.split(r'[。！？.!?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        simplified_sentences = []
        
        for sentence in sentences:
            # 移除过长的修饰语
            simplified = self._simplify_sentence(sentence, removed)
            if simplified:
                simplified_sentences.append(simplified)
        
        # 重新组合句子
        result = '。'.join(simplified_sentences)
        if result:
            result += '。'
        
        return result
    
    def _simplify_sentence(self, sentence: str, removed: List[str]) -> str:
        """简化单个句子 - Simplify single sentence"""
        words = sentence.split()
        
        if len(words) <= 15:  # 短句子不需要简化
            return sentence
        
        # 移除停用词
        filtered_words = [word for word in words if word.lower() not in self.stop_words]
        
        # 如果移除后句子太短，保留一些停用词
        if len(filtered_words) < len(words) * 0.5:
            # 保留关键停用词
            filtered_words = words[:10] + words[-5:]  # 保留开头和结尾
        
        return ' '.join(filtered_words)
    
    def _remove_duplicates(self, text: str, removed: List[str]) -> str:
        """移除重复内容 - Remove duplicate content"""
        # 简单的重复检测（基于句子）
        sentences = re.split(r'[。.!?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 使用集合检测重复句子
        seen = set()
        unique_sentences = []
        
        for sentence in sentences:
            # 生成句子哈希（忽略大小写和空格）
            sentence_hash = hashlib.md5(sentence.lower().replace(' ', '').encode()).hexdigest()
            
            if sentence_hash not in seen:
                seen.add(sentence_hash)
                unique_sentences.append(sentence)
            else:
                removed.append(f"[重复] {sentence}")
        
        result = '。'.join(unique_sentences)
        if result:
            result += '。'
        
        return result
    
    def _extract_key_points(self, text: str) -> List[str]:
        """提取关键点 - Extract key points"""
        key_points = []
        
        # 分割句子
        sentences = re.split(r'[。！？.!?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 简单的关键点提取规则
        important_keywords = [
            "重要", "关键", "核心", "主要", "总结", "结论", "建议", "应该",
            "必须", "需要", "重要", "critical", "important", "key", "main",
            "essential", "necessary", "must", "should"
        ]
        
        for sentence in sentences:
            # 检查是否包含重要关键词
            if any(keyword in sentence.lower() for keyword in important_keywords):
                key_points.append(sentence)
            
            # 或者句子较短且信息密集
            elif len(sentence) <= 100 and len(sentence.split()) >= 5:
                key_points.append(sentence)
        
        # 限制关键点数量
        if len(key_points) > 5:
            key_points = key_points[:5]
        
        return key_points
    
    def _aggressive_compression(self, text: str, removed: List[str]) -> str:
        """激进压缩 - Aggressive compression"""
        # 只保留关键句子
        sentences = re.split(r'[。.!?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= 3:
            return text
        
        # 保留开头和结尾的句子（通常包含重要信息）
        keep_indices = {0, 1, len(sentences) - 2, len(sentences) - 1}
        
        # 寻找包含数字或重要关键词的句子
        important_patterns = [
            r'\d+',  # 数字
            r'[0-9]+%',  # 百分比
            r'最好', r'最差', r'最高', r'最低',  # 比较级
            r'best', r'worst', r'highest', r'lowest'
        ]
        
        for i, sentence in enumerate(sentences):
            if i in keep_indices:
                continue
            
            for pattern in important_patterns:
                if re.search(pattern, sentence):
                    keep_indices.add(i)
                    break
        
        # 构建压缩后的文本
        compressed_sentences = [sentences[i] for i in sorted(keep_indices)]
        
        # 记录被移除的句子
        for i, sentence in enumerate(sentences):
            if i not in keep_indices:
                removed.append(f"[激进压缩移除] {sentence}")
        
        result = '。'.join(compressed_sentences)
        if result:
            result += '。'
        
        return result
    
    def _enforce_compression_ratio(self, original: str, compressed: str) -> str:
        """确保压缩比例 - Enforce compression ratio"""
        if len(original) == 0:
            return compressed
        
        current_ratio = len(compressed) / len(original)
        
        if current_ratio <= self.max_ratio:
            return compressed
        
        # 需要进一步压缩以达到目标比例
        target_length = int(len(original) * self.max_ratio)
        
        if len(compressed) <= target_length:
            return compressed
        
        # 简单截断（在实际应用中可以使用更智能的方法）
        if target_length >= 50:  # 确保最小长度
            return compressed[:target_length] + "..."
        else:
            return compressed[:50] + "..."  # 至少保留50字符
    
    def batch_compress(self, texts: List[str], aggressive: bool = False) -> List[CompressionResult]:
        """批量压缩 - Batch compress"""
        results = []
        
        for text in texts:
            result = self.compress(text, aggressive)
            results.append(result)
        
        logger.info(f"批量压缩完成: {len(texts)} 个文本")
        return results
    
    def calculate_savings(self, results: List[CompressionResult]) -> Dict[str, Any]:
        """计算节省空间 - Calculate space savings"""
        if not results:
            return {"total_savings": 0, "avg_ratio": 1.0}
        
        total_original = sum(len(r.original_text) for r in results)
        total_compressed = sum(len(r.compressed_text) for r in results)
        
        if total_original > 0:
            total_savings = total_original - total_compressed
            savings_percentage = (total_savings / total_original) * 100
            avg_ratio = total_compressed / total_original
        else:
            total_savings = 0
            savings_percentage = 0
            avg_ratio = 1.0
        
        return {
            "total_original_chars": total_original,
            "total_compressed_chars": total_compressed,
            "total_savings_chars": total_savings,
            "savings_percentage": savings_percentage,
            "avg_compression_ratio": avg_ratio,
            "num_texts": len(results),
        }


# 工具函数 - Utility functions
def create_compressor(min_length: int = 100, max_ratio: float = 0.5) -> MemoryCompressor:
    """创建压缩器 - Create compressor"""
    return MemoryCompressor(min_length=min_length, max_ratio=max_ratio)