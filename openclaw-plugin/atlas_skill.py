"""
ATLAS-MemoryCore OpenClaw Skill
桥接 atlas-memory-core 项目，提供真实 Qdrant + 向量嵌入支持
"""

import json
import sys
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 将 atlas-memory-core 加入模块搜索路径
ATLAS_CORE_SRC = "/Volumes/data/openclaw_workspace/projects/atlas-memory-core/src"
if ATLAS_CORE_SRC not in sys.path:
    sys.path.insert(0, ATLAS_CORE_SRC)

# 延迟初始化，避免 OpenClaw 启动时阻塞
_manager = None

def _get_manager():
    """获取或初始化 MemoryLifecycleManager（惰性加载）"""
    global _manager
    if _manager is None:
        # 绕过 macOS 系统代理，确保直连本地 Qdrant
        os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
        os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
        try:
            from core.lifecycle_manager import MemoryLifecycleManager
            _manager = MemoryLifecycleManager(
                url="http://localhost:6333",
                qmd_path="/Users/luolimo/OpenClaw/workspace/memory/atlas_promoted.md"
            )
            logger.info("ATLAS MemoryLifecycleManager 初始化成功")
        except Exception as e:
            logger.error(f"ATLAS MemoryLifecycleManager 初始化失败: {e}")
            raise
    return _manager


def _infer_category(text: str):
    """根据内容自动推断记忆分类"""
    from core.qdrant_storage import MemoryCategory
    text_lower = text.lower()
    if any(k in text_lower for k in ["交易", "买入", "卖出", "仓位", "止损", "行情", "k线", "ma", "macd", "rsi", "trade", "signal"]):
        return MemoryCategory.WORK  # 交易类映射到 WORK
    if any(k in text_lower for k in ["代码", "bug", "fix", "function", "class", "import", "python", "js", "api", "debug", "error"]):
        return MemoryCategory.PROJECT
    if any(k in text_lower for k in ["学习", "笔记", "总结", "理解", "概念", "原理", "课程", "书", "文档"]):
        return MemoryCategory.LEARNING
    if any(k in text_lower for k in ["系统", "配置", "openclaw", "qdrant", "qmd", "服务器", "部署", "agent"]):
        return MemoryCategory.SYSTEM
    if any(k in text_lower for k in ["项目", "任务", "计划", "进度", "里程碑", "需求", "deadline"]):
        return MemoryCategory.PROJECT
    return MemoryCategory.PERSONAL


def _infer_importance(text: str, explicit: str = None):
    """根据内容自动推断重要性"""
    from core.qdrant_storage import MemoryImportance
    if explicit:
        mapping = {
            "critical": MemoryImportance.CRITICAL,
            "high": MemoryImportance.HIGH,
            "medium": MemoryImportance.MEDIUM,
            "low": MemoryImportance.LOW,
        }
        if explicit.lower() in mapping:
            return mapping[explicit.lower()]

    text_lower = text.lower()
    if any(k in text_lower for k in ["重要", "关键", "紧急", "必须", "核心", "critical", "urgent"]):
        return MemoryImportance.HIGH
    if any(k in text_lower for k in ["注意", "记住", "提醒", "不要忘"]):
        return MemoryImportance.MEDIUM
    if len(text) > 300:
        return MemoryImportance.MEDIUM
    return MemoryImportance.MEDIUM


