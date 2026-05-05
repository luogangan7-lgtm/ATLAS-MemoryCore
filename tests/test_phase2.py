#!/usr/bin/env python3
"""
ATLAS-MemoryCore V6.0 Phase 2 功能测试
测试融合压缩引擎和高级检索功能
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.qdrant_storage import QdrantStorage
from src.optimization.fusion_compressor import FusionCompressor, CompressionConfig
from src.core.advanced_retrieval import AdvancedRetrieval, RetrievalConfig, RetrievalMode, TemporalFilter

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_fusion_compressor():
    """测试融合压缩引擎"""
    print("\n" + "="*60)
    print("测试融合压缩引擎")
    print("="*60)
    
    try:
        # 创建压缩器
        config = CompressionConfig(
            model_name="Qwen/Qwen2.5-7B-Instruct",
            use_4bit=True,
            compression_ratio=0.3
        )
        compressor = FusionCompressor(config)
        
        # 测试压缩统计
        stats = compressor.get_compression_stats()
        print(f"压缩引擎状态: {'已加载' if stats['model_loaded'] else '回退模式'}")
        print(f"模型名称: {stats['model_name']}")
        print(f"4位量化: {stats['use_4bit']}")
        print(f"目标压缩比例: {stats['compression_ratio_target']}")
        
        # 测试压缩
        test_text = """
        ATLAS-MemoryCore V6.0 是一个先进的记忆管理系统，专门为解决OpenClaw的失忆问题而设计。
        该系统采用了四层融合架构，包括零Token捕获层、惰性检索引擎、熔断与压缩引擎以及夜间自净化循环。
        通过集成Qdrant向量数据库和nomic-embed-text-v1.5嵌入模型，实现了高效的语义检索和记忆持久化。
        系统还引入了智能记忆生命周期管理，基于5维度评分和艾宾浩斯遗忘曲线自动优化记忆存储。
        """
        
        print(f"\n原始文本长度: {len(test_text)} 字符")
        
        result = compressor.compress_memory(test_text, {"category": "test", "importance": "high"})
        
        print(f"压缩后长度: {len(result.compressed_text)} 字符")
        print(f"压缩比例: {result.compression_ratio:.2%}")
        print(f"质量分数: {result.quality_score:.2f}")
        print(f"关键词: {', '.join(result.keywords[:5])}")
        print(f"摘要: {result.summary}")
        
        # 测试批量压缩
        memories = [
            ("这是第一个测试记忆，包含一些重要的技术细节。", {"id": 1}),
            ("第二个记忆关于项目管理和团队协作的最佳实践。", {"id": 2}),
            ("第三个记忆记录了系统架构设计和性能优化方案。", {"id": 3})
        ]
        
        batch_results = compressor.batch_compress(memories)
        print(f"\n批量压缩完成: {len(batch_results)} 个记忆")
        
        for i, res in enumerate(batch_results):
            print(f"  记忆{i+1}: {len(res.compressed_text)}字符, 质量: {res.quality_score:.2f}")
        
        # 测试压缩决策
        should_compress = compressor.should_compress(test_text, access_frequency=0.2)
        print(f"\n是否应该压缩: {should_compress}")
        
        return True
        
    except Exception as e:
        logger.error(f"融合压缩测试失败: {e}")
        return False

def test_advanced_retrieval():
    """测试高级检索功能"""
    print("\n" + "="*60)
    print("测试高级检索功能")
    print("="*60)
    
    try:
        # 创建存储客户端
        storage = QdrantStorage()
        
        # 创建高级检索
        retrieval = AdvancedRetrieval(storage)
        
        # 测试不同检索模式
        test_queries = [
            ("技术架构", RetrievalMode.SEMANTIC),
            ("最近的项目", RetrievalMode.TEMPORAL),
            ("积极的经验", RetrievalMode.SENTIMENT),
            ("关键词搜索", RetrievalMode.KEYWORD),
            ("混合检索", RetrievalMode.HYBRID)
        ]
        
        for query, mode in test_queries:
            print(f"\n检索模式: {mode.value}")
            print(f"查询: '{query}'")
            
            config = RetrievalConfig(
                mode=mode,
                max_results=3
            )
            
            if mode == RetrievalMode.TEMPORAL:
                config.temporal_filter = TemporalFilter.THIS_WEEK
            
            results = retrieval.retrieve(query, config=config)
            
            if results:
                for i, result in enumerate(results):
                    print(f"  结果{i+1}: 分数={result.final_score:.3f}, "
                          f"语义={result.similarity_score:.3f}, "
                          f"时间={result.temporal_score:.3f}, "
                          f"情感={result.sentiment_score:.3f}")
                    print(f"      文本: {result.text[:80]}...")
            else:
                print("  无结果")
        
        # 测试时间序列分析
        print("\n时间序列分析:")
        temporal_analysis = retrieval.get_temporal_analysis(days=7)
        print(f"  总记忆数: {temporal_analysis['total_memories']}")
        print(f"  日均记忆: {temporal_analysis['average_per_day']:.1f}")
        
        if temporal_analysis['daily_counts']:
            print("  每日分布:")
            for date, count in list(temporal_analysis['daily_counts'].items())[:3]:
                print(f"    {date}: {count}个记忆")
        
        # 测试情感分析
        print("\n情感分析:")
        sentiment_analysis = retrieval.get_sentiment_analysis()
        if sentiment_analysis.get('available', False):
            print(f"  分析记忆数: {sentiment_analysis['total_analyzed']}")
            print(f"  平均情感: {sentiment_analysis['average_sentiment']:.3f}")
            print(f"  正面比例: {sentiment_analysis['positive_ratio']:.1%}")
        else:
            print("  情感分析不可用 (需要安装TextBlob)")
        
        return True
        
    except Exception as e:
        logger.error(f"高级检索测试失败: {e}")
        return False

def test_integration():
    """测试集成功能"""
    print("\n" + "="*60)
    print("测试集成功能")
    print("="*60)
    
    try:
        # 创建存储
        storage = QdrantStorage()
        
        # 创建压缩器
        compressor = FusionCompressor()
        
        # 创建检索器
        retrieval = AdvancedRetrieval(storage)
        
        # 测试数据
        test_memories = [
            {
                "text": "今天完成了ATLAS-MemoryCore Phase 1的开发，解决了OpenClaw的失忆问题。",
                "metadata": {
                    "category": "work",
                    "importance": "high",
                    "timestamp": datetime.now().isoformat(),
                    "project": "ATLAS"
                }
            },
            {
                "text": "项目会议讨论了Phase 2的开发计划，包括融合压缩引擎和高级检索功能。",
                "metadata": {
                    "category": "meeting",
                    "importance": "medium",
                    "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
                    "project": "ATLAS"
                }
            },
            {
                "text": "系统性能测试显示，检索速度提升了50%，Token成本降低了70%。",
                "metadata": {
                    "category": "test",
                    "importance": "high",
                    "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
                    "project": "ATLAS"
                }
            }
        ]
        
        # 存储记忆
        print("存储测试记忆...")
        for mem in test_memories:
            storage.store_memory(
                text=mem["text"],
                metadata=mem["metadata"],
                embedding=None  # 自动生成嵌入
            )
        
        # 测试压缩
        print("\n测试记忆压缩...")
        for mem in test_memories:
            should_compress = compressor.should_compress(mem["text"], access_frequency=0.5)
            print(f"  记忆 '{mem['text'][:30]}...' - 应该压缩: {should_compress}")
            
            if should_compress:
                result = compressor.compress_memory(mem["text"], mem["metadata"])
                print(f"    压缩比例: {result.compression_ratio:.1%}, 质量: {result.quality_score:.2f}")
        
        # 测试高级检索
        print("\n测试高级检索...")
        
        # 语义检索
        semantic_results = retrieval.retrieve(
            "ATLAS项目进展",
            mode=RetrievalMode.SEMANTIC,
            max_results=2
        )
        print(f"语义检索结果: {len(semantic_results)} 个")
        
        # 时间序列检索
        temporal_results = retrieval.retrieve(
            "最近的工作",
            mode=RetrievalMode.TEMPORAL,
            temporal_filter=TemporalFilter.THIS_WEEK,
            max_results=2
        )
        print(f"时间序列检索结果: {len(temporal_results)} 个")
        
        # 混合检索
        hybrid_results = retrieval.retrieve(
            "重要的技术成就",
            mode=RetrievalMode.HYBRID,
            max_results=2
        )
        print(f"混合检索结果: {len(hybrid_results)} 个")
        
        # 显示最佳结果
        if hybrid_results:
            best_result = hybrid_results[0]
            print(f"\n最佳匹配:")
            print(f"  分数: {best_result.final_score:.3f}")
            print(f"  文本: {best_result.text}")
            print(f"  时间: {best_result.timestamp}")
        
        return True
        
    except Exception as e:
        logger.error(f"集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("ATLAS-MemoryCore V6.0 Phase 2 功能测试")
    print("="*60)
    
    # 运行测试
    tests = [
        ("融合压缩引擎", test_fusion_compressor),
        ("高级检索功能", test_advanced_retrieval),
        ("集成功能", test_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n▶ 运行测试: {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
            status = "✅ 通过" if success else "❌ 失败"
            print(f"  结果: {status}")
        except Exception as e:
            logger.error(f"测试异常: {e}")
            results.append((test_name, False))
            print(f"  结果: ❌ 异常")
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试汇总:")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {test_name}")
    
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！Phase 2 功能验证成功。")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，需要检查。")
        return 1

if __name__ == "__main__":
    sys.exit(main())