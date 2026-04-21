#!/usr/bin/env python3
"""
Aegis-Cortex V6.2 集成测试脚本
Integration test script for Aegis-Cortex V6.2
测试TurboQuant压缩、四级过滤、Token经济等组件的集成
Test integration of TurboQuant compression, four-stage filtering, token economy, etc.
"""

import sys
import os
import time
import json
import numpy as np
from datetime import datetime, timedelta

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.aegis_orchestrator import get_global_orchestrator, AegisOrchestrator
from core.aegis_config import AegisCortexConfig
from core.turboquant_compressor import TurboQuantCompressor
from core.four_stage_filter import FourStageFilter, FourStageFilterConfig
from core.token_economy import TokenEconomyMonitor, TokenOperation
from core.qdrant_storage import QdrantMemoryStorage, MemoryRecord
from core.scoring import MemoryScoringEngine as ScoringEngine, ScoringConfig
from core.embedding import EmbeddingModel


class MockQdrantStorage:
    """模拟Qdrant存储 - Mock Qdrant storage for testing"""
    
    def __init__(self):
        self.memories = []
        self._create_sample_memories()
    
    def _create_sample_memories(self):
        """创建测试记忆样本 - Create sample memories for testing"""
        # 样本记忆数据
        sample_memories = [
            {
                "content": "用户喜欢在早上喝咖啡，特别是美式咖啡。",
                "importance_score": 0.8,
                "metadata": {"category": "preference", "source": "conversation"},
                "embedding": np.random.randn(768).astype(np.float32)
            },
            {
                "content": "交易策略：当RSI低于30时买入，高于70时卖出。",
                "importance_score": 0.9,
                "metadata": {"category": "trading", "priority": "high"},
                "embedding": np.random.randn(768).astype(np.float32)
            },
            {
                "content": "项目截止日期是2026年4月30日，需要提前完成。",
                "importance_score": 0.7,
                "metadata": {"category": "deadline", "urgency": "high"},
                "embedding": np.random.randn(768).astype(np.float32)
            },
            {
                "content": "Python代码优化技巧：使用列表推导式替代for循环。",
                "importance_score": 0.6,
                "metadata": {"category": "coding", "topic": "optimization"},
                "embedding": np.random.randn(768).astype(np.float32)
            },
            {
                "content": "会议记录：每周一上午10点团队同步会议。",
                "importance_score": 0.5,
                "metadata": {"category": "meeting", "frequency": "weekly"},
                "embedding": np.random.randn(768).astype(np.float32)
            }
        ]
        
        for i, mem in enumerate(sample_memories):
            record = MemoryRecord(
                id=f"test_memory_{i}",
                content=mem["content"],
                embedding=mem["embedding"],
                importance_score=mem["importance_score"],
                metadata=mem["metadata"],
                created_at=datetime.now() - timedelta(days=i)
            )
            self.memories.append(record)
    
    def search_memories(self, query_vector, limit=10):
        """搜索记忆 - Search memories"""
        # 简单模拟：返回所有记忆
        return self.memories[:limit]
    
    def get_recent_memories(self, limit=10):
        """获取最近记忆 - Get recent memories"""
        return self.memories[:limit]
    
    def search_by_category(self, category, limit=10):
        """按类别搜索 - Search by category"""
        filtered = [m for m in self.memories 
                   if m.metadata and m.metadata.get("category") == category]
        return filtered[:limit]


class MockEmbeddingModel:
    """模拟嵌入模型 - Mock embedding model for testing"""
    
    def __init__(self):
        self.dimension = 768
    
    def encode(self, text):
        """生成文本嵌入 - Generate text embedding"""
        # 创建确定性嵌入（基于文本哈希）
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        np.random.seed(hash_val % (2**32))
        return np.random.randn(self.dimension).astype(np.float32)


def test_turboquant_compression():
    """测试TurboQuant压缩 - Test TurboQuant compression"""
    print("🧪 测试TurboQuant压缩引擎...")
    print("Testing TurboQuant compression engine...")
    
    compressor = TurboQuantCompressor()
    
    # 测试KV缓存压缩
    kv_cache = {
        "layer_1": np.random.randn(32, 128, 768).astype(np.float32),
        "layer_2": np.random.randn(32, 128, 768).astype(np.float32)
    }
    
    # 压缩
    compressed = compressor.compress_kv_cache(kv_cache)
    print(f"  KV缓存压缩: {len(kv_cache)}层 → {len(compressed)}层")
    print(f"  KV cache compression: {len(kv_cache)} layers → {len(compressed)} layers")
    
    # 解压缩
    decompressed = compressor.decompress_kv_cache(compressed)
    print(f"  KV缓存解压缩: {len(decompressed)}层恢复")
    print(f"  KV cache decompression: {len(decompressed)} layers restored")
    
    # 测试上下文压缩
    context_text = "这是一个测试上下文。包含多个句子用于测试压缩功能。" * 50
    compressed_text = compressor.compress_context(context_text, max_tokens=100)
    
    original_tokens = len(context_text.split())
    compressed_tokens = len(compressed_text.split())
    compression_ratio = compressed_tokens / original_tokens
    
    print(f"  上下文压缩: {original_tokens} tokens → {compressed_tokens} tokens")
    print(f"  Context compression: {original_tokens} tokens → {compressed_tokens} tokens")
    print(f"  压缩率: {compression_ratio:.1%}")
    print(f"  Compression ratio: {compression_ratio:.1%}")
    
    return compression_ratio < 0.5  # 期望压缩率低于50%


