"""
嵌入模型模块 - 零Token本地嵌入实现
"""

import logging
from typing import List, Optional
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """嵌入模型配置"""

    model_name: str = "nomic-ai/nomic-embed-text-v1.5"
    device: str = "cpu"  # 或 "cuda" 如果有GPU
    cache_folder: Optional[str] = None
    normalize_embeddings: bool = True
    batch_size: int = 32


class EmbeddingModel:
    """本地嵌入模型管理器"""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self.model = None
        self._initialize_model()

    def _initialize_model(self):
        """初始化嵌入模型"""
        try:
            logger.info(f"正在加载嵌入模型: {self.config.model_name}")
            self.model = SentenceTransformer(
                self.config.model_name,
                device=self.config.device,
                cache_folder=self.config.cache_folder,
            )
            logger.info(f"嵌入模型加载成功，维度: {self.get_dimension()}")
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {e}")
            raise

    def get_dimension(self) -> int:
        """获取嵌入维度"""
        if self.model is None:
            raise RuntimeError("模型未初始化")
        return self.model.get_sentence_embedding_dimension()

    def encode(self, texts: List[str]) -> List[List[float]]:
        """
        将文本编码为向量

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        if self.model is None:
            raise RuntimeError("模型未初始化")
        
        # 输入验证
        if not texts:
            raise ValueError("输入文本列表不能为空")
        
        for text in texts:
            if not text or not isinstance(text, str):
                raise ValueError(f"无效的文本输入: {text}")

        try:
            # 批量编码
            embeddings = self.model.encode(
                texts,
                batch_size=self.config.batch_size,
                normalize_embeddings=self.config.normalize_embeddings,
                show_progress_bar=False,
            )

            # 转换为Python列表
            return embeddings.tolist()

        except Exception as e:
            logger.error(f"文本编码失败: {e}")
            raise

    def encode_single(self, text: str) -> List[float]:
        """
        编码单个文本

        Args:
            text: 输入文本

        Returns:
            向量
        """
        return self.encode([text])[0]

    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            vec1: 向量1
            vec2: 向量2

        Returns:
            相似度分数 (0-1)
        """
        import numpy as np

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

    def batch_similarity(
        self, query_vec: List[float], target_vecs: List[List[float]]
    ) -> List[float]:
        """
        批量计算相似度

        Args:
            query_vec: 查询向量
            target_vecs: 目标向量列表

        Returns:
            相似度列表
        """
        import numpy as np

        query = np.array(query_vec)
        targets = np.array(target_vecs)

        # 批量计算点积
        dot_products = np.dot(targets, query)

        # 计算范数
        query_norm = np.linalg.norm(query)
        target_norms = np.linalg.norm(targets, axis=1)

        # 避免除零
        valid_mask = (query_norm > 0) & (target_norms > 0)
        similarities = np.zeros(len(target_vecs))

        if valid_mask.any():
            similarities[valid_mask] = dot_products[valid_mask] / (
                target_norms[valid_mask] * query_norm
            )

        # 裁剪到0-1范围
        similarities = np.clip(similarities, 0.0, 1.0)

        return similarities.tolist()


# 全局默认实例
_default_embedding_model: Optional[EmbeddingModel] = None


def get_default_embedding_model() -> EmbeddingModel:
    """获取默认嵌入模型实例"""
    global _default_embedding_model
    if _default_embedding_model is None:
        _default_embedding_model = EmbeddingModel()
    return _default_embedding_model
