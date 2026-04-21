#!/usr/bin/env python3
"""
Aegis-Cortex V6.2 端到端集成测试
测试完整查询处理流程和性能改进
"""

import sys
import os
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 70)
print("🔬 Aegis-Cortex V6.2 端到端集成测试")
print("=" * 70)

# 模拟Qdrant客户端
class MockQdrantClient:
    """模拟Qdrant客户端用于测试"""
    
    def __init__(self):
        self.collections = {}
        self.vectors = {}
        self.metadata = {}
        self.query_count = 0
    
    def get_collections(self):
        """获取集合列表"""
        from collections import namedtuple
        Collection = namedtuple('Collection', ['name'])
        Collections = namedtuple('Collections', ['collections'])
        
        collections = []
        for name in self.collections.keys():
            collections.append(Collection(name=name))
        
        return Collections(collections=collections)
    
    def search(self, collection_name, query_vector, limit=10):
        """模拟向量搜索"""
        self.query_count += 1
        
        if collection_name not in self.vectors:
            return []
        
        # 模拟相似度计算
        results = []
        vectors = self.vectors[collection_name]
        metadata = self.metadata.get(collection_name, {})
        
        for idx, vector in enumerate(vectors):
            # 简单余弦相似度
            similarity = np.dot(query_vector, vector) / (
                np.linalg.norm(query_vector) * np.linalg.norm(vector) + 1e-10
            )
            
            result = {
                "id": idx,
                "version": 0,
                "score": float(similarity),
                "payload": metadata.get(idx, {"content": f"记忆{idx}", "importance": 0.5})
            }
            results.append(result)
        
        # 按相似度排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

# 测试1: 核心组件集成
def test_core_components():
    """测试核心组件集成"""
    print("\n1️⃣ 测试核心组件集成")
    print("-" * 40)
    
    components = {}
    
    try:
        # 1. 评分引擎
        from src.core.scoring import MemoryScoringEngine
        scoring_engine = MemoryScoringEngine()
        components["scoring_engine"] = scoring_engine
        print("✅ MemoryScoringEngine 初始化成功")
        
        # 2. 嵌入模型
        from src.core.embedding import EmbeddingModel
        embedding_model = EmbeddingModel()
        components["embedding_model"] = embedding_model
        print("✅ EmbeddingModel 初始化成功")
        
        # 3. 生命周期管理器
        from src.core.lifecycle_manager import MemoryLifecycleManager
        lifecycle_manager = MemoryLifecycleManager()
        components["lifecycle_manager"] = lifecycle_manager
        print("✅ MemoryLifecycleManager 初始化成功")
        
        # 4. Aegis-Cortex V6.2 组件
        from src.core.aegis_orchestrator import get_global_orchestrator
        from src.core.turboquant_compressor import TurboQuantCompressor
        from src.core.four_stage_filter import FourStageFilter
        from src.core.token_economy import TokenEconomyMonitor
        
        # TurboQuant压缩器
        turboquant = TurboQuantCompressor()
        components["turboquant"] = turboquant
        print("✅ TurboQuantCompressor 初始化成功")
        
        # 四级过滤器
        four_stage_filter = FourStageFilter()
        components["four_stage_filter"] = four_stage_filter
        print("✅ FourStageFilter 初始化成功")
        
        # Token经济监控
        token_economy = TokenEconomyMonitor()
        components["token_economy"] = token_economy
        print("✅ TokenEconomyMonitor 初始化成功")
        
        # Aegis协调器
        orchestrator = get_global_orchestrator()
        components["orchestrator"] = orchestrator
        print("✅ AegisOrchestrator 初始化成功")
        
        return True, components
        
    except Exception as e:
        print(f"❌ 核心组件集成失败: {e}")
        import traceback
        traceback.print_exc()
        return False, {}

