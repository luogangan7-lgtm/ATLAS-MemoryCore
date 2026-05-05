#!/usr/bin/env python3
"""
ATLAS-MemoryCore V6.0 快速测试
"""

import sys
sys.path.insert(0, '/Volumes/data/openclaw_workspace/projects/atlas-memory-core/src')

from core.lifecycle_manager import MemoryLifecycleManager, MemoryCategory, MemoryImportance

def quick_test():
    """快速测试"""
    print("🚀 ATLAS-MemoryCore V6.0 快速测试")
    print("=" * 50)
    
    try:
        # 1. 初始化管理器
        print("🔧 初始化生命周期管理器...")
        manager = MemoryLifecycleManager()
        print("✅ 初始化成功")
        
        # 2. 测试记忆捕获
        print("\n📝 测试记忆捕获...")
        memory_id = manager.capture_memory(
            text="ATLAS-MemoryCore V6.0融合架构测试成功",
            category=MemoryCategory.PROJECT,
            importance=MemoryImportance.HIGH,
            tags=["test", "v6", "fusion"]
        )
        print(f"✅ 记忆捕获成功: ID={memory_id[:8]}")
        
        # 3. 测试记忆检索
        print("\n🔍 测试记忆检索...")
        memories = manager.retrieve_memories(
            query="ATLAS融合架构",
            limit=3
        )
        print(f"✅ 找到{len(memories)}条相关记忆")
        
        for i, memory in enumerate(memories):
            print(f"  {i+1}. {memory.text[:50]}... (评分: {memory.score:.3f})")
        
        # 4. 测试统计信息
        print("\n📊 测试统计信息...")
        stats = manager.get_statistics()
        
        storage_stats = stats["storage"]
        if "error" not in storage_stats:
            print(f"✅ 记忆总数: {storage_stats.get('total_memories', 0)}")
            print(f"✅ 平均评分: {storage_stats.get('average_score', 0):.3f}")
        
        # 5. 测试优化循环
        print("\n🔄 测试优化循环...")
        manager.optimize_memories(force=True)
        print("✅ 优化循环完成")
        
        # 6. 清理测试数据
        print("\n🧹 清理测试数据...")
        manager.storage.delete_memory(memory_id)
        print("✅ 测试数据清理完成")
        
        print("\n" + "=" * 50)
        print("🎉 ATLAS-MemoryCore V6.0 快速测试通过!")
        print("✅ 融合架构核心功能正常")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = quick_test()
    sys.exit(0 if success else 1)