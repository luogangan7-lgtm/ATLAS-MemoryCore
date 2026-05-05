#!/usr/bin/env python3
"""
ATLAS Memory Core 简化测试
"""

import sys
import time
import requests
from qdrant_client import QdrantClient
from qdrant_client.http import models

def test_qdrant_connection():
    """测试Qdrant连接"""
    print("🔍 测试Qdrant连接...")
    
    try:
        # 方法1: 直接HTTP测试
        print("1. HTTP直接测试...")
        response = requests.get("http://localhost:6333/collections", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ HTTP连接成功")
            collections = response.json()["result"]["collections"]
            print(f"   现有集合: {[c['name'] for c in collections]}")
        else:
            print(f"   ❌ HTTP连接失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ HTTP测试异常: {e}")
        return False
    
    try:
        # 方法2: Qdrant客户端测试
        print("2. Qdrant客户端测试...")
        client = QdrantClient(
            host="localhost",
            port=6333,
            timeout=10,
            prefer_grpc=False  # 强制使用HTTP
        )
        
        # 获取集合列表
        collections = client.get_collections()
        print(f"   ✅ 客户端连接成功")
        print(f"   集合数量: {len(collections.collections)}")
        
        # 检查atlas_memories集合是否存在
        collection_names = [c.name for c in collections.collections]
        if "atlas_memories" in collection_names:
            print(f"   ✅ atlas_memories集合已存在")
        else:
            print(f"   ℹ️ atlas_memories集合不存在，将创建...")
            
            # 创建集合
            client.create_collection(
                collection_name="atlas_memories",
                vectors_config=models.VectorParams(
                    size=768,  # nomic-embed-text维度
                    distance=models.Distance.COSINE
                )
            )
            print(f"   ✅ atlas_memories集合创建成功")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 客户端测试异常: {e}")
        return False

def test_embedding_model():
    """测试嵌入模型"""
    print("\n🔍 测试嵌入模型...")
    
    try:
        # 避免下载，只测试导入
        from sentence_transformers import SentenceTransformer
        
        print("1. 测试SentenceTransformer导入...")
        # 不实际加载模型，只测试库
        print("   ✅ SentenceTransformer库可用")
        
        # 测试本地是否有缓存模型
        import os
        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.exists(cache_dir):
            print(f"   ℹ️ HuggingFace缓存目录: {cache_dir}")
            
            # 检查nomic模型是否已缓存
            nomic_path = os.path.join(cache_dir, "models--nomic-ai--nomic-embed-text-v1.5")
            if os.path.exists(nomic_path):
                print("   ✅ nomic-embed-text-v1.5模型已缓存")
            else:
                print("   ℹ️ nomic模型未缓存，首次使用时会下载")
        else:
            print("   ℹ️ HuggingFace缓存目录不存在")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 嵌入模型测试异常: {e}")
        return False

def test_basic_functionality():
    """测试基础功能"""
    print("\n🔍 测试基础功能...")
    
    try:
        # 测试配置模块
        print("1. 测试配置模块...")
        from atlas_memory.core.config import ConfigManager
        
        config_manager = ConfigManager()
        config = config_manager.config
        
        print(f"   ✅ 配置加载成功")
        print(f"   版本: {config.version}")
        print(f"   嵌入提供者: {config.embedding.provider}")
        
        # 修复配置
        config.storage.qdrant_url = "http://localhost:6333"
        config.storage.collection_name = "atlas_memories"
        
        print(f"   ✅ 配置修复完成")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 基础功能测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🏔️ ATLAS Memory Core 简化测试")
    print("=" * 50)
    
    all_passed = True
    
    # 测试1: Qdrant连接
    if not test_qdrant_connection():
        all_passed = False
    
    # 测试2: 嵌入模型
    if not test_embedding_model():
        all_passed = False
    
    # 测试3: 基础功能
    if not test_basic_functionality():
        all_passed = False
    
    print("\n" + "=" * 50)
    
    if all_passed:
        print("🎉 所有测试通过！ATLAS Memory Core 已就绪")
        print("\n🚀 下一步:")
        print("1. 运行完整测试: python -m atlas_memory test")
        print("2. 进入交互模式: python -m atlas_memory interactive")
        print("3. 创建示例数据: python -m atlas_memory create-sample")
    else:
        print("⚠️  部分测试失败，需要进一步调试")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())