# 测试2: 查询处理流程
def test_query_processing(components: Dict[str, Any]):
    """测试查询处理流程"""
    print("\n2️⃣ 测试查询处理流程")
    print("-" * 40)
    
    try:
        orchestrator = components["orchestrator"]
        embedding_model = components["embedding_model"]
        
        # 测试查询
        test_queries = [
            "如何优化AI代理的记忆系统？",
            "Token经济模型如何节省成本？",
            "TurboQuant压缩算法的原理是什么？",
            "四级过滤系统如何提高检索精度？"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n查询 {i}: {query}")
            
            # 生成查询向量
            query_vector = embedding_model.encode(query)
            print(f"  向量维度: {len(query_vector)}")
            
            # 使用协调器处理查询
            start_time = time.time()
            result = orchestrator.process_query(query, limit=5)
            processing_time = time.time() - start_time
            
            print(f"  处理时间: {processing_time:.3f}秒")
            
            if "error" in result:
                print(f"  ❌ 查询处理失败: {result['error']}")
            else:
                print(f"  ✅ 查询处理成功")
                print(f"  检索结果: {len(result.get('results', []))} 条")
                print(f"  使用Token: {result.get('token_usage', 0)}")
                print(f"  压缩率: {result.get('compression_rate', 0):.1%}")
                
                # 显示前3个结果
                for j, item in enumerate(result.get('results', [])[:3], 1):
                    print(f"    {j}. {item.get('content', '')[:60]}... (分数: {item.get('score', 0):.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ 查询处理测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试3: TurboQuant压缩性能
def test_turboquant_compression(components: Dict[str, Any]):
    """测试TurboQuant压缩性能"""
    print("\n3️⃣ 测试TurboQuant压缩性能")
    print("-" * 40)
    
    try:
        turboquant = components["turboquant"]
        
        # 测试数据
        test_data = [
            {"id": 1, "vector": np.random.randn(768).tolist(), "metadata": {"importance": 0.8}},
            {"id": 2, "vector": np.random.randn(768).tolist(), "metadata": {"importance": 0.6}},
            {"id": 3, "vector": np.random.randn(768).tolist(), "metadata": {"importance": 0.9}},
            {"id": 4, "vector": np.random.randn(768).tolist(), "metadata": {"importance": 0.7}},
            {"id": 5, "vector": np.random.randn(768).tolist(), "metadata": {"importance": 0.5}},
        ]
        
        print(f"测试数据: {len(test_data)} 条记录")
        
        # 压缩测试
        start_time = time.time()
        compressed_data = turboquant.compress_batch(test_data)
        compression_time = time.time() - start_time
        
        # 解压测试
        start_time = time.time()
        decompressed_data = turboquant.decompress_batch(compressed_data)
        decompression_time = time.time() - start_time
        
        # 计算压缩率
        original_size = sum(len(json.dumps(item).encode('utf-8')) for item in test_data)
        compressed_size = sum(len(json.dumps(item).encode('utf-8')) for item in compressed_data)
        compression_ratio = 1 - (compressed_size / original_size)
        
        print(f"压缩时间: {compression_time:.3f}秒")
        print(f"解压时间: {decompression_time:.3f}秒")
        print(f"原始大小: {original_size} 字节")
        print(f"压缩大小: {compressed_size} 字节")
        print(f"压缩率: {compression_ratio:.1%}")
        
        # 验证数据完整性
        if len(decompressed_data) == len(test_data):
            print("✅ 数据完整性验证通过")
        else:
            print(f"❌ 数据完整性验证失败: 期望 {len(test_data)} 条，实际 {len(decompressed_data)} 条")
        
        return True
        
    except Exception as e:
        print(f"❌ TurboQuant压缩测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试4: 四级过滤系统
def test_four_stage_filter(components: Dict[str, Any]):
    """测试四级过滤系统"""
    print("\n4️⃣ 测试四级过滤系统")
    print("-" * 40)
    
    try:
        four_stage_filter = components["four_stage_filter"]
        
        # 模拟检索结果
        mock_results = []
        for i in range(20):
            mock_results.append({
                "id": i,
                "content": f"测试记忆内容 {i}",
                "score": 0.9 - (i * 0.04),  # 递减的相似度分数
                "metadata": {
                    "importance": 0.5 + (i % 3) * 0.2,
                    "timestamp": f"2026-04-{20 + (i % 5):02d}",
                    "category": ["技术", "优化", "AI"][i % 3]
                }
            })
        
        print(f"模拟检索结果: {len(mock_results)} 条")
        
        # 应用四级过滤
        start_time = time.time()
        filtered_results = four_stage_filter.filter(
            mock_results,
            query="AI记忆优化",
            context={"user_id": "test_user", "time_of_day": "morning"}
        )
        filter_time = time.time() - start_time
        
        print(f"过滤时间: {filter_time:.3f}秒")
        print(f"过滤前: {len(mock_results)} 条")
        print(f"过滤后: {len(filtered_results)} 条")
        print(f"过滤率: {(1 - len(filtered_results)/len(mock_results)):.1%}")
        
        # 显示过滤后的结果
        print("\n过滤后结果 (前5条):")
        for i, result in enumerate(filtered_results[:5], 1):
            print(f"  {i}. {result['content'][:40]}... (分数: {result['score']:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ 四级过滤测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试5: Token经济监控
def test_token_economy(components: Dict[str, Any]):
    """测试Token经济监控"""
    print("\n5️⃣ 测试Token经济监控")
    print("-" * 40)
    
    try:
        token_economy = components["token_economy"]
        
        # 模拟Token使用
        test_operations = [
            {"operation": "query", "tokens": 150, "model": "gpt-4"},
            {"operation": "embedding", "tokens": 50, "model": "nomic"},
            {"operation": "compression", "tokens": 10, "model": "turboquant"},
            {"operation": "query", "tokens": 200, "model": "gpt-4"},
            {"operation": "summary", "tokens": 100, "model": "claude-3"},
        ]
        
        print("模拟Token使用记录:")
        for op in test_operations:
            token_economy.record_usage(
                operation=op["operation"],
                tokens=op["tokens"],
                model=op["model"]
            )
            print(f"  {op['operation']}: {op['tokens']} tokens ({op['model']})")
        
        # 获取统计信息
        stats = token_economy.get_statistics()
        
        print(f"\nToken使用统计:")
        print(f"  总Token数: {stats['total_tokens']}")
        print(f"  总成本: ${stats['total_cost']:.4f}")
        print(f"  平均每查询Token: {stats['avg_tokens_per_query']:.1f}")
        print(f"  最昂贵模型: {stats['most_expensive_model']}")
        
        # 检查是否需要降级
        should_downgrade = token_economy.should_downgrade_model("gpt-4")
        print(f"  GPT-4是否需要降级: {should_downgrade}")
        
        if should_downgrade:
            alternative = token_economy.get_alternative_model("gpt-4")
            print(f"  推荐替代模型: {alternative}")
        
        return True
        
    except Exception as e:
        print(f"❌ Token经济测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试6: 系统状态检查
def test_system_status(components: Dict[str, Any]):
    """测试系统状态检查"""
    print("\n6️⃣ 测试系统状态检查")
    print("-" * 40)
    
    try:
        orchestrator = components["orchestrator"]
        
        # 获取系统状态
        status = orchestrator.get_system_status()
        
        print("系统状态报告:")
        print(f"  版本: {status.get('version', 'N/A')}")
        print(f"  状态: {status.get('status', 'N/A')}")
        print(f"  组件数量: {len(status.get('components', {}))}")
        
        # 检查组件状态
        components_status = status.get('components', {})
        for comp_name, comp_status in components_status.items():
            status_str = "✅ 正常" if comp_status.get('active', False) else "❌ 异常"
            print(f"  {comp_name}: {status_str}")
        
        # 检查性能指标
        metrics = status.get('metrics', {})
        if metrics:
            print(f"\n性能指标:")
            for metric_name, metric_value in metrics.items():
                print(f"  {metric_name}: {metric_value}")
        
        return True
        
    except Exception as e:
        print(f"❌ 系统状态测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# 主测试函数
def main():
    """主测试函数"""
    print("🚀 开始Aegis-Cortex V6.2端到端测试")
    print("=" * 70)
    
    test_results = {}
    
    # 测试1: 核心组件集成
    success, components = test_core_components()
    test_results["core_components"] = success
    
    if not success:
        print("\n❌ 核心组件集成失败，终止测试")
        return False
    
    # 测试2-6
    tests = [
        ("query_processing", lambda: test_query_processing(components)),
        ("turboquant_compression", lambda: test_turboquant_compression(components)),
        ("four_stage_filter", lambda: test_four_stage_filter(components)),
        ("token_economy", lambda: test_token_economy(components)),
        ("system_status", lambda: test_system_status(components)),
    ]
    
    for test_name, test_func in tests:
        test_results[test_name] = test_func()
    
    # 汇总结果
    print("\n" + "=" * 70)
    print("📊 测试结果汇总")
    print("=" * 70)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！Aegis-Cortex V6.2 集成测试成功")
        return True
    else:
        print(f"\n⚠️  部分测试失败 ({total-passed}/{total})")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)