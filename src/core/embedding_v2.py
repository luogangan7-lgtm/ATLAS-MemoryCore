"""
增强嵌入模型 - 集成nomic-embed-text-v1.5
零Token捕获层的核心组件
"""

import time
import hashlib
from typing import List, Union, Optional, Dict, Any
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    from nomic import embed
    NOMIC_AVAILABLE = True
except ImportError:
    NOMIC_AVAILABLE = False

from dataclasses import dataclass
from enum import Enum


class EmbeddingModelType(Enum):
    """嵌入模型类型"""
    NOMIC = "nomic"  # nomic-embed-text-v1.5
    SENTENCE_TRANSFORMERS = "sentence_transformers"  # 备用模型
    FALLBACK = "fallback"  # 降级方案


@dataclass
class EmbeddingConfig:
    """嵌入配置"""
    model_type: EmbeddingModelType = EmbeddingModelType.NOMIC
    model_name: str = "nomic-ai/nomic-embed-text-v1.5"
    batch_size: int = 32
    normalize_embeddings: bool = True
    device: str = "cpu"  # 默认使用CPU，避免GPU内存问题
    cache_size: int = 1000  # 缓存大小
    timeout_seconds: int = 30  # 超时时间


class EnhancedEmbeddingModel:
    """
    增强嵌入模型
    支持多种嵌入模型，优先使用nomic-embed-text-v1.5
    """
    
    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self.model = None
        self.model_type = None
        self.vector_size = 768  # nomic-embed-text-v1.5的维度
        
        # 简单的LRU缓存
        self.cache = {}
        self.cache_order = []
        
        self._initialize_model()
    
    def _initialize_model(self):
        """初始化嵌入模型"""
        try:
            if self.config.model_type == EmbeddingModelType.NOMIC and NOMIC_AVAILABLE:
                self._init_nomic_model()
                # _init_nomic_model may have already set a fallback model_type;
                # only assign NOMIC here if it didn't (i.e. still None)
                if self.model_type is None:
                    self.model_type = EmbeddingModelType.NOMIC
                    print(f"✅ 使用Nomic嵌入模型: {self.config.model_name}")

            elif SENTENCE_TRANSFORMERS_AVAILABLE:
                self._init_sentence_transformers()
                self.model_type = EmbeddingModelType.SENTENCE_TRANSFORMERS
                print(f"⚠️ 使用Sentence Transformers作为备用模型")
                
            else:
                self._init_fallback_model()
                self.model_type = EmbeddingModelType.FALLBACK
                print("⚠️ 使用降级嵌入模型（随机向量）")
                
        except Exception as e:
            print(f"❌ 嵌入模型初始化失败: {e}")
            self._init_fallback_model()
            self.model_type = EmbeddingModelType.FALLBACK
    
    def _init_nomic_model(self):
        """初始化Nomic模型"""
        # Nomic模型通过API调用，需要API token
        # 如果没有配置token，降级到备用模型
        self.vector_size = 768  # nomic-embed-text-v1.5的固定维度
        self.model = None  # Nomic通过embed.text调用
        
        # 检查Nomic token
        try:
            from nomic import embed
            # 尝试一个简单的调用来验证token
            test_result = embed.text(
                texts=["test"],
                model='nomic-embed-text-v1.5',
                task_type='search_document'
            )
            print("✅ Nomic API token验证成功")
        except Exception as e:
            print(f"⚠️ Nomic API token未配置或无效: {e}")
            print("⚠️ 将降级到备用嵌入模型")
            # 降级到sentence-transformers
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                self._init_sentence_transformers()
                self.model_type = EmbeddingModelType.SENTENCE_TRANSFORMERS
            else:
                self._init_fallback_model()
                self.model_type = EmbeddingModelType.FALLBACK
    
    def _init_sentence_transformers(self):
        """初始化Sentence Transformers模型"""
        try:
            self.model = SentenceTransformer(
                self.config.model_name,
                device=self.config.device
            )
            # 兼容新旧版本
            try:
                self.vector_size = self.model.get_embedding_dimension()
            except AttributeError:
                self.vector_size = self.model.get_sentence_embedding_dimension()
        except Exception as e:
            print(f"❌ Sentence Transformers初始化失败: {e}")
            raise
    
    def _init_fallback_model(self):
        """初始化降级模型（随机向量）"""
        self.vector_size = 768
        self.model = None
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def _update_cache(self, key: str, embedding: List[float]):
        """更新缓存"""
        if key in self.cache:
            self.cache_order.remove(key)
        
        self.cache[key] = embedding
        self.cache_order.append(key)
        
        # 维护缓存大小
        while len(self.cache) > self.config.cache_size:
            oldest_key = self.cache_order.pop(0)
            del self.cache[oldest_key]
    
    def encode_single(self, text: str, task: str = "document") -> List[float]:
        """
        编码单个文本。

        Args:
            text: 输入文本
            task: "document"（存储）或 "query"（检索）。
                  nomic 模型会自动添加 search_document:/search_query: 前缀。

        Returns:
            嵌入向量
        """
        if not text or not isinstance(text, str):
            raise ValueError(f"无效的文本输入: {text}")

        cache_key = self._get_cache_key(f"{task}:{text}")
        if cache_key in self.cache:
            return self.cache[cache_key]

        if self.model_type == EmbeddingModelType.NOMIC:
            embedding = self._encode_with_nomic([text], task=task)[0]
        elif self.model_type == EmbeddingModelType.SENTENCE_TRANSFORMERS:
            embedding = self._encode_with_sentence_transformers([text], task=task)[0]
        else:
            embedding = self._encode_with_fallback([text])[0]

        self._update_cache(cache_key, embedding)
        return embedding
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量编码文本
        
        Args:
            texts: 文本列表
            
        Returns:
            嵌入向量列表
        """
        # 输入验证
        if not texts:
            raise ValueError("输入文本列表不能为空")
        
        for text in texts:
            if not text or not isinstance(text, str):
                raise ValueError(f"无效的文本输入: {text}")
        
        # 分批处理
        batch_size = self.config.batch_size
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # 检查缓存
            batch_embeddings = []
            batch_to_encode = []
            batch_indices = []
            
            for j, text in enumerate(batch):
                cache_key = self._get_cache_key(text)
                if cache_key in self.cache:
                    batch_embeddings.append(self.cache[cache_key])
                else:
                    batch_to_encode.append(text)
                    batch_indices.append(j)
            
            # 编码未缓存的文本
            if batch_to_encode:
                if self.model_type == EmbeddingModelType.NOMIC:
                    encoded = self._encode_with_nomic(batch_to_encode)
                elif self.model_type == EmbeddingModelType.SENTENCE_TRANSFORMERS:
                    encoded = self._encode_with_sentence_transformers(batch_to_encode)
                else:
                    encoded = self._encode_with_fallback(batch_to_encode)
                
                # 更新缓存并合并结果
                for idx, (text, emb) in enumerate(zip(batch_to_encode, encoded)):
                    cache_key = self._get_cache_key(text)
                    self._update_cache(cache_key, emb)
                    
                    # 找到在原始batch中的位置
                    original_idx = batch_indices[idx]
                    # 插入到正确位置
                    while len(batch_embeddings) <= original_idx:
                        batch_embeddings.append(None)
                    batch_embeddings[original_idx] = emb
            
            # 确保所有位置都有值
            for j in range(len(batch)):
                if batch_embeddings[j] is None:
                    # 这不应该发生，但以防万一
                    text = batch[j]
                    cache_key = self._get_cache_key(text)
                    if cache_key in self.cache:
                        batch_embeddings[j] = self.cache[cache_key]
                    else:
                        # 重新编码
                        emb = self.encode_single(text)
                        batch_embeddings[j] = emb
            
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    def _encode_with_nomic(self, texts: List[str]) -> List[List[float]]:
        """使用Nomic API编码"""
        try:
            # Nomic嵌入调用
            result = embed.text(
                texts=texts,
                model='nomic-embed-text-v1.5',
                task_type='search_document'  # 或 'search_query'
            )
            
            embeddings = result['embeddings']
            
            # 确保归一化
            if self.config.normalize_embeddings:
                embeddings = [self._normalize_vector(emb) for emb in embeddings]
            
            return embeddings
            
        except Exception as e:
            print(f"❌ Nomic编码失败: {e}")
            # 降级到备用方案
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                return self._encode_with_sentence_transformers(texts)
            else:
                return self._encode_with_fallback(texts)
    
    def _encode_with_sentence_transformers(self, texts: List[str], task: str = "document") -> List[List[float]]:
        """使用Sentence Transformers编码（nomic 模型自动添加任务前缀）"""
        try:
            encode_texts = texts
            if "nomic" in self.config.model_name.lower():
                prefix = "search_query: " if task == "query" else "search_document: "
                encode_texts = [prefix + t for t in texts]

            embeddings = self.model.encode(
                encode_texts,
                batch_size=self.config.batch_size,
                normalize_embeddings=self.config.normalize_embeddings,
                show_progress_bar=False
            )
            
            # 转换为列表格式
            return [emb.tolist() for emb in embeddings]
            
        except Exception as e:
            print(f"❌ Sentence Transformers编码失败: {e}")
            return self._encode_with_fallback(texts)
    
    def _encode_with_fallback(self, texts: List[str]) -> List[List[float]]:
        """使用降级方案编码（随机向量）"""
        embeddings = []
        for text in texts:
            # 生成伪随机但确定性的向量
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            np.random.seed(seed)
            vector = np.random.randn(self.vector_size).tolist()
            
            if self.config.normalize_embeddings:
                vector = self._normalize_vector(vector)
            
            embeddings.append(vector)
        
        return embeddings
    
    def _normalize_vector(self, vector: List[float]) -> List[float]:
        """归一化向量"""
        norm = np.linalg.norm(vector)
        if norm > 0:
            return [v / norm for v in vector]
        return vector
    
    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度
        
        Args:
            vec1: 向量1
            vec2: 向量2
            
        Returns:
            相似度分数 (0-1)
        """
        if len(vec1) != len(vec2):
            raise ValueError(f"向量维度不匹配: {len(vec1)} != {len(vec2)}")
        
        # 转换为numpy数组
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        
        # 计算余弦相似度
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # 确保在0-1范围内
        return max(0.0, min(1.0, similarity))
    
    def batch_similarity(self, query_vec: List[float], 
                        target_vecs: List[List[float]]) -> List[float]:
        """
        批量计算相似度
        
        Args:
            query_vec: 查询向量
            target_vecs: 目标向量列表
            
        Returns:
            相似度分数列表
        """
        similarities = []
        query_np = np.array(query_vec)
        
        for target_vec in target_vecs:
            if len(query_vec) != len(target_vec):
                similarities.append(0.0)
                continue
            
            target_np = np.array(target_vec)
            dot_product = np.dot(query_np, target_np)
            norm1 = np.linalg.norm(query_np)
            norm2 = np.linalg.norm(target_np)
            
            if norm1 == 0 or norm2 == 0:
                similarities.append(0.0)
            else:
                similarity = dot_product / (norm1 * norm2)
                similarities.append(max(0.0, min(1.0, similarity)))
        
        return similarities
    
    def get_vector_size(self) -> int:
        """获取向量维度"""
        return self.vector_size
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model_type": self.model_type.value if self.model_type else "unknown",
            "model_name": self.config.model_name,
            "vector_size": self.vector_size,
            "cache_size": len(self.cache),
            "normalize_embeddings": self.config.normalize_embeddings,
            "available_models": {
                "nomic": NOMIC_AVAILABLE,
                "sentence_transformers": SENTENCE_TRANSFORMERS_AVAILABLE
            }
        }
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.cache_order.clear()


