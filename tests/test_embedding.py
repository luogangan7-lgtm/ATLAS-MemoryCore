"""
嵌入模型测试
"""

import pytest
import numpy as np
from atlas_memory.core.embedding import EmbeddingModel, EmbeddingConfig


class TestEmbeddingModel:
    """嵌入模型测试类"""
    
    def test_initialization(self):
        """测试初始化"""
        config = EmbeddingConfig(
            model_name="nomic-ai/nomic-embed-text-v1.5",
            device="cpu"
        )
        model = EmbeddingModel(config)
        
        assert model.model is not None
        assert model.get_dimension() > 0
    
    def test_encode_single(self):
        """测试单个文本编码"""
        model = EmbeddingModel()
        
        text = "这是一个测试文本"
        vector = model.encode_single(text)
        
        assert isinstance(vector, list)
        assert len(vector) == model.get_dimension()
        assert all(isinstance(v, float) for v in vector)
    
    def test_encode_batch(self):
        """测试批量编码"""
        model = EmbeddingModel()
        
        texts = ["文本1", "文本2", "文本3"]
        vectors = model.encode(texts)
        
        assert len(vectors) == len(texts)
        for vector in vectors:
            assert len(vector) == model.get_dimension()
    
    def test_similarity(self):
        """测试相似度计算"""
        model = EmbeddingModel()
        
        # 测试相同文本
        text = "相同的文本"
        vec1 = model.encode_single(text)
        vec2 = model.encode_single(text)
        
        similarity = model.similarity(vec1, vec2)
        assert 0.9 <= similarity <= 1.0  # 相同文本应该高度相似
        
        # 测试不同文本
        vec3 = model.encode_single("完全不同的文本")
        similarity2 = model.similarity(vec1, vec3)
        assert 0.0 <= similarity2 <= 0.5  # 不同文本应该相似度较低
    
    def test_batch_similarity(self):
        """测试批量相似度计算"""
        model = EmbeddingModel()
        
        query_text = "查询文本"
        target_texts = ["目标文本1", "目标文本2", "目标文本3"]
        
        query_vec = model.encode_single(query_text)
        target_vecs = model.encode(target_texts)
        
        similarities = model.batch_similarity(query_vec, target_vecs)
        
        assert len(similarities) == len(target_texts)
        assert all(0.0 <= s <= 1.0 for s in similarities)
    
    def test_zero_vector_handling(self):
        """测试零向量处理"""
        model = EmbeddingModel()
        
        # 创建零向量
        dimension = model.get_dimension()
        zero_vector = [0.0] * dimension
        
        # 测试零向量相似度
        similarity = model.similarity(zero_vector, zero_vector)
        assert similarity == 0.0
        
        # 测试零向量批量相似度
        similarities = model.batch_similarity(zero_vector, [zero_vector, zero_vector])
        assert all(s == 0.0 for s in similarities)
    
    def test_invalid_input(self):
        """测试无效输入"""
        model = EmbeddingModel()
        
        # 测试空文本
        with pytest.raises(Exception):
            model.encode_single("")
        
        # 测试空列表
        with pytest.raises(Exception):
            model.encode([])
    
    def test_get_default_model(self):
        """测试获取默认模型"""
        from atlas_memory.core.embedding import get_default_embedding_model
        
        model1 = get_default_embedding_model()
        model2 = get_default_embedding_model()
        
        # 应该是同一个实例
        assert model1 is model2
        assert model1.model is not None