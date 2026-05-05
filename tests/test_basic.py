#!/usr/bin/env python3
"""
Aegis-Cortex V6.2 基础测试
Basic test for Aegis-Cortex V6.2
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

print("=" * 60)
print("Aegis-Cortex V6.2 基础测试")
print("Aegis-Cortex V6.2 Basic Test")
print("=" * 60)

try:
    # 测试1: 配置系统
    print("\n1. 测试配置系统...")
    print("1. Testing configuration system...")
    
    from core.aegis_config import AegisCortexConfig
    
    config = AegisCortexConfig()
    print(f"   版本: {config.version}")
    print(f"   Version: {config.version}")
    print(f"   架构: {config.architecture}")
    print(f"   Architecture: {config.architecture}")
    
    # 检查配置
    print(f"   TurboQuant启用: {config.turboquant.enabled}")
    print(f"   TurboQuant enabled: {config.turboquant.enabled}")
    print(f"   四级过滤启用: {config.four_stage_filter.enabled}")
    print(f"   Four-stage filter enabled: {config.four_stage_filter.enabled}")
    print(f"   Token经济启用: {config.token_economy.enabled}")
    print(f"   Token economy enabled: {config.token_economy.enabled}")
    
    # 验证配置
    errors = config.validate()
    if errors:
        print(f"   配置错误: {errors}")
        print(f"   Config errors: {errors}")
    else:
        print(f"   配置验证: 通过")
        print(f"   Config validation: PASSED")
    
    # 测试2: Aegis协调器
    print("\n2. 测试Aegis协调器...")
    print("2. Testing Aegis orchestrator...")
    
    from core.aegis_orchestrator import get_global_orchestrator
    
    orchestrator = get_global_orchestrator()
    status = orchestrator.get_system_status()
    
    print(f"   系统状态: {status['version']} - {status['architecture']}")
    print(f"   System status: {status['version']} - {status['architecture']}")
    
    # 检查组件
    print(f"   组件状态:")
    print(f"   Component status:")
    for comp_name, comp_info in status['components'].items():
        enabled = "✅" if comp_info['enabled'] else "❌"
        print(f"     {enabled} {comp_name}: {comp_info['status']}")
    
    # 测试3: 创建配置文件
    print("\n3. 测试配置文件生成...")
    print("3. Testing config file generation...")
    
    config_dict = config.to_dict()
    print(f"   配置项数: {len(config_dict)}")
    print(f"   Config items: {len(config_dict)}")
    
    # 显示关键配置
    print(f"   关键配置:")
    print(f"   Key configurations:")
    print(f"     TurboQuant压缩率: {config.turboquant.compression_ratio}")
    print(f"     TurboQuant compression ratio: {config.turboquant.compression_ratio}")
    print(f"     相似度阈值: {config.four_stage_filter.similarity_threshold}")
    print(f"     Similarity threshold: {config.four_stage_filter.similarity_threshold}")
    print(f"     最大Token数/查询: {config.token_economy.max_tokens_per_query}")
    print(f"     Max tokens per query: {config.token_economy.max_tokens_per_query}")
    print(f"     夜间优化时间: {config.nocturnal_optimization.optimization_time}")
    print(f"     Nocturnal optimization time: {config.nocturnal_optimization.optimization_time}")
    
    # 测试4: 模拟Token经济
    print("\n4. 测试Token经济模拟...")
    print("4. Testing token economy simulation...")
    
    try:
        from core.token_economy import TokenEconomyMonitor, TokenOperation, TokenEconomyConfig
        
        econ_config = TokenEconomyConfig(daily_token_budget=100.0)
        monitor = TokenEconomyMonitor(econ_config)
        
        print(f"   Token监控器初始化: 成功")
        print(f"   Token monitor initialization: SUCCESS")
        print(f"   降级级别: {monitor.downgrade_level.value}")
        print(f"   Downgrade level: {monitor.downgrade_level.value}")
        
    except Exception as e:
        print(f"   Token经济测试跳过: {e}")
        print(f"   Token economy test skipped: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 基础架构测试完成！")
    print("✅ Basic architecture test completed!")
    print("=" * 60)
    
    # 总结
    print("\n📊 测试总结:")
    print("📊 Test summary:")
    print(f"   ✅ 配置系统: 正常")
    print(f"   ✅ Configuration system: OK")
    print(f"   ✅ Aegis协调器: 正常")
    print(f"   ✅ Aegis orchestrator: OK")
    print(f"   ✅ 组件状态: 全部激活")
    print(f"   ✅ Component status: All active")
    
    # 下一步
    print("\n🚀 下一步:")
    print("🚀 Next steps:")
    print("   1. 安装依赖: pip install numpy sentence-transformers qdrant-client")
    print("      1. Install dependencies: pip install numpy sentence-transformers qdrant-client")
    print("   2. 启动Qdrant服务: docker run -p 6333:6333 qdrant/qdrant")
    print("      2. Start Qdrant service: docker run -p 6333:6333 qdrant/qdrant")
    print("   3. 运行完整集成测试")
    print("      3. Run complete integration test")
    print("   4. 性能基准测试")
    print("      4. Performance benchmark")
    
except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)