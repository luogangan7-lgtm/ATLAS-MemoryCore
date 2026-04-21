"""
优化的Token估算器 - 准确估算Token数量，确保压缩有效
"""

import re
from typing import Dict, List, Any


class OptimizedTokenEstimator:
    """优化的Token估算器"""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        准确估算Token数量
        基于GPT Tokenizer的近似算法
        """
        if not text:
            return 0
        
        # 1. 中文字符：1个中文字符 ≈ 1.5 tokens
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        chinese_chars = len(chinese_pattern.findall(text))
        
        # 2. 英文单词：1个单词 ≈ 1.3 tokens (平均)
        # 先移除中文
        text_without_chinese = chinese_pattern.sub(' ', text)
        english_words = re.findall(r'\b[a-zA-Z]{2,}\b', text_without_chinese)
        
        # 3. 数字和符号
        numbers = re.findall(r'\b\d+\b', text_without_chinese)
        symbols = re.findall(r'[^\w\s\u4e00-\u9fff]', text)
        
        # 4. 空格
        spaces = text.count(' ')
        
        # 5. 估算Token
        # 中文字符: 1.5 tokens/char
        # 英文单词: 1.3 tokens/word (平均长度5字符)
        # 数字: 1 token/3 digits
        # 符号: 1 token/3 symbols
        # 空格: 1 token/4 spaces
        
        tokens = (
            chinese_chars * 1.5 +
            len(english_words) * 1.3 +
            sum(len(n) for n in numbers) / 3 +
            len(symbols) / 3 +
            spaces / 4
        )
        
        return max(int(tokens), 1)
    
    @staticmethod
    def estimate_context_tokens(context: Dict[str, Any]) -> int:
        """估算完整上下文的Token数"""
        total = 0
        
        # 查询
        if "query" in context:
            total += OptimizedTokenEstimator.estimate_tokens(context["query"])
        
        # 记忆
        if "memories" in context:
            for memory in context["memories"]:
                if isinstance(memory, dict) and "text" in memory:
                    total += OptimizedTokenEstimator.estimate_tokens(memory["text"])
        
        # 系统提示
        if "system_prompt" in context:
            total += OptimizedTokenEstimator.estimate_tokens(context["system_prompt"])
        
        return total
    
    @staticmethod
    def calculate_savings(original: str, compressed: str) -> Dict[str, Any]:
        """计算压缩节省"""
        original_tokens = OptimizedTokenEstimator.estimate_tokens(original)
        compressed_tokens = OptimizedTokenEstimator.estimate_tokens(compressed)
        
        savings = original_tokens - compressed_tokens
        ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        
        return {
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "tokens_saved": savings,
            "compression_ratio": ratio,
            "effective": savings > 0
        }


class EfficientCompressor:
    """高效压缩器"""
    
    def __init__(self, target_compression_ratio: float = 0.6):
        self.target_ratio = target_compression_ratio
    
    def compress_text(self, text: str, min_length: int = 30) -> str:
        """
        高效压缩文本
        策略: 提取关键信息，移除冗余
        """
        if len(text) <= min_length:
            return text
        
        # 1. 移除多余空白
        compressed = re.sub(r'\s+', ' ', text.strip())
        
        # 2. 提取关键句子（基于标点）
        sentences = re.split(r'[.!?。！？]+', compressed)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= 2:
            # 短文本直接截断
            target_len = int(len(text) * self.target_ratio)
            if target_len < min_length:
                target_len = min_length
            
            if len(text) > target_len:
                return text[:target_len] + "..."
            return text
        
        # 3. 智能选择句子
        selected = []
        
        # 总是包含第一句（通常是主题）
        if sentences:
            selected.append(sentences[0])
        
        # 选择包含关键词的句子
        keywords = ["关键", "重要", "必须", "需要", "建议", "注意", "优化", "提高", "减少", "避免"]
        for sentence in sentences[1:-1]:
            if any(keyword in sentence for keyword in keywords):
                selected.append(sentence)
                if len(selected) >= 3:  # 最多3句
                    break
        
        # 如果不够，选择中间有信息的句子
        if len(selected) < 3 and len(sentences) > 2:
            mid_idx = len(sentences) // 2
            if mid_idx > 0 and mid_idx < len(sentences) - 1:
                selected.append(sentences[mid_idx])
        
        # 总是包含最后一句（通常是结论）
        if len(sentences) > 1:
            selected.append(sentences[-1])
        
        # 4. 构建压缩文本
        if len(selected) == 1:
            compressed_text = selected[0]
        else:
            compressed_text = "。".join(selected) + "。"
        
        # 5. 应用目标长度
        target_len = int(len(text) * self.target_ratio)
        if target_len < min_length:
            target_len = min_length
        
        if len(compressed_text) > target_len:
            compressed_text = compressed_text[:target_len] + "..."
        
        return compressed_text
    
    def compress_memory(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """压缩记忆"""
        original_text = memory.get("text", "")
        
        if not original_text:
            return memory
        
        # 计算原始Token
        original_tokens = OptimizedTokenEstimator.estimate_tokens(original_text)
        
        # 如果已经很短，不压缩
        if original_tokens <= 20:
            return memory
        
        # 压缩文本
        compressed_text = self.compress_text(original_text)
        compressed_tokens = OptimizedTokenEstimator.estimate_tokens(compressed_text)
        
        # 创建压缩后的记忆
        compressed_memory = memory.copy()
        compressed_memory["original_text"] = original_text
        compressed_memory["text"] = compressed_text
        compressed_memory["compression_stats"] = {
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "tokens_saved": original_tokens - compressed_tokens,
            "compression_ratio": compressed_tokens / original_tokens
        }
        
        return compressed_memory


# 测试函数
def test_token_estimation():
    """测试Token估算"""
    test_cases = [
        ("你好世界", "简单中文"),
        ("Hello world, this is a test.", "英文句子"),
        ("Python性能优化：使用列表推导式代替循环", "混合文本"),
        ("风险管理：单笔交易不超过2%，总仓位不超过10%", "专业文本"),
    ]
    
    print("🧪 Token估算测试")
    print("-" * 40)
    
    for text, description in test_cases:
        tokens = OptimizedTokenEstimator.estimate_tokens(text)
        print(f"{description}: '{text}'")
        print(f"  长度: {len(text)} chars, 估算Token: {tokens}")
        print(f"  比例: {tokens/len(text):.2f} tokens/char")
        print()


if __name__ == "__main__":
    test_token_estimation()