# 全局单例实例
_global_embedding_model = None

def get_embedding_model(config: Optional[EmbeddingConfig] = None) -> EnhancedEmbeddingModel:
    """
    获取全局嵌入模型实例（单例模式）
    
    Args:
        config: 配置参数
        
    Returns:
        嵌入模型实例
    """
    global _global_embedding_model
    
    if _global_embedding_model is None:
        _global_embedding_model = EnhancedEmbeddingModel(config)
    
    return _global_embedding_model


def test_embedding_model():
    """测试嵌入模型"""
    print("🧪 测试增强嵌入模型...")
    
    model = get_embedding_model()
    info = model.get_model_info()
    
    print(f"📊 模型信息:")
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    # 测试编码
    texts = [
        "这是一个测试文本",
        "完全不同的内容",
        "ATLAS记忆系统开发中"
    ]
    
    print(f"\n📝 测试文本:")
    for i, text in enumerate(texts):
        print(f"  {i+1}. {text}")
    
    # 单文本编码
    print(f"\n🔤 单文本编码测试:")
    for text in texts:
        embedding = model.encode_single(text)
        print(f"  '{text[:20]}...' -> 维度: {len(embedding)}, 前3值: {embedding[:3]}")
    
    # 批量编码
    print(f"\n📦 批量编码测试:")
    embeddings = model.encode_batch(texts)
    print(f"  批量编码 {len(embeddings)} 个文本完成")
    
    # 相似度计算
    print(f"\n📐 相似度计算测试:")
    vec1 = embeddings[0]
    vec2 = embeddings[1]
    vec3 = embeddings[2]
    
    sim12 = model.similarity(vec1, vec2)
    sim13 = model.similarity(vec1, vec3)
    
    print(f"  文本1 vs 文本2 相似度: {sim12:.3f}")
    print(f"  文本1 vs 文本3 相似度: {sim13:.3f}")
    
    # 批量相似度
    print(f"\n📊 批量相似度测试:")
    batch_sim = model.batch_similarity(vec1, embeddings)
    for i, sim in enumerate(batch_sim):
        print(f"  文本1 vs 文本{i+1}: {sim:.3f}")
    
    print(f"\n✅ 嵌入模型测试完成")


if __name__ == "__main__":
    test_embedding_model()