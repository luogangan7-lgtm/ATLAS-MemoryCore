"""
检索模块测试 - Retrieval Module Tests
"""

import pytest
import time
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from atlas_memory.core.retrieval import MemoryRetrieval, MemoryCache, SearchResult
from atlas_memory.core.storage import MemoryRecord, MemoryMetadata, MemoryCategory
from atlas_memory.core.embedding import EmbeddingModel


class TestMemoryCache:
    """内存缓存测试 - Memory Cache Tests"""

    def test_cache_initialization(self):
        """测试缓存初始化 - Test cache initialization"""
        cache = MemoryCache(max_size=100, ttl_seconds=3600)

        assert cache.max_size == 100
        assert cache.ttl_seconds == 3600
        assert len(cache.cache) == 0
        assert len(cache.access_order) == 0

    def test_generate_key(self):
        """测试生成缓存键 - Test generate cache key"""
        cache = MemoryCache()

        key1 = cache._generate_key("查询1", {"filter": "value1"})
        key2 = cache._generate_key("查询1", {"filter": "value1"})
        key3 = cache._generate_key("查询2", {"filter": "value1"})

        # 相同查询应该生成相同键
        assert key1 == key2
        # 不同查询应该生成不同键
        assert key1 != key3

    def test_cache_set_and_get(self):
        """测试缓存设置和获取 - Test cache set and get"""
        cache = MemoryCache()

        # 创建测试结果
        test_results = [
            SearchResult(
                memory=Mock(spec=MemoryRecord),
                score=0.9,
                relevance=0.85,
                explanation="测试解释",
            )
        ]

        # 设置缓存
        cache.set("测试查询", {"filter": "test"}, test_results)

        # 获取缓存
        cached = cache.get("测试查询", {"filter": "test"})

        assert cached is not None
        assert len(cached) == 1
        assert cached[0].score == 0.9
        assert cached[0].relevance == 0.85

    def test_cache_expiration(self):
        """测试缓存过期 - Test cache expiration"""
        cache = MemoryCache(ttl_seconds=1)  # 1秒过期

        test_results = [Mock(spec=SearchResult)]
        cache.set("测试查询", None, test_results)

        # 立即获取应该存在
        assert cache.get("测试查询", None) is not None

        # 等待过期
        time.sleep(1.1)

        # 应该被清理
        cache._clean_expired()
        assert cache.get("测试查询", None) is None

    def test_cache_eviction(self):
        """测试缓存驱逐 - Test cache eviction"""
        cache = MemoryCache(max_size=2)

        # 添加3个条目
        for i in range(3):
            cache.set(f"查询{i}", None, [Mock(spec=SearchResult)])

        # 应该只保留2个
        assert len(cache.cache) == 2
        assert len(cache.access_order) == 2

    def test_cache_clear(self):
        """测试清空缓存 - Test cache clear"""
        cache = MemoryCache()

        # 添加一些数据
        for i in range(5):
            cache.set(f"查询{i}", None, [Mock(spec=SearchResult)])

        assert len(cache.cache) == 5
        assert len(cache.access_order) == 5

        # 清空缓存
        cache.clear()

        assert len(cache.cache) == 0
        assert len(cache.access_order) == 0


class TestMemoryRetrieval:
    """记忆检索测试 - Memory Retrieval Tests"""

    @pytest.fixture
    def mock_storage(self):
        """模拟存储 - Mock storage"""
        storage = Mock()

        # 模拟搜索返回
        mock_memory = MemoryRecord(
            id="test_id",
            text="测试记忆内容",
            vector=[0.1] * 768,
            metadata=MemoryMetadata(
                category=MemoryCategory.LEARNING, importance=0.8, tags=["test"]
            ),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            access_count=5,
            last_accessed=datetime.now() - timedelta(days=1),
            score=0.7,
        )

        storage.search.return_value = [mock_memory]
        storage.retrieve.return_value = mock_memory
        return storage

    @pytest.fixture
    def mock_embedding(self):
        """模拟嵌入模型 - Mock embedding model"""
        embedding = Mock()
        embedding.encode_single.return_value = [0.1] * 768
        embedding.similarity.return_value = 0.85
        return embedding

    @pytest.fixture
    def retrieval(self, mock_storage, mock_embedding):
        """创建检索器 - Create retriever"""
        return MemoryRetrieval(
            memory_storage=mock_storage, embedding_model=mock_embedding
        )

    def test_initialization(self, retrieval):
        """测试初始化 - Test initialization"""
        assert retrieval.memory_storage is not None
        assert retrieval.embedding_model is not None
        assert retrieval.config is not None
        assert retrieval.cache is not None

    def test_search_basic(self, retrieval, mock_storage, mock_embedding):
        """测试基础搜索 - Test basic search"""
        results = retrieval.search("测试查询", limit=5, threshold=0.7)

        # 验证调用
        mock_embedding.encode_single.assert_called_with("测试查询")
        mock_storage.search.assert_called()

        # 验证结果
        assert len(results) > 0
        assert results[0].score == 0.85
        assert results[0].relevance >= 0.0
        assert results[0].relevance <= 1.0

    def test_search_with_filters(self, retrieval):
        """测试带过滤器的搜索 - Test search with filters"""
        filters = {"category": "learning", "importance": {"gte": 0.5}}

        results = retrieval.search("测试查询", filters=filters)

        # 应该调用搜索
        assert retrieval.embedding_model.encode_single.called

    def test_search_with_cache(self, retrieval):
        """测试带缓存的搜索 - Test search with cache"""
        # 第一次搜索（应该缓存）
        results1 = retrieval.search("测试查询", use_cache=True)

        # 第二次搜索（应该从缓存获取）
        results2 = retrieval.search("测试查询", use_cache=True)

        # 验证结果相同
        assert len(results1) == len(results2)
        if results1 and results2:
            assert results1[0].score == results2[0].score

    def test_search_by_category(self, retrieval, mock_storage):
        """测试按分类搜索 - Test search by category"""
        # 模拟按分类搜索
        mock_storage.search.return_value = [
            MemoryRecord(
                id="cat_test",
                text="分类测试",
                vector=[0.1] * 768,
                metadata=MemoryMetadata(category=MemoryCategory.LEARNING),
                created_at=datetime.now(),
                updated_at=datetime.now(),
                score=0.6,
            )
        ]

        results = retrieval.search_by_category(
            MemoryCategory.LEARNING, limit=5, min_importance=0.5
        )

        assert len(results) > 0
        assert results[0].metadata.category == MemoryCategory.LEARNING

    def test_find_similar_memories(self, retrieval, mock_storage):
        """测试查找相似记忆 - Test find similar memories"""
        results = retrieval.find_similar_memories("test_id", limit=3)

        # 应该调用检索和搜索
        mock_storage.retrieve.assert_called_with("test_id")
        assert retrieval.embedding_model.encode_single.called

    def test_clear_cache(self, retrieval):
        """测试清空缓存 - Test clear cache"""
        # 先添加一些缓存
        retrieval.search("测试查询1")
        retrieval.search("测试查询2")

        # 清空缓存
        retrieval.clear_cache()

        # 验证缓存已清空
        stats = retrieval.get_cache_stats()
        assert stats["cache_size"] == 0

    def test_get_cache_stats(self, retrieval):
        """测试获取缓存统计 - Test get cache stats"""
        # 添加一些缓存
        retrieval.search("测试查询")

        stats = retrieval.get_cache_stats()

        assert "cache_size" in stats
        assert "max_size" in stats
        assert "ttl_seconds" in stats
        assert "access_order_length" in stats

        assert stats["cache_size"] >= 0
        assert stats["max_size"] == retrieval.config.cache_size

    def test_search_with_explain(self, retrieval):
        """测试带解释的搜索 - Test search with explain"""
        results = retrieval.search("测试查询", explain=True)

        assert len(results) > 0
        assert results[0].explanation != ""
        assert "相关性" in results[0].explanation

    def test_empty_query(self, retrieval):
        """测试空查询 - Test empty query"""
        results = retrieval.search("", limit=5)

        # 空查询应该返回结果（如果有记忆）
        assert results is not None

    def test_low_threshold(self, retrieval, mock_storage):
        """测试低阈值搜索 - Test low threshold search"""
        # 模拟低相似度结果
        mock_memory = MemoryRecord(
            id="low_score",
            text="低分记忆",
            vector=[0.1] * 768,
            metadata=MemoryMetadata(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            score=0.3,
        )
        mock_storage.search.return_value = [mock_memory]

        results = retrieval.search("测试", threshold=0.2)

        # 低阈值应该返回结果
        assert len(results) > 0

    def test_high_threshold(self, retrieval, mock_storage):
        """测试高阈值搜索 - Test high threshold search"""
        # 模拟低相似度结果
        mock_memory = MemoryRecord(
            id="low_score",
            text="低分记忆",
            vector=[0.1] * 768,
            metadata=MemoryMetadata(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            score=0.3,
        )
        mock_storage.search.return_value = [mock_memory]

        results = retrieval.search("测试", threshold=0.9)

        # 高阈值可能不返回结果
        # 这取决于模拟的相似度分数


class TestIntegration:
    """集成测试 - Integration Tests"""

    @pytest.mark.integration
    def test_create_retrieval_system(self):
        """测试创建检索系统 - Test create retrieval system"""
        # 这个测试需要实际的 Qdrant 服务
        # 在 CI/CD 环境中运行
        pytest.skip("需要 Qdrant 服务")

    @pytest.mark.integration
    def test_end_to_end_workflow(self):
        """测试端到端工作流 - Test end-to-end workflow"""
        # 完整的存储-检索工作流测试
        pytest.skip("需要完整的环境")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
