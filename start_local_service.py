#!/usr/bin/env python3
"""
启动本地ATLAS服务（简化版）
"""

import sys
import os
import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MemoryStorage:
    """内存存储"""
    
    def __init__(self):
        self.memories = []
        self.load_memories()
    
    def load_memories(self):
        """加载记忆"""
        try:
            data_file = os.path.expanduser("~/.atlas_memories.json")
            if os.path.exists(data_file):
                with open(data_file, 'r') as f:
                    self.memories = json.load(f)
                logger.info(f"Loaded {len(self.memories)} memories")
        except Exception as e:
            logger.error(f"Failed to load memories: {e}")
            self.memories = []
    
    def save_memories(self):
        """保存记忆"""
        try:
            data_file = os.path.expanduser("~/.atlas_memories.json")
            with open(data_file, 'w') as f:
                json.dump(self.memories, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memories: {e}")
    
    def capture(self, text: str, category: str = "general", importance: str = "medium") -> dict:
        """捕获记忆"""
        memory_id = len(self.memories) + 1
        
        memory = {
            "id": memory_id,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "importance": importance,
            "compressed": False,
            "size_bytes": len(text.encode('utf-8'))
        }
        
        self.memories.append(memory)
        self.save_memories()
        
        return {
            "success": True,
            "memory_id": memory_id,
            "message": f"Memory captured (ID: {memory_id})"
        }
    
    def search(self, query: str, limit: int = 10) -> dict:
        """搜索记忆"""
        query_lower = query.lower()
        results = []
        
        for memory in self.memories:
            if query_lower in memory["text"].lower():
                results.append(memory)
        
        return {
            "success": True,
            "query": query,
            "results": results[:limit],
            "count": len(results)
        }
    
    def list_memories(self, limit: int = 10) -> dict:
        """列出记忆"""
        recent = self.memories[-limit:] if self.memories else []
        return {
            "success": True,
            "memories": recent,
            "count": len(recent),
            "total": len(self.memories)
        }
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        total_size = sum(m.get("size_bytes", 0) for m in self.memories)
        
        return {
            "success": True,
            "stats": {
                "total_memories": len(self.memories),
                "total_size_bytes": total_size,
                "total_size_mb": total_size / (1024 * 1024),
                "average_size_bytes": total_size / len(self.memories) if self.memories else 0,
                "last_updated": datetime.now().isoformat(),
                "compression_enabled": False,
                "cache_enabled": False
            }
        }

class AtlasRequestHandler(BaseHTTPRequestHandler):
    """ATLAS HTTP请求处理器"""
    
    storage = MemoryStorage()
    
    def _send_response(self, status_code: int, data: dict):
        """发送响应"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = json.dumps(data, indent=2)
        self.wfile.write(response.encode('utf-8'))
    
    def do_GET(self):
        """处理GET请求"""
        try:
            if self.path == '/health':
                self._send_response(200, {
                    "status": "healthy",
                    "service": "ATLAS-MemoryCore V6.0",
                    "version": "6.0.0",
                    "timestamp": datetime.now().isoformat()
                })
            
            elif self.path == '/stats':
                stats = self.storage.get_stats()
                self._send_response(200, stats)
            
            elif self.path.startswith('/search'):
                # 解析查询参数
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                
                query = params.get('q', [''])[0]
                limit = int(params.get('limit', [10])[0])
                
                if not query:
                    self._send_response(400, {"error": "Query parameter 'q' is required"})
                    return
                
                results = self.storage.search(query, limit)
                self._send_response(200, results)
            
            elif self.path == '/list':
                limit = 10
                memories = self.storage.list_memories(limit)
                self._send_response(200, memories)
            
            else:
                self._send_response(404, {"error": "Endpoint not found", "available_endpoints": [
                    "/health", "/stats", "/search?q=<query>", "/list"
                ]})
        
        except Exception as e:
            logger.error(f"GET request failed: {e}")
            self._send_response(500, {"error": str(e)})
    
    def do_POST(self):
        """处理POST请求"""
        try:
            if self.path == '/capture':
                # 读取请求体
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                text = data.get('text', '')
                category = data.get('category', 'general')
                importance = data.get('importance', 'medium')
                
                if not text:
                    self._send_response(400, {"error": "Text is required"})
                    return
                
                result = self.storage.capture(text, category, importance)
                self._send_response(201, result)
            
            else:
                self._send_response(404, {"error": "Endpoint not found"})
        
        except Exception as e:
            logger.error(f"POST request failed: {e}")
            self._send_response(500, {"error": str(e)})
    
    def do_OPTIONS(self):
        """处理OPTIONS请求（CORS）"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        """自定义日志消息"""
        logger.info(f"{self.address_string()} - {format % args}")

def start_server(port: int = 8000):
    """启动HTTP服务器"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, AtlasRequestHandler)
    
    logger.info(f"🚀 ATLAS-MemoryCore V6.0 服务启动")
    logger.info(f"📡 监听端口: {port}")
    logger.info(f"🔗 健康检查: http://localhost:{port}/health")
    logger.info(f"📊 统计信息: http://localhost:{port}/stats")
    logger.info(f"🔍 搜索API: http://localhost:{port}/search?q=<query>")
    logger.info(f"💾 捕获API: POST http://localhost:{port}/capture")
    logger.info(f"📋 列表API: http://localhost:{port}/list")
    logger.info(f"\n按 Ctrl+C 停止服务")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务停止")
        httpd.server_close()

def test_service():
    """测试服务"""
    import requests
    import time
    
    # 等待服务启动
    time.sleep(2)
    
    print("\n🧪 测试ATLAS服务...")
    
    # 测试健康检查
    try:
        response = requests.get('http://localhost:8000/health', timeout=5)
        print(f"✅ 健康检查: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False
    
    # 测试捕获记忆
    try:
        data = {"text": "测试记忆: ATLAS-MemoryCore V6.0 生产部署成功", "category": "test"}
        response = requests.post('http://localhost:8000/capture', json=data, timeout=5)
        print(f"✅ 捕获记忆: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"❌ 捕获记忆失败: {e}")
    
    # 测试搜索
    try:
        response = requests.get('http://localhost:8000/search?q=ATLAS', timeout=5)
        print(f"✅ 搜索测试: {response.status_code} - 找到 {len(response.json()['results'])} 个结果")
    except Exception as e:
        print(f"❌ 搜索测试失败: {e}")
    
    # 测试统计
    try:
        response = requests.get('http://localhost:8000/stats', timeout=5)
        stats = response.json()['stats']
        print(f"✅ 统计信息: {stats['total_memories']} 个记忆, {stats['total_size_mb']:.2f} MB")
    except Exception as e:
        print(f"❌ 统计测试失败: {e}")
    
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='ATLAS-MemoryCore 本地服务')
    parser.add_argument('--port', type=int, default=8000, help='服务端口')
    parser.add_argument('--test', action='store_true', help='运行测试后退出')
    
    args = parser.parse_args()
    
    if args.test:
        # 在后台启动服务
        server_thread = threading.Thread(target=start_server, args=(args.port,), daemon=True)
        server_thread.start()
        
        # 运行测试
        test_service()
    else:
        # 启动服务
        start_server(args.port)