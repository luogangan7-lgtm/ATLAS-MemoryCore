#!/usr/bin/env python3
"""
ATLAS-MemoryCore V6.0 简单测试（使用降级模型）
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/src')

def test_basic_functionality():
    """测试基本功能"""
    print("🧪 ATLAS-MemoryCore V6.0 基本功能测试")
    print("=" * 50)
    
    try:
        # 1. 测试嵌入模型（降级模式）
        print("\n🔤 测试嵌入模型...")
        from core.embedding_v2 import EnhancedEmbeddingModel, EmbeddingConfig, EmbeddingModelType
        
        # 强制使用降级模型
        config = EmbeddingConfig(model_type=EmbeddingModelType.FALLBACK)
        model = EnhancedEmbeddingModel(config)
        
        info = model.get_model_info()
        print(f"✅ 嵌入模型初始化: {info['model_type']}")
        
        # 测试编码
        text = "测试文本"
        embedding = model.encode_single(text)
        print(f"✅ 编码测试: 维度={len(embedding)}")
        
        # 2. 测试存储
        print("\n💾 测试存储系统...")
        from core.qdrant_storage import QdrantMemoryStorage, MemoryCategory, MemoryImportance
        
        storage = QdrantMemoryStorage()
        print("✅ 存储系统初始化")
        
        # 3. 测试记忆捕获和检索
        print("\n📝 测试记忆生命周期...")
        from core.lifecycle_manager import MemoryLifecycleManager
        
        manager = MemoryLifecycleManager()
        print("✅ 生命周期管理器初始化")
        
        # 捕获记忆
        memory_id = manager.capture_memory(
            text="简单测试记忆",
            category=MemoryCategory.SYSTEM,
            importance=MemoryImportance.MEDIUM,
            tags=["test", "simple"]
        )
        print(f"✅ 记忆捕获: ID={memory_id[:8]}")
        
        # 检索记忆
        memories = manager.retrieve_memories(
            query="测试",
            limit=3
        )
        print(f"✅ 记忆检索: 找到{len(memories)}条")
        
        # 显示记忆
        for i, memory in enumerate(memories):
            print(f"  {i+1}. {memory.text[:30]}... (评分: {memory.score:.3f})")
        
        # 统计信息
        stats = manager.get_statistics()
        print(f"✅ 系统统计: {stats['storage'].get('total_memories', 0)}条记忆")
        
        # 清理
        manager.storage.delete_memory(memory_id)
        print("✅ 测试数据清理完成")
        
        print("\n" + "=" * 50)
        print("🎉 基本功能测试通过!")
        print("✅ 降级嵌入模型工作正常")
        print("✅ Qdrant存储工作正常")
        print("✅ 记忆生命周期管理正常")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_command_line():
    """测试命令行接口"""
    print("\n💻 测试命令行接口...")
    print("-" * 30)
    
    try:
        # 测试直接导入
        import subprocess
        
        # 运行帮助命令
        result = subprocess.run(
            [sys.executable, "-m", "src", "--help"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            print("✅ 命令行帮助正常")
            return True
        else:
            print(f"❌ 命令行帮助失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 命令行测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 开始ATLAS-MemoryCore V6.0测试...")
    
    # 测试基本功能
    func_success = test_basic_functionality()
    
    # 测试命令行
    cli_success = test_command_line()
    
    print("\n" + "=" * 50)
    print("📋 测试结果总结:")
    print(f"  基本功能测试: {'✅ 通过' if func_success else '❌ 失败'}")
    print(f"  命令行接口测试: {'✅ 通过' if cli_success else '❌ 失败'}")
    
    if func_success and cli_success:
        print("\n🎯 开发进度:")
        print("  ✅ Phase 1: 基础架构升级 - 完成")
        print("  ✅ 零Token捕获层: 实现")
        print("  ✅ 惰性检索引擎: 实现")
        print("  ✅ 记忆生命周期管理: 实现")
        print("  ⏳ Phase 2: 智能功能增强 - 待开始")
        print("  ⏳ 融合压缩引擎: 待实现")
        print("  ⏳ 夜间自优化循环: 基础实现")
        
        print("\n📋 下一步:")
        print("  1. 配置Nomic API token以启用高质量嵌入")
        print("  2. 实现融合压缩引擎（Qwen2.5-7B集成）")
        print("  3. 完善API文档和使用指南")
        print("  4. 部署生产环境")
        
        sys.exit(0)
    else:
        print("\n❌ 测试失败，请修复问题")
        sys.exit(1)

if __name__ == "__main__":
    main()