"""
ATLAS Memory Core - 基础示例
展示基本的内存存储和检索功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas_memory.core.storage import MemoryStorage, MemoryMetadata, MemoryCategory
from atlas_memory.core.embedding import EmbeddingModel


def main():
    print("🏔️ ATLAS Memory Core - 基础示例")
    print("=" * 50)
    
    # 1. 初始化记忆存储
    print("1. 初始化记忆存储系统...")
    memory_storage = MemoryStorage(
        qdrant_url="http://localhost:6333",
        collection_name="atlas_memories_demo"
    )
    
    # 2. 存储一些记忆
    print("\n2. 存储记忆...")
    
    memories = [
        {
            "text": "今天学习了Python异步编程，asyncio库非常强大",
            "metadata": MemoryMetadata(
                category=MemoryCategory.LEARNING,
                importance=0.8,
                tags=["python", "async", "asyncio"]
            )
        },
        {
            "text": "比特币价格突破70,000美元，市场情绪乐观",
            "metadata": MemoryMetadata(
                category=MemoryCategory.TRADING,
                importance=0.9,
                tags=["bitcoin", "trading", "crypto"]
            )
        },
        {
            "text": "完成了OpenClaw Skill开发文档，准备发布到GitHub",
            "metadata": MemoryMetadata(
                category=MemoryCategory.PROJECT,
                importance=0.7,
                tags=["openclaw", "github", "documentation"]
            )
        },
        {
            "text": "使用Qdrant向量数据库存储AI记忆，性能很好",
            "metadata": MemoryMetadata(
                category=MemoryCategory.CODE,
                importance=0.6,
                tags=["qdrant", "vector-database", "ai"]
            )
        }
    ]
    
    memory_ids = []
    for mem in memories:
        memory_id = memory_storage.store(
            text=mem["text"],
            metadata=mem["metadata"]
        )
        memory_ids.append(memory_id)
        print(f"  存储: {mem['text'][:50]}... (ID: {memory_id[:8]})")
    
    # 3. 检索单个记忆
    print("\n3. 检索单个记忆...")
    if memory_ids:
        memory = memory_storage.retrieve(memory_ids[0])
        if memory:
            print(f"  检索到: {memory.text}")
            print(f"  分类: {memory.metadata.category.value}")
            print(f"  重要性: {memory.metadata.importance}")
            print(f"  标签: {', '.join(memory.metadata.tags)}")
    
    # 4. 搜索相关记忆
    print("\n4. 搜索相关记忆...")
    
    queries = [
        "Python编程学习",
        "加密货币交易",
        "向量数据库技术"
    ]
    
    for query in queries:
        print(f"\n  查询: '{query}'")
        results = memory_storage.search(query, limit=2, threshold=0.5)
        
        if results:
            for i, result in enumerate(results, 1):
                print(f"    {i}. [{result.score:.2f}] {result.text}")
        else:
            print("    未找到相关记忆")
    
    # 5. 获取统计信息
    print("\n5. 系统统计信息...")
    stats = memory_storage.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # 6. 清理（可选）
    print("\n6. 清理测试数据...")
    response = input("  是否删除测试数据？(y/N): ")
    if response.lower() == 'y':
        for memory_id in memory_ids:
            memory_storage.delete(memory_id)
        print("  测试数据已删除")
    else:
        print("  保留测试数据")
    
    print("\n✅ 基础示例完成！")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 示例运行失败: {e}")
        print("\n💡 可能的原因：")
        print("  1. Qdrant服务未启动")
        print("  2. 网络连接问题")
        print("  3. 依赖包未安装")
        print("\n🔧 解决方案：")
        print("  1. 启动Qdrant: docker run -p 6333:6333 qdrant/qdrant")
        print("  2. 安装依赖: pip install -e .")
        print("  3. 检查网络: curl http://localhost:6333")