"""
ATLAS-MemoryCore V6.0 主入口点
融合架构：自优化记忆体 + Aegis-Cortex Token经济学
"""

import sys
import argparse
import time
from datetime import datetime
from typing import Optional

from core.lifecycle_manager import MemoryLifecycleManager, MemoryCategory, MemoryImportance
from core.embedding_v2 import test_embedding_model
from core.qdrant_storage import QdrantMemoryStorage


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="ATLAS-MemoryCore V6.0 - 智能记忆系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s capture "重要记忆文本" --category work --importance high
  %(prog)s search "查询内容" --limit 5
  %(prog)s optimize --force
  %(prog)s stats
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # capture命令
    capture_parser = subparsers.add_parser("capture", help="捕获记忆")
    capture_parser.add_argument("text", help="记忆文本")
    capture_parser.add_argument("--category", choices=[c.value for c in MemoryCategory], 
                               default="personal", help="记忆分类")
    capture_parser.add_argument("--importance", choices=[i.value for i in MemoryImportance], 
                               default="medium", help="重要性级别")
    capture_parser.add_argument("--tags", nargs="+", help="标签列表")
    
    # search命令
    search_parser = subparsers.add_parser("search", help="搜索记忆")
    search_parser.add_argument("query", help="查询文本")
    search_parser.add_argument("--limit", type=int, default=5, help="返回数量")
    search_parser.add_argument("--category", choices=[c.value for c in MemoryCategory], 
                              help="分类过滤")
    search_parser.add_argument("--threshold", type=float, default=0.82, 
                              help="相似度阈值")
    
    # optimize命令
    optimize_parser = subparsers.add_parser("optimize", help="优化记忆")
    optimize_parser.add_argument("--force", action="store_true", 
                                help="强制优化（忽略时间间隔）")
    
    # stats命令
    stats_parser = subparsers.add_parser("stats", help="显示统计信息")
    
    # test命令
    test_parser = subparsers.add_parser("test", help="运行测试")
    test_parser.add_argument("--embedding", action="store_true", help="测试嵌入模型")
    test_parser.add_argument("--storage", action="store_true", help="测试存储")
    test_parser.add_argument("--lifecycle", action="store_true", help="测试生命周期")
    test_parser.add_argument("--all", action="store_true", help="运行所有测试")
    
    # backup命令
    backup_parser = subparsers.add_parser("backup", help="备份数据")
    backup_parser.add_argument("--dir", default="./backup", help="备份目录")
    
    # restore命令
    restore_parser = subparsers.add_parser("restore", help="恢复数据")
    restore_parser.add_argument("--dir", required=True, help="备份目录")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 初始化管理器
    manager = MemoryLifecycleManager()
    
    try:
        if args.command == "capture":
            handle_capture(manager, args)
        elif args.command == "search":
            handle_search(manager, args)
        elif args.command == "optimize":
            handle_optimize(manager, args)
        elif args.command == "stats":
            handle_stats(manager)
        elif args.command == "test":
            handle_test(args)
        elif args.command == "backup":
            handle_backup(manager, args)
        elif args.command == "restore":
            handle_restore(manager, args)
            
    except KeyboardInterrupt:
        print("\n\n👋 操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)


def handle_capture(manager: MemoryLifecycleManager, args):
    """处理捕获命令"""
    print(f"📝 捕获记忆...")
    
    # 解析参数
    category = MemoryCategory(args.category)
    importance = MemoryImportance(args.importance)
    
    # 捕获记忆
    memory_id = manager.capture_memory(
        text=args.text,
        category=category,
        importance=importance,
        tags=args.tags
    )
    
    print(f"✅ 记忆捕获成功!")
    print(f"   ID: {memory_id}")
    print(f"   分类: {category.value}")
    print(f"   重要性: {importance.value}")
    print(f"   标签: {args.tags or '无'}")


def handle_search(manager: MemoryLifecycleManager, args):
    """处理搜索命令"""
    print(f"🔍 搜索记忆: '{args.query}'")
    
    # 解析参数
    category = MemoryCategory(args.category) if args.category else None
    
    # 搜索记忆
    memories = manager.retrieve_memories(
        query=args.query,
        limit=args.limit,
        category=category,
        similarity_threshold=args.threshold
    )
    
    if not memories:
        print("📭 未找到相关记忆")
        return
    
    print(f"📚 找到{len(memories)}条相关记忆:")
    
    for i, memory in enumerate(memories):
        print(f"\n{i+1}. {'⭐' * int(memory.score * 5)} 评分: {memory.score:.3f}")
        print(f"   分类: {memory.metadata.category.value}")
        print(f"   重要性: {memory.metadata.importance.value}")
        print(f"   创建: {datetime.fromtimestamp(memory.metadata.created_at).strftime('%Y-%m-%d %H:%M')}")
        print(f"   最后访问: {datetime.fromtimestamp(memory.metadata.last_accessed).strftime('%Y-%m-%d %H:%M')}")
        print(f"   访问次数: {memory.metadata.access_count}")
        print(f"   内容: {memory.text[:100]}..." if len(memory.text) > 100 else f"   内容: {memory.text}")
        
        if memory.metadata.tags:
            print(f"   标签: {', '.join(memory.metadata.tags)}")


def handle_optimize(manager: MemoryLifecycleManager, args):
    """处理优化命令"""
    print("🔄 开始记忆优化...")
    
    manager.optimize_memories(force=args.force)
    
    print("✅ 记忆优化完成")


def handle_stats(manager: MemoryLifecycleManager):
    """处理统计命令"""
    print("📊 记忆系统统计信息:")
    
    stats = manager.get_statistics()
    
    # 存储统计
    storage = stats["storage"]
    if "error" in storage:
        print(f"❌ 存储错误: {storage['error']}")
    else:
        print(f"\n💾 存储统计:")
        print(f"  记忆总数: {storage.get('total_memories', 0)}")
        print(f"  平均评分: {storage.get('average_score', 0):.3f}")
        print(f"  向量数量: {storage.get('vectors_count', 0)}")
        
        if "categories" in storage:
            print(f"  分类分布:")
            for cat, count in storage["categories"].items():
                print(f"    {cat}: {count}")
        
        if "importances" in storage:
            print(f"  重要性分布:")
            for imp, count in storage["importances"].items():
                print(f"    {imp}: {count}")
    
    # 生命周期事件
    events = stats["lifecycle_events"]
    print(f"\n📈 生命周期事件:")
    print(f"  事件总数: {events['total']}")
    if "by_stage" in events:
        print(f"  阶段分布:")
        for stage, count in events["by_stage"].items():
            print(f"    {stage}: {count}")
    
    # 嵌入模型信息
    embedding = stats["embedding_model"]
    print(f"\n🤖 嵌入模型:")
    print(f"  模型类型: {embedding.get('model_type', 'unknown')}")
    print(f"  向量维度: {embedding.get('vector_size', 0)}")
    print(f"  缓存大小: {embedding.get('cache_size', 0)}")
    
    # 配置信息
    config = stats["config"]
    print(f"\n⚙️  系统配置:")
    print(f"  升级阈值: {config.get('upgrade_threshold', 0.85)}")
    print(f"  遗忘阈值: {config.get('forget_threshold', 0.3)}")
    print(f"  最大年龄: {config.get('max_age_days', 7)}天")
    print(f"  最后优化: {stats.get('last_optimization', '从未')}")


def handle_test(args):
    """处理测试命令"""
    if args.all or args.embedding:
        print("🧪 测试嵌入模型...")
        test_embedding_model()
    
    if args.all or args.storage:
        print("\n🧪 测试存储系统...")
        test_storage()
    
    if args.all or args.lifecycle:
        print("\n🧪 测试生命周期管理器...")
        from core.lifecycle_manager import test_lifecycle_manager
        test_lifecycle_manager()
    
    if not any([args.all, args.embedding, args.storage, args.lifecycle]):
        print("请指定测试类型，或使用 --all 运行所有测试")


def test_storage():
    """测试存储系统"""
    try:
        storage = QdrantMemoryStorage()
        
        # 测试存储
        print("📝 测试记忆存储...")
        
        # 创建测试向量
        test_vector = [0.1] * 768
        
        memory_id = storage.store_memory(
            text="测试记忆内容",
            embedding=test_vector,
            category=MemoryCategory.SYSTEM,
            importance=MemoryImportance.MEDIUM,
            tags=["test", "storage"]
        )
        
        print(f"  存储成功，ID: {memory_id}")
        
        # 测试检索
        print("🔍 测试记忆检索...")
        memories = storage.search_memories(
            query_embedding=test_vector,
            limit=3
        )
        
        print(f"  检索到{len(memories)}条记忆")
        
        # 测试统计
        print("📊 测试统计信息...")
        stats = storage.get_statistics()
        print(f"  统计: {stats}")
        
        # 清理测试数据
        storage.delete_memory(memory_id)
        
        print("✅ 存储系统测试完成")
        
    except Exception as e:
        print(f"❌ 存储测试失败: {e}")


def handle_backup(manager: MemoryLifecycleManager, args):
    """处理备份命令"""
    print(f"💾 备份数据到 {args.dir}...")
    
    manager.export_backup(args.dir)
    
    print("✅ 备份完成")


def handle_restore(manager: MemoryLifecycleManager, args):
    """处理恢复命令"""
    print(f"📥 从 {args.dir} 恢复数据...")
    
    manager.import_backup(args.dir)
    
    print("✅ 恢复完成")


if __name__ == "__main__":
    main()