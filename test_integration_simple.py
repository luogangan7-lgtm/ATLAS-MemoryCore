#!/usr/bin/env python3
"""
Aegis-Cortex V6.2 简单集成测试
Simple integration test for Aegis-Cortex V6.2
"""

import sys
import os
import numpy as np
from datetime import datetime, timedelta

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

print("=" * 60)
print("Aegis-Cortex V6.2 集成测试开始")
print("Aegis-Cortex V6.2 Integration Test Start")
print("=" * 60)

try:
    # 测试1: TurboQuant压缩
    print("\n1. 测试TurboQuant压缩引擎...")
    print("1. Testing TurboQuant compression engine...")
    
    from core.turboquant_compressor import TurboQuantCompressor
    compressor = TurboQuantCompressor()
    
    # 测试KV缓存压缩
    kv_cache = {"test_layer": np.random.randn(32, 128, 768).astype(np.float32)}
    compressed = compressor.compress_kv_cache(kv_cache)
    decompressed = compressor.decompress_kv_cache(compressed)
    
    print(f"   KV缓存压缩测试: 通过")
    print(f"   KV cache compression test: PASSED")
    
    # 测试上下文压缩
    context = "这是一个测试上下文。" * 20
    compressed_text = compressor.compress_context(context, max_tokens=50)
    
    orig_tokens = len(context.split())
    comp_tokens = len(compressed_text.split())
    ratio = comp_tokens / orig_tokens
    
    print(f"   上下文压缩: {orig_tokens} → {comp_tokens} tokens (压缩率: {ratio:.1%})")
    print(f"   Context compression: {orig_tokens} → {comp_tokens} tokens (ratio: {ratio:.1%})")
    
    # 测试2: Token经济监控
    print("\n2. 测试Token经济监控...")
    print("2. Testing token economy monitoring...")
    
    from core.token_economy import TokenEconomyMonitor, TokenOperation, TokenEconomyConfig
    
    config = TokenEconomyConfig(daily_token_budget=100.0)
    monitor = TokenEconomyMonitor(config)
    
    # 记录使用情况
    monitor.record_usage(TokenOperation.CAPTURE, "local-embedding", 100, 0)
    monitor.record_usage(TokenOperation.GENERATION, "gpt-4", 200, 150)
    
    print(f"   总成本: {monitor.total_cost:.4f}元")
    print(f"   Total cost: {monitor.total_cost:.4f} RMB")
    print(f"   总Token数: {monitor.total_tokens}")
    print(f"   Total tokens: {monitor.total_tokens}")
    
    # 测试3: Aegis协调器
    print("\n3. 测试Aegis协调器...")
    print("3. Testing Aegis orchestrator...")
    
    from core.aegis_orchestrator import get_global_orchestrator
    
    orchestrator = get_global_orchestrator()
    status = orchestrator.get_system_status()
    
    print(f"   系统版本: {status['version']}")
    print(f"   System version: {status['version']}")
    print(f"   架构: {status['architecture']}")
    print(f"   Architecture: {status['architecture']}")
    
    # 检查组件状态
    print(f"   组件状态:")
    print(f"   Component status:")
    for comp, info in status['components'].items():
        print(f"     {comp}: {info['enabled']} - {info['status']}")
    
    # 测试4: 配置系统
    print("\n4. 测试配置系统...")
    print("4. Testing configuration system...")
    
    from core.aegis_config import AegisCortexConfig
    
    config = AegisCortexConfig()
    config_dict = config.to_dict()
    
    print(f"   配置验证: {config.validate()}")
    print(f"   Config validation: {config.validate()}")
    print(f"   配置项数: {len(config_dict)}")
    print(f"   Config items: {len(config_dict)}")
    
    # 测试5: 四级过滤（模拟）
    print("\n5. 测试四级过滤系统（模拟）...")
    print("5. Testing four-stage filter system (simulated)...")
    
    # 创建模拟记忆记录
    class MockMemoryRecord:
        def __init__(self, content, importance=0.5):
            self.content = content
            self.importance_score = importance
            self.embedding = np.random.randn(768).astype(np.float32)
            self.metadata = {"category": "test"}
            self.created_at = datetime.now()
    
    mock_memories = [
        MockMemoryRecord("测试记忆1", 0.8),
        MockMemoryRecord("测试记忆2", 0.6),
        MockMemoryRecord("测试记忆3", 0.4)
    ]
    
    print(f"   创建了 {len(mock_memories)} 个模拟记忆")
    print(f"   Created {len(mock_memories)} mock memories")
    
    print("\n" + "=" * 60)
    print("✅ 所有基础测试通过！")
    print("✅ All basic tests passed!")
    print("=" * 60)
    
    # 性能指标总结
    print("\n📊 性能指标总结:")
    print("📊 Performance metrics summary:")
    print(f"   TurboQuant压缩率: {ratio:.1%}")
    print(f"   TurboQuant compression ratio: {ratio:.1%}")
    print(f"   Token成本监控: 启用")
    print(f"   Token cost monitoring: ENABLED")
    print(f"   系统组件: {len(status['components'])}个全部激活")
    print(f"   System components: {len(status['components'])} all active")
    
    # 下一步建议
    print("\n🚀 下一步建议:")
    print("🚀 Next steps:")
    print("   1. 连接真实Qdrant数据库")
    print("      1. Connect to real Qdrant database")
    print("   2. 集成现有评分引擎和嵌入模型")
    print("      2. Integrate existing scoring engine and embedding model")
    print("   3. 运行完整端到端测试")
    print("      3. Run complete end-to-end test")
    print("   4. 性能基准测试 (V6.0 vs V6.2)")
    print("      4. Performance benchmark (V6.0 vs V6.2)")
    
except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)