class AtlasSkill:
    """ATLAS-MemoryCore OpenClaw Skill — Qdrant 向量记忆后端"""

    def handle_command(self, command: str, args: list) -> dict:
        cmd = command.lower().strip()
        # 同时支持 SKILL.md 的 /memory 前缀风格和直接命令
        if cmd.startswith("memory "):
            cmd = cmd[7:].strip()

        handlers = {
            "store":    self._handle_store,
            "capture":  self._handle_store,   # 别名
            "search":   self._handle_search,
            "list":     self._handle_list,
            "stats":    self._handle_stats,
            "optimize": self._handle_optimize,
            "clear":    self._handle_clear,
            "export":   self._handle_export,
            "import":   self._handle_import,
            "debug":    self._handle_debug,
            "help":     self._handle_help,
        }
        handler = handlers.get(cmd)
        if handler is None:
            return {
                "error": f"未知命令: {cmd}",
                "available": list(handlers.keys())
            }
        try:
            return handler(args)
        except Exception as e:
            logger.error(f"命令 {cmd} 执行失败: {e}", exc_info=True)
            return {"error": str(e), "command": cmd}

    def _handle_store(self, args: list) -> dict:
        """存储记忆到 Qdrant（带向量嵌入）"""
        if not args:
            return {"error": "请提供记忆内容"}
        text = " ".join(args)

        # 解析可选参数 --category --importance --tags
        importance_str = None
        category_str = None
        tags = []
        clean_parts = []
        i = 0
        while i < len(args):
            if args[i] == "--importance" and i + 1 < len(args):
                importance_str = args[i + 1]; i += 2
            elif args[i] == "--category" and i + 1 < len(args):
                category_str = args[i + 1]; i += 2
            elif args[i] == "--tags" and i + 1 < len(args):
                tags = args[i + 1].split(","); i += 2
            else:
                clean_parts.append(args[i]); i += 1
        text = " ".join(clean_parts) if clean_parts else text

        category = _infer_category(text) if not category_str else _infer_category_explicit(category_str)
        importance = _infer_importance(text, importance_str)

        manager = _get_manager()
        memory_id = manager.capture_memory(
            text=text,
            category=category,
            importance=importance,
            tags=tags
        )
        return {
            "success": True,
            "memory_id": memory_id[:12],
            "category": category.value,
            "importance": importance.value,
            "text_preview": text[:80] + ("..." if len(text) > 80 else ""),
        }

    def _handle_search(self, args: list) -> dict:
        """语义向量搜索记忆"""
        if not args:
            return {"error": "请提供搜索查询"}

        # 解析参数
        limit = 5
        threshold = 0.50
        clean_parts = []
        i = 0
        while i < len(args):
            if args[i] in ("-n", "--limit") and i + 1 < len(args):
                limit = int(args[i + 1]); i += 2
            elif args[i] == "--threshold" and i + 1 < len(args):
                threshold = float(args[i + 1]); i += 2
            else:
                clean_parts.append(args[i]); i += 1

        query = " ".join(clean_parts)
        manager = _get_manager()
        memories = manager.retrieve_memories(
            query=query,
            limit=limit,
            similarity_threshold=threshold
        )

        results = []
        for m in memories:
            results.append({
                "id": m.id[:12],
                "score": round(m.score, 3),
                "category": m.metadata.category.value,
                "importance": m.metadata.importance.value,
                "created": datetime.fromtimestamp(m.metadata.created_at).strftime("%Y-%m-%d %H:%M"),
                "text": m.text[:200] + ("..." if len(m.text) > 200 else ""),
                "tags": m.metadata.tags,
            })

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "threshold": threshold,
            "results": results,
        }

    def _handle_list(self, args: list) -> dict:
        """列出最近的记忆（全文扫描）"""
        limit = 10
        if args:
            try:
                limit = int(args[0])
            except ValueError:
                pass

        manager = _get_manager()
        # 用空查询向量做全量 scroll
        all_points = manager.storage.client.scroll(
            collection_name=manager.storage.collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )[0]

        memories = []
        for p in all_points:
            pl = p.payload
            md = pl.get("metadata", {})
            memories.append({
                "id": str(p.id)[:12],
                "score": round(pl.get("score", 0), 3),
                "category": md.get("category", "unknown"),
                "importance": md.get("importance", "unknown"),
                "created": datetime.fromtimestamp(md.get("created_at", 0)).strftime("%Y-%m-%d %H:%M") if md.get("created_at") else "unknown",
                "text": pl.get("text", "")[:100] + "...",
            })

        return {
            "success": True,
            "count": len(memories),
            "memories": memories,
        }

    def _handle_stats(self, args: list) -> dict:
        """获取记忆系统统计信息"""
        manager = _get_manager()
        stats = manager.get_statistics()
        storage = stats.get("storage", {})
        return {
            "success": True,
            "total_memories": storage.get("total_memories", 0),
            "average_score": storage.get("average_score", 0),
            "vectors_count": storage.get("vectors_count", 0),
            "categories": storage.get("categories", {}),
            "importances": storage.get("importances", {}),
            "collection_status": storage.get("collection_status", "unknown"),
            "lifecycle_events": stats.get("lifecycle_events", {}).get("total", 0),
            "last_optimization": stats.get("last_optimization", "从未"),
            "embedding_model": stats.get("embedding_model", {}).get("model_type", "unknown"),
        }

    def _handle_optimize(self, args: list) -> dict:
        """手动触发记忆优化（遗忘低分 + 升级高分到 QMD）"""
        force = "--force" in args
        manager = _get_manager()
        manager.optimize_memories(force=force)
        stats = manager.storage.get_statistics()
        return {
            "success": True,
            "message": "优化完成",
            "total_memories": stats.get("total_memories", 0),
        }

    def _handle_clear(self, args: list) -> dict:
        """清空所有记忆（需要确认码）"""
        if not args or args[0] != "CONFIRM_CLEAR":
            return {
                "error": "危险操作，需要确认",
                "usage": "/memory clear CONFIRM_CLEAR"
            }
        manager = _get_manager()
        client = manager.storage.client
        col = manager.storage.collection_name
        # 删除并重建集合
        client.delete_collection(col)
        manager.storage._ensure_collection()
        return {"success": True, "message": f"集合 {col} 已清空并重建"}

    def _handle_export(self, args: list) -> dict:
        """导出记忆到 JSON 文件"""
        if not args:
            filepath = f"/Users/luolimo/OpenClaw/workspace/backup/atlas_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            filepath = args[0]
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        manager = _get_manager()
        manager.storage.export_to_json(filepath)
        return {"success": True, "exported_to": filepath}

    def _handle_import(self, args: list) -> dict:
        """从 JSON 文件导入记忆（注意：恢复的记忆需重新嵌入才能语义搜索）"""
        if not args:
            return {"error": "请指定文件路径"}
        filepath = args[0]
        if not os.path.exists(filepath):
            return {"error": f"文件不存在: {filepath}"}
        manager = _get_manager()
        manager.storage.import_from_json(filepath)
        return {"success": True, "imported_from": filepath, "note": "向量占位，需重新嵌入后才能语义搜索"}

    def _handle_debug(self, args: list) -> dict:
        """调试工具"""
        sub = args[0] if args else "info"

        if sub == "info":
            manager = _get_manager()
            col_info = manager.storage.client.get_collection(manager.storage.collection_name)
            return {
                "qdrant_url": "http://localhost:6333",
                "collection": manager.storage.collection_name,
                "vector_size": manager.storage.vector_size,
                "collection_status": str(col_info.status),
                "points_count": col_info.points_count,
                "indexed_vectors_count": col_info.indexed_vectors_count,
                "atlas_core_path": ATLAS_CORE_SRC,
            }
        elif sub == "test":
            manager = _get_manager()
            test_id = manager.capture_memory(
                text="[DEBUG TEST] ATLAS Memory 系统自检",
                category=__import__("core.qdrant_storage", fromlist=["MemoryCategory"]).MemoryCategory.SYSTEM,
                importance=__import__("core.qdrant_storage", fromlist=["MemoryImportance"]).MemoryImportance.LOW,
                tags=["debug", "test"]
            )
            results = manager.retrieve_memories("系统自检", limit=1, similarity_threshold=0.50)
            manager.storage.delete_memory(test_id)
            return {
                "success": len(results) > 0,
                "test_id": test_id[:12],
                "retrieved": len(results),
                "pipeline": "capture → embed → store → search → delete",
            }
        elif sub == "reset":
            global _manager
            _manager = None
            return {"success": True, "message": "管理器已重置，下次调用时重新初始化"}
        else:
            return {"error": f"未知调试子命令: {sub}", "available": ["info", "test", "reset"]}

    def _handle_help(self, args: list) -> dict:
        return {
            "success": True,
            "commands": {
                "/memory store <文本> [--importance high|medium|low|critical] [--tags tag1,tag2]": "存储记忆到 Qdrant（自动嵌入向量 + 分类）",
                "/memory search <查询> [-n 数量] [--threshold 0.82]": "语义向量搜索",
                "/memory list [数量]": "列出最近的记忆",
                "/memory stats": "统计信息",
                "/memory optimize [--force]": "优化（遗忘低分 + 升级高分到 QMD）",
                "/memory clear CONFIRM_CLEAR": "清空所有记忆",
                "/memory export [路径]": "导出到 JSON",
                "/memory import <路径>": "从 JSON 导入",
                "/memory debug info|test|reset": "调试工具",
            },
            "backend": "Qdrant http://localhost:6333 + nomic-ai/nomic-embed-text-v1.5 (768维)",
        }


