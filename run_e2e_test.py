#!/usr/bin/env python3
"""
简化版端到端测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("🔬 Aegis-Cortex V6.2 简化端到端测试")
print("=" * 50)

# 测试核心组件
print("\n1. 测试核心组件导入...")
try:
    from src.core.scoring import MemoryScoringEngine
    from src.core.embedding import EmbeddingModel
    from src.core.lifecycle_manager import MemoryLifecycleManager
    print("✅ 核心组件导入成功")
except Exception as e:
    print(f"❌ 核心组件导入失败: {e}")
    sys.exit(1)

# 测试V6.2组件
print("\n2. 测试Aegis-Cortex V6.2组件...")
try:
    from src.core.aegis_orchestrator import get_global_orchestrator
    from src.core.turboquant_compressor import TurboQuantCompressor
    from src.core.four_stage_filter import FourStageFilter
    from src.core.token_economy import TokenEconomyMonitor
    print("✅ V6.2组件导入成功")
except Exception as e:
    print(f"❌ V6.2组件导入失败: {e}")
    sys.exit(1)

# 初始化组件
print("\n3. 初始化组件...")
try:
    # 核心组件
    scoring_engine = MemoryScoringEngine()
    embedding_model = EmbeddingModel()
    lifecycle_manager = MemoryLifecycleManager()
    
    # V6.2组件
    turboquant = TurboQuantCompressor()
    four_stage_filter = FourStageFilter()
    token_economy = TokenEconomyMonitor()
    orchestrator = get_global_orchestrator()
    
    print("✅ 所有组件初始化成功")
except Exception as e:
    print(f"❌ 组件初始化失败: {e}")
    sys.exit(1)

# 测试系统状态
print("\n4. 测试系统状态...")
try:
    status = orchestrator.get_system_status()
    print(f"✅ 系统状态检查成功")
    print(f"   版本: {status.get('version', 'N/A')}")
    print(f"   状态: {status.get('status', 'N/A')}")
    
    # 检查组件状态
    components = status.get('components', {})
    for comp, comp_status in components.items():
        active = "✅" if comp_status.get('active', False) else "❌"
        print(f"   {active} {comp}: {comp_status.get('status', 'N/A')}")
    
except Exception as e:
    print(f"❌ 系统状态检查失败: {e}")

# 测试查询处理
print("\n5. 测试查询处理...")
try:
    test_query = "如何优化AI记忆系统？"
    result = orchestrator.process_query(test_query, limit=3)
    
    if "error" in result:
        print(f"❌ 查询处理失败: {result['error']}")
    else:
        print(f"✅ 查询处理成功")
        print(f"   检索结果: {len(result.get('results', []))} 条")
        print(f"   Token使用: {result.get('token_usage', 0)}")
        print(f"   压缩率: {result.get('compression_rate', 0):.1%}")
        
        # 显示结果
        for i, item in enumerate(result.get('results', [])[:3], 1):
            content = item.get('content', '')[:50]
            print(f"   {i}. {content}...")
    
except Exception as e:
    print(f"❌ 查询处理测试失败: {e}")

# 测试Token经济
print("\n6. 测试Token经济监控...")
try:
    # 记录一些使用
    token_economy.record_usage("query", 150, "gpt-4")
    token_economy.record_usage("embedding", 50, "nomic")
    token_economy.record_usage("compression", 10, "turboquant")
    
    stats = token_economy.get_statistics()
    print(f"✅ Token经济监控正常")
    print(f"   总Token: {stats['total_tokens']}")
    print(f"   总成本: ${stats['total_cost']:.4f}")
    print(f"   平均每查询: {stats['avg_tokens_per_query']:.1f} tokens")
    
except Exception as e:
    print(f"❌ Token经济测试失败: {e}")

print("\n" + "=" * 50)
print("🎉 Aegis-Cortex V6.2 简化端到端测试完成")
print("=" * 50)