"""
ATLAS Memory Core 主入口点 - Main Entry Point
提供命令行接口和快速启动功能
Provides command line interface and quick start functionality
"""

import sys
import argparse
import logging
from typing import Optional

from .core.config import ConfigManager, get_config_manager
from .core.embedding import EmbeddingModel
from .core.storage import MemoryStorage
from .core.retrieval import MemoryRetrieval, create_retrieval_system
from .core.scoring import MemoryScoring, create_scoring_system

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """设置日志配置 - Setup logging configuration"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )


def test_connection(config_path: Optional[str] = None):
    """测试系统连接 - Test system connections"""
    print("🔍 测试系统连接...")
    
    try:
        # 测试配置
        config_manager = get_config_manager(config_path)
        config = config_manager.config
        print(f"✅ 配置加载成功: {config.version}")
        
        # 测试嵌入模型
        print("🧠 测试嵌入模型...")
        embedding = EmbeddingModel()
        test_text = "测试文本"
        vector = embedding.encode_single(test_text)
        print(f"✅ 嵌入模型正常，维度: {len(vector)}")
        
        # 测试存储连接
        print("💾 测试存储连接...")
        storage = MemoryStorage(
            qdrant_url=config.storage.qdrant_url,
            collection_name=config.storage.collection_name,
            embedding_model=embedding,
            vector_size=config_manager.get_embedding_dimension()
        )
        stats = storage.get_stats()
        print(f"✅ 存储连接正常: {stats.get('total_memories', 0)} 条记忆")
        
        # 测试检索系统
        print("🔎 测试检索系统...")
        retrieval = create_retrieval_system(
            qdrant_url=config.storage.qdrant_url,
            collection_name=config.storage.collection_name,
            config_path=config_path
        )
        print("✅ 检索系统正常")
        
        # 测试评分系统
        print("📊 测试评分系统...")
        scoring = create_scoring_system(config_path)
        print("✅ 评分系统正常")
        
        print("\n🎉 所有系统测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def interactive_mode(config_path: Optional[str] = None):
    """交互模式 - Interactive mode"""
    print("🏔️ ATLAS Memory Core 交互模式")
    print("=" * 50)
    
    # 初始化系统
    try:
        retrieval = create_retrieval_system(config_path=config_path)
        scoring = create_scoring_system(config_path)
        
        from .core.storage import MemoryStorage, MemoryMetadata, MemoryCategory
        storage = retrieval.memory_storage
        
        print("✅ 系统初始化完成")
        print(f"📊 当前记忆数量: {storage.get_stats().get('total_memories', 0)}")
        print()
        
    except Exception as e:
        print(f"❌ 系统初始化失败: {e}")
        return
    
    while True:
        print("\n请选择操作:")
        print("  1. 存储记忆")
        print("  2. 搜索记忆")
        print("  3. 查看统计")
        print("  4. 测试评分")
        print("  5. 退出")
        
        try:
            choice = input("\n请输入选项 (1-5): ").strip()
            
            if choice == "1":
                # 存储记忆
                text = input("请输入记忆内容: ").strip()
                if not text:
                    print("❌ 记忆内容不能为空")
                    continue
                
                category_input = input("请输入分类 (learning/trading/code/personal/work/project/other): ").strip()
                try:
                    category = MemoryCategory(category_input.lower())
                except ValueError:
                    category = MemoryCategory.OTHER
                    print(f"⚠️  使用默认分类: {category.value}")
                
                importance_input = input("请输入重要性 (0.0-1.0，默认0.5): ").strip()
                try:
                    importance = float(importance_input) if importance_input else 0.5
                    importance = max(0.0, min(1.0, importance))
                except ValueError:
                    importance = 0.5
                    print(f"⚠️  使用默认重要性: {importance}")
                
                tags_input = input("请输入标签 (逗号分隔，可选): ").strip()
                tags = [tag.strip() for tag in tags_input.split(",")] if tags_input else []
                
                metadata = MemoryMetadata(
                    category=category,
                    importance=importance,
                    tags=tags
                )
                
                memory_id = storage.store(text, metadata)
                print(f"✅ 记忆存储成功: {memory_id[:8]}")
            
            elif choice == "2":
                # 搜索记忆
                query = input("请输入搜索查询: ").strip()
                if not query:
                    print("❌ 搜索查询不能为空")
                    continue
                
                limit_input = input("请输入返回数量 (默认5): ").strip()
                limit = int(limit_input) if limit_input.isdigit() else 5
                
                threshold_input = input("请输入相似度阈值 (0.0-1.0，默认0.7): ").strip()
                try:
                    threshold = float(threshold_input) if threshold_input else 0.7
                    threshold = max(0.0, min(1.0, threshold))
                except ValueError:
                    threshold = 0.7
                
                results = retrieval.search(query, limit=limit, threshold=threshold, explain=True)
                
                if results:
                    print(f"\n🔍 找到 {len(results)} 条相关记忆:")
                    for i, result in enumerate(results, 1):
                        print(f"\n{i}. [{result.relevance:.2f}] {result.memory.text[:100]}...")
                        print(f"   分类: {result.memory.metadata.category.value}")
                        print(f"   重要性: {result.memory.metadata.importance:.2f}")
                        print(f"   解释: {result.explanation}")
                else:
                    print("❌ 未找到相关记忆")
            
            elif choice == "3":
                # 查看统计
                stats = storage.get_stats()
                print("\n📊 系统统计:")
                for key, value in stats.items():
                    print(f"  {key}: {value}")
                
                cache_stats = retrieval.get_cache_stats()
                print("\n📦 缓存统计:")
                for key, value in cache_stats.items():
                    print(f"  {key}: {value}")
            
            elif choice == "4":
                # 测试评分
                # 获取一些记忆进行评分
                from .core.storage import MemoryCategory
                
                test_memories = []
                for category in MemoryCategory:
                    memories = retrieval.search_by_category(category, limit=2)
                    test_memories.extend(memories)
                
                if test_memories:
                    print(f"\n📊 测试 {len(test_memories)} 条记忆的评分:")
                    for memory in test_memories[:5]:  # 只显示前5条
                        score = scoring.calculate_score(memory)
                        print(f"\n  ID: {memory.id[:8]}")
                        print(f"  文本: {memory.text[:80]}...")
                        print(f"  分类: {memory.metadata.category.value}")
                        print(f"  重要性: {memory.metadata.importance:.2f}")
                        print(f"  评分: {score:.3f}")
                else:
                    print("❌ 没有可测试的记忆")
            
            elif choice == "5":
                print("👋 退出交互模式")
                break
            
            else:
                print("❌ 无效选项")
        
        except KeyboardInterrupt:
            print("\n👋 用户中断")
            break
        except Exception as e:
            print(f"❌ 操作失败: {e}")


def create_sample_data(config_path: Optional[str] = None):
    """创建示例数据 - Create sample data"""
    print("📝 创建示例数据...")
    
    try:
        retrieval = create_retrieval_system(config_path=config_path)
        storage = retrieval.memory_storage
        
        from .core.storage import MemoryMetadata, MemoryCategory
        
        sample_memories = [
            {
                "text": "今天学习了Python异步编程，asyncio库非常强大，可以高效处理并发任务",
                "metadata": MemoryMetadata(
                    category=MemoryCategory.LEARNING,
                    importance=0.8,
                    tags=["python", "async", "asyncio", "concurrency"]
                )
            },
            {
                "text": "比特币价格突破70,000美元，市场情绪乐观，可以考虑分批建仓",
                "metadata": MemoryMetadata(
                    category=MemoryCategory.TRADING,
                    importance=0.9,
                    tags=["bitcoin", "trading", "crypto", "investment"]
                )
            },
            {
                "text": "完成了OpenClaw Skill开发文档，准备发布到GitHub，使用MIT许可证",
                "metadata": MemoryMetadata(
                    category=MemoryCategory.PROJECT,
                    importance=0.7,
                    tags=["openclaw", "github", "documentation", "opensource"]
                )
            },
            {
                "text": "使用Qdrant向量数据库存储AI记忆，性能很好，支持混合搜索",
                "metadata": MemoryMetadata(
                    category=MemoryCategory.CODE,
                    importance=0.6,
                    tags=["qdrant", "vector-database", "ai", "search"]
                )
            },
            {
                "text": "明天上午10点有团队会议，需要准备项目进度报告",
                "metadata": MemoryMetadata(
                    category=MemoryCategory.WORK,
                    importance=0.5,
                    tags=["meeting", "work", "schedule"]
                )
            },
        ]
        
        created_count = 0
        for memory_data in sample_memories:
            try:
                memory_id = storage.store(
                    text=memory_data["text"],
                    metadata=memory_data["metadata"]
                )
                created_count += 1
                print(f"  ✅ 创建: {memory_data['text'][:50]}...")
            except Exception as e:
                print(f"  ❌ 失败: {e}")
        
        print(f"\n🎉 示例数据创建完成: {created_count}/{len(sample_memories)} 条")
        
        # 测试搜索
        print("\n🔍 测试搜索功能...")
        results = retrieval.search("Python编程", limit=2)
        if results:
            print("✅ 搜索功能正常")
        else:
            print("⚠️  搜索未返回结果")
        
        return True
        
    except Exception as e:
        print(f"❌ 创建示例数据失败: {e}")
        return False


def main():
    """主函数 - Main function"""
    parser = argparse.ArgumentParser(
        description="ATLAS Memory Core - 零Token智能记忆系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s test                    # 测试系统连接
  %(prog)s interactive             # 进入交互模式
  %(prog)s create-sample           # 创建示例数据
  %(prog)s --config ./config.yaml  # 使用指定配置文件
        """
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        choices=["test", "interactive", "create-sample", "help"],
        default="interactive",
        help="执行命令 (默认: interactive)"
    )
    
    parser.add_argument(
        "--config",
        "-c",
        help="配置文件路径"
    )
    
    parser.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别 (默认: INFO)"
    )
    
    parser.add_argument(
        "--log-file",
        help="日志文件路径"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.log_level, args.log_file)
    
    # 显示欢迎信息
    print("🏔️ ATLAS Memory Core v0.1.0")
    print("=" * 50)
    
    # 执行命令
    if args.command == "test":
        success = test_connection(args.config)
        sys.exit(0 if success else 1)
    
    elif args.command == "interactive":
        interactive_mode(args.config)
    
    elif args.command == "create-sample":
        success = create_sample_data(args.config)
        sys.exit(0 if success else 1)
    
    elif args.command == "help":
        parser.print_help()
    
    else:
        print(f"未知命令: {args.command}")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 程序被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 程序运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)