def _infer_category_explicit(cat_str: str):
    from core.qdrant_storage import MemoryCategory
    mapping = {
        "personal": MemoryCategory.PERSONAL,
        "work": MemoryCategory.WORK,
        "learning": MemoryCategory.LEARNING,
        "project": MemoryCategory.PROJECT,
        "system": MemoryCategory.SYSTEM,
        "conversation": MemoryCategory.CONVERSATION,
    }
    return mapping.get(cat_str.lower(), MemoryCategory.PERSONAL)


# OpenClaw skill 入口点
_skill = AtlasSkill()


def handle_atlas_command(command: str, args: list) -> dict:
    """OpenClaw skill handler"""
    return _skill.handle_command(command, args)


if __name__ == "__main__":
    import json as _json
    import sys as _sys

    if len(_sys.argv) < 2:
        print(_json.dumps({"error": "usage: atlas_skill.py <command|--server> [args...]"}))
        _sys.exit(1)

    if _sys.argv[1] == "--server":
        # 持久化 HTTP 服务模式：预热模型，监听 localhost:16334
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import urllib.parse as _urlparse

        PORT = 16334

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # 静默 access log
                pass

            def do_GET(self):
                parsed = _urlparse.urlparse(self.path)
                params = dict(_urlparse.parse_qsl(parsed.query))
                cmd = parsed.path.lstrip("/")
                args_str = params.get("args", "")
                args = args_str.split("\x00") if args_str else []
                result = _skill.handle_command(cmd, args)
                body = _json.dumps(result, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        # 预热：初始化 manager（加载嵌入模型 + 连接 Qdrant）
        try:
            _get_manager()
            print(f"[atlas-skill] server ready on :{PORT}", flush=True)
        except Exception as _e:
            print(f"[atlas-skill] warmup failed: {_e}", flush=True)

        HTTPServer(("127.0.0.1", PORT), _Handler).serve_forever()
    else:
        _cmd = _sys.argv[1]
        _args = _sys.argv[2:]
        _result = _skill.handle_command(_cmd, _args)
        print(_json.dumps(_result, ensure_ascii=False))