def test_four_stage_filter():
    """测试四级过滤 - Test four-stage filtering"""
    print("\n🧪 测试四级过滤检索系统...")
    print("Testing four-stage filtering retrieval system...")
    
    # 创建模拟组件
    qdrant_storage = MockQdrantStorage()
    scoring_engine = ScoringEngine()
    
    # 创建过滤器
    filter_config = FourStageFilterConfig(
        similarity_threshold=0.5,  # 降低阈值以便测试
        importance_threshold=0.4
    )
    filter_system = FourStageFilter(qdrant_storage, scoring_engine, filter_config)
    
    # 测试查询
    query = "咖啡和交易策略"
    query_embedding = np.random.randn(768).astype(np.float32)
    
    results = filter_system.retrieve_memories(query, query_embedding)
    
    print(f"  查询: '{query}'")
    print(f"  Query: '{query}'")
    print(f"  检索结果: {len(results)}条记忆")
    print(f"  Retrieval results: {len(results)} memories")
    
    if results:
        for i, memory in enumerate(results[:3]):
            print(f"    {i+1}. {memory.content[:50]}... (重要性: {memory.importance_score:.2f})")
            print(f"       {memory.content[:50]}... (importance: {memory.importance_score:.2f})")
    
    return len(results) > 0


def test_token_economy():
    """测试Token经济监控 - Test token economy monitoring"""
    print("\n🧪 测试Token经济监控...")
    print("Testing token economy monitoring...")
    
    from core.token_economy import TokenEconomyConfig
    config = TokenEconomyConfig(
        daily_token_budget=100.0,
        token_cost_warning_threshold=10.0
    )
    monitor = TokenEconomyMonitor(config)
    
    # 记录一些使用情况
    operations = [
        (TokenOperation.CAPTURE, "local-embedding", 100, 0),
        (TokenOperation.RETRIEVAL, "four_stage_filter", 50, 10),
        (TokenOperation.GENERATION, "gpt-4", 200, 150),
        (TokenOperation.COMPRESSION, "turboquant", 300, 75),
    ]
    
    for op, model, input_tokens, output_tokens in operations:
        monitor.record_usage(op, model, input_tokens, output_tokens)
    
    # 获取报告
    daily_report = monitor.get_daily_report()
    weekly_report = monitor.get_weekly_report()
    
    print(f"  总成本: {monitor.total_cost:.4f}元")
    print(f"  Total cost: {monitor.total_cost:.4f} RMB")
    print(f"  总Token数: {monitor.total_tokens}")
    print(f"  Total tokens: {monitor.total_tokens}")
    print(f"  降级级别: {monitor.downgrade_level.value}")
    print(f"  Downgrade level: {monitor.downgrade_level.value}")
    
    # 预测成本
    prediction = monitor.predict_costs()
    print(f"  预测每日成本: {prediction.predicted_daily_cost:.2f}元")
    print(f"  Predicted daily cost: {prediction.predicted_daily_cost:.2f} RMB")
    
    return monitor.total_cost > 0


def test_aegis_orchestrator():
    """测试Aegis协调器 - Test Aegis orchestrator"""
    print("\n🧪 测试Aegis协调器完整流程...")
    print("Testing Aegis orchestrator complete workflow...")
    
    # 创建模拟组件
    qdrant_storage = MockQdrantStorage()
    scoring_engine = ScoringEngine()
    embedding_model = MockEmbeddingModel()
    
    # 获取协调器
    orchestrator = get_global_orchestrator()
    
    # 创建上下文
    query = "告诉我用户的偏好和交易策略"
    context = orchestrator.create_context(
        query=query,
        qdrant_storage=qdrant_storage,
        scoring_engine=scoring_engine,
        embedding_model=embedding_model
    )
    
    print(f"  初始查询: '{query}'")
    print(f"  Initial query: '{query}'")
    print(f"  查询向量维度: {context.query_embedding.shape}")
    print(f"  Query vector dimension: {context.query_embedding.shape}")
    
    # 处理查询
    result = orchestrator.process_query(context)
    
    print(f"  处理耗时: {result.get_elapsed_time():.2f}秒")
    print(f"  Processing time: {result.get_elapsed_time():.2f} seconds")
    print(f"  检索记忆数: {len(result.retrieved_memories)}")
    print(f"  Retrieved memories: {len(result.retrieved_memories)}")
    print(f"  是否压缩: {result.compressed_context is not None}")
    print(f"  Compressed: {result.compressed_context is not None}")
    
    if result.compressed_context:
        compressed_tokens = len(result.compressed_context.split())
        print(f"  压缩后Token数: {compressed_tokens}")
        print(f"  Compressed tokens: {compressed_tokens}")
    
    # 显示Token使用情况
    if result.token_usage:
        print(f"  Token使用情况:")
        print(f"  Token usage:")
        for op, usages in result.token_usage.items():
            total_tokens = sum(u["total_tokens"] for u in usages)
            total_cost = sum(u["cost_rmb"] for u in usages)
            print(f"    {op}: {total_tokens} tokens, {total_cost:.4f}元")
            print(f"      {op}: {total_tokens} tokens, {total_cost:.4f} RMB")
    
    # 获取系统状态
    status = orchestrator.get_system_status()
    print(f"  系统状态: {status['version']} - {status['architecture']}")
    print(f"  System status: {status['version']} - {status['architecture']}")
    
    return result.retrieved_memories is not None


def test_performance_comparison():
    """性能对比测试 - Performance comparison test"""
    print("\n📊 性能对比测试 (V6.0 vs V6.2)...")
    print("Performance comparison test (V6.0 vs V6.2)...")
    
    # 模拟传统检索（V6.0）
    print("  传统检索 (V6.0):")
    print("  Traditional retrieval (V6.0):")
    
    start_time = time.time()
    qdrant_storage = MockQdrantStorage()
    query_embedding = np.random.randn(768).astype(np.float32)
    
    # 简单检索（无过滤）
    traditional_results = qdrant_storage.search_memories(query_embedding, limit=10)
    traditional_time = time.time() - start_time
    
    print(f"    检索时间: {traditional_time:.3f}秒")
    print(f"    Retrieval time: {traditional_time:.3f} seconds")
    print(f"    结果数量: {len(traditional_results)}")
    print(f"    Result count: {len(traditional_results)}")
    
    # Aegis-Cortex检索（V6.2）
    print("  Aegis-Cortex检索 (V6.2):")
    print("  Aegis-Cortex retrieval (V6.2):")
    
    start_time = time.time()
    orchestrator = get_global_orchestrator()
    scoring_engine = ScoringEngine()
    embedding_model = MockEmbeddingModel()
    
    context = orchestrator.create_context(
        query="测试查询",
        qdrant_storage=qdrant_storage,
        scoring_engine=scoring_engine,
        embedding_model=embedding_model,
        query_embedding=query_embedding
    )
    
    result = orchestrator.process_query(context)
    aegis_time = time.time() - start_time
    
    print(f"    总处理时间: {aegis_time:.3f}秒")
    print(f"    Total processing time: {aegis_time:.3f} seconds")
    print(f"    检索记忆数: {len(result.retrieved_memories)}")
    print(f"    Retrieved memories: {len(result.retrieved_memories)}")
    print(f"    压缩率: {len(result.compressed_context.split()) / 100:.1%}")
    print(f"    Compression ratio: {len(result.compressed_context.split()) / 100:.1%}")
    
    # 计算改进
    time_improvement = (traditional_time - aegis_time) / traditional_time * 100
    print(f"    时间改进: {time_improvement:+.1f}%")
    print(f"    Time improvement: {time_improvement:+.1f}%")
    
    return aegis_time < traditional_time * 1.5  # 允许一些开销


def main():
    """主测试函数 - Main test function"""
    print("=" * 60)
    print("Aegis-Cortex V6.2 集成测试")
    print("Aegis-Cortex V6.2 Integration Test")
    print("=" * 60)
    
    test_results = {}
    
    try:
        # 运行所有测试
        test_results["turboquant"] = test_turboquant_compression()
        test_results["four_stage_filter"] = test_four_stage_filter()
        test_results["token_economy"] = test_token_economy()
        test_results["aegis_orchestrator"] = test_aegis_orchestrator()
        test_results["performance"] = test_performance_comparison()
        
        # 输出总结
        print("\n" + "=" * 60)
        print("测试结果总结")
        print("Test Results Summary")
        print("=" * 60)
        
        all_passed = True
        for test_name, passed in test_results.items():
            status = "✅ 通过" if passed else "❌ 失败"
            status_en = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{test_name:20} {status:10} {status_en}")
            if not passed:
                all_passed = False
        
        print("\n" + "=" * 60)
        if all_passed:
            print("🎉 所有测试通过！Aegis-Cortex V6.2 集成成功！")
            print("🎉 All tests passed! Aegis-Cortex V6.2 integration successful!")
        else:
            print("⚠️  部分测试失败，需要进一步调试。")
            print("⚠️  Some tests failed, need further debugging.")
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)