"""
ATLAS-MemoryCore OpenClaw Skill v7.0.0
双轨记忆系统：Qdrant 结构化知识库 + QMD 日记搜索引擎
压缩模型：oMLX Qwen3.5-9B-OptiQ-4bit（本地，零 token 成本）
"""

import json
import sys
import os
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

# atlas-memory-core 路径
ATLAS_CORE_SRC = "/Volumes/data/openclaw_workspace/projects/atlas-memory-core/src"
if ATLAS_CORE_SRC not in sys.path:
    sys.path.insert(0, ATLAS_CORE_SRC)

# QMD 二进制路径
QMD_BIN = "/Users/luolimo/.bun/install/cache/@GH@tobi-qmd-cfd640e@@@1/bin/qmd"
QMD_COLLECTION = "memory-dir-main"

# oMLX 配置（本地 Qwen3.5-9B-OptiQ-4bit）
OMLX_URL = "http://127.0.0.1:7749/v1/chat/completions"
OMLX_API_KEY = "774955"
OMLX_MODEL = "Qwen3.5-9B-OptiQ-4bit"

# 闲聊过滤词
CHIT_CHAT_KEYWORDS = ["你好", "谢谢", "好的", "没问题", "了解", "收到", "OK", "ok", "嗯", "哦", "是的", "不是"]

# 延迟初始化
_manager = None


def _get_manager():
    global _manager
    if _manager is None:
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
    from core.qdrant_storage import MemoryCategory
    text_lower = text.lower()
    if any(k in text_lower for k in ["交易", "买入", "卖出", "仓位", "止损", "行情", "k线", "ma", "macd", "rsi", "trade", "signal"]):
        return MemoryCategory.WORK
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


def _compress_via_omlx(text: str, ratio: float = 0.3) -> str:
    """调用本地 oMLX Qwen3.5-9B-OptiQ-4bit 压缩文本，零云端 token"""
    import urllib.request as _urlreq
    target_len = max(100, int(len(text) * ratio))
    messages = [
        {
            "role": "user",
            "content": (
                f"将以下内容压缩为约{target_len}字的简洁摘要。"
                f"保留关键决策、配置变更、重要事实，删除闲聊和重复内容。"
                f"直接输出摘要，不要解释。\n\n{text}"
            )
        }
    ]
    payload = json.dumps({
        "model": OMLX_MODEL,
        "messages": messages,
        "max_tokens": max(200, target_len * 2),
        "temperature": 0.3,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False}
    }).encode()
    req = _urlreq.Request(OMLX_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {OMLX_API_KEY}")
    try:
        with _urlreq.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"oMLX 压缩失败，返回原文: {e}")
        return text


def _search_qmd(query: str, limit: int = 3) -> list:
    """调用 QMD 搜索日记/对话记忆，返回结构化结果列表"""
    if not os.path.exists(QMD_BIN):
        return []
    try:
        result = subprocess.run(
            [QMD_BIN, "search", query, "-c", QMD_COLLECTION, "-n", str(limit), "--json"],
            capture_output=True, text=True, timeout=8,
            env={**os.environ, "NO_PROXY": "localhost,127.0.0.1"}
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        items = data if isinstance(data, list) else data.get("results", [])
        results = []
        for item in items[:limit]:
            file_path = item.get("file", item.get("path", ""))
            results.append({
                "source": "qmd",
                "path": file_path,
                "title": item.get("title", file_path.split("/")[-1]),
                "snippet": item.get("snippet", item.get("text", ""))[:200],
                "score": item.get("score", 0),
            })
        return results
    except Exception as e:
        logger.warning(f"QMD 搜索失败（降级为空）: {e}")
        return []


def _is_chit_chat(text: str) -> bool:
    """判断是否为无意义闲聊，过滤不值得存储的内容"""
    if len(text.strip()) < 50:
        return True
    short_text = text.strip()[:100].lower()
    hit_count = sum(1 for kw in CHIT_CHAT_KEYWORDS if kw.lower() in short_text)
    return hit_count >= 3


class AtlasSkill:
    """ATLAS-MemoryCore v7.0.0 — 双轨记忆后端"""

    def handle_command(self, command: str, args: list) -> dict:
        cmd = command.lower().strip()
        if cmd.startswith("memory "):
            cmd = cmd[7:].strip()

        handlers = {
            "store":        self._handle_store,
            "capture":      self._handle_store,
            "search":       self._handle_search,
            "dual_search":  self._handle_dual_search,
            "auto_capture": self._handle_auto_capture,
            "list":         self._handle_list,
            "stats":        self._handle_stats,
            "optimize":     self._handle_optimize,
            "compress":     self._handle_compress,
            "clear":        self._handle_clear,
            "export":       self._handle_export,
            "import":       self._handle_import,
            "debug":        self._handle_debug,
            "help":         self._handle_help,
        }
        handler = handlers.get(cmd)
        if handler is None:
            return {"error": f"未知命令: {cmd}", "available": list(handlers.keys())}
        try:
            return handler(args)
        except Exception as e:
            logger.error(f"命令 {cmd} 执行失败: {e}", exc_info=True)
            return {"error": str(e), "command": cmd}

    def _handle_store(self, args: list) -> dict:
        if not args:
            return {"error": "请提供记忆内容"}
        text = " ".join(args)
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
        memory_id = manager.capture_memory(text=text, category=category, importance=importance, tags=tags)
        return {
            "success": True,
            "memory_id": memory_id[:12],
            "category": category.value,
            "importance": importance.value,
            "text_preview": text[:80] + ("..." if len(text) > 80 else ""),
        }

    def _handle_search(self, args: list) -> dict:
        """Qdrant 语义搜索（结构化知识库）"""
        if not args:
            return {"error": "请提供搜索查询"}
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
        memories = manager.retrieve_memories(query=query, limit=limit, similarity_threshold=threshold)
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
        return {"success": True, "query": query, "count": len(results), "threshold": threshold, "results": results}

    def _handle_dual_search(self, args: list) -> dict:
        """双轨搜索：Qdrant（结构化）+ QMD（日记），合并排序"""
        if not args:
            return {"error": "请提供搜索查询"}
        limit = 3
        threshold = 0.55
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

        # Qdrant 搜索
        qdrant_results = []
        try:
            manager = _get_manager()
            memories = manager.retrieve_memories(query=query, limit=limit, similarity_threshold=threshold)
            for m in memories:
                qdrant_results.append({
                    "source": "qdrant",
                    "score": round(m.score, 3),
                    "category": m.metadata.category.value,
                    "created": datetime.fromtimestamp(m.metadata.created_at).strftime("%Y-%m-%d %H:%M"),
                    "text": m.text[:200] + ("..." if len(m.text) > 200 else ""),
                })
        except Exception as e:
            logger.warning(f"Qdrant 搜索失败: {e}")

        # QMD 搜索
        qmd_results = _search_qmd(query, limit)

        # 合并，按 score 排序，最多返回 limit*2 条
        all_results = qdrant_results + [
            {"source": "qmd", "score": r.get("score", 0), "title": r.get("title", ""),
             "text": r.get("snippet", ""), "created": ""}
            for r in qmd_results
        ]
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        deduped = []
        seen_texts = set()
        for r in all_results:
            key = r["text"][:60]
            if key not in seen_texts:
                seen_texts.add(key)
                deduped.append(r)
        deduped = deduped[:limit * 2]

        return {
            "success": True,
            "query": query,
            "count": len(deduped),
            "qdrant_count": len(qdrant_results),
            "qmd_count": len(qmd_results),
            "results": deduped,
        }

    def _handle_auto_capture(self, args: list) -> dict:
        """自动捕获对话片段存入 Qdrant（after_response hook 调用）"""
        if not args:
            return {"success": False, "reason": "empty"}
        text = " ".join(args)
        if _is_chit_chat(text):
            return {"success": False, "reason": "chit_chat_filtered"}
        category = _infer_category(text)
        importance = _infer_importance(text)
        try:
            manager = _get_manager()
            memory_id = manager.capture_memory(
                text=text,
                category=category,
                importance=importance,
                tags=["auto_captured"]
            )
            return {"success": True, "memory_id": memory_id[:12], "category": category.value}
        except Exception as e:
            return {"success": False, "reason": str(e)}

    def _handle_list(self, args: list) -> dict:
        limit = 10
        if args:
            try:
                limit = int(args[0])
            except ValueError:
                pass
        manager = _get_manager()
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
                "category": md.get("category", "unknown"),
                "importance": md.get("importance", "unknown"),
                "created": datetime.fromtimestamp(md.get("created_at", 0)).strftime("%Y-%m-%d %H:%M") if md.get("created_at") else "unknown",
                "text": pl.get("text", "")[:100] + "...",
            })
        return {"success": True, "count": len(memories), "memories": memories}

    def _handle_stats(self, args: list) -> dict:
        manager = _get_manager()
        stats = manager.get_statistics()
        storage = stats.get("storage", {})
        return {
            "success": True,
            "total_memories": storage.get("total_memories", 0),
            "vectors_count": storage.get("vectors_count", 0),
            "categories": storage.get("categories", {}),
            "collection_status": storage.get("collection_status", "unknown"),
            "embedding_model": stats.get("embedding_model", {}).get("model_type", "unknown"),
            "compress_backend": f"oMLX/{OMLX_MODEL}",
            "qmd_collection": QMD_COLLECTION,
        }

    def _handle_optimize(self, args: list) -> dict:
        force = "--force" in args
        manager = _get_manager()
        manager.optimize_memories(force=force)
        stats = manager.storage.get_statistics()
        return {"success": True, "message": "优化完成", "total_memories": stats.get("total_memories", 0)}

    def _handle_compress(self, args: list) -> dict:
        if not args:
            return {"error": "请提供要压缩的文本"}
        ratio = 0.3
        clean_parts = []
        i = 0
        while i < len(args):
            if args[i] == "--ratio" and i + 1 < len(args):
                ratio = float(args[i + 1]); i += 2
            else:
                clean_parts.append(args[i]); i += 1
        text = " ".join(clean_parts)
        compressed = _compress_via_omlx(text, ratio)
        return {
            "success": True,
            "original_len": len(text),
            "compressed_len": len(compressed),
            "ratio_achieved": round(len(compressed) / max(len(text), 1), 2),
            "compressed": compressed,
        }

    def _handle_clear(self, args: list) -> dict:
        if not args or args[0] != "CONFIRM_CLEAR":
            return {"error": "危险操作，需要确认", "usage": "/memory clear CONFIRM_CLEAR"}
        manager = _get_manager()
        client = manager.storage.client
        col = manager.storage.collection_name
        client.delete_collection(col)
        manager.storage._ensure_collection()
        return {"success": True, "message": f"集合 {col} 已清空并重建"}

    def _handle_export(self, args: list) -> dict:
        if not args:
            filepath = f"/Users/luolimo/OpenClaw/workspace/backup/atlas_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            filepath = args[0]
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        manager = _get_manager()
        manager.storage.export_to_json(filepath)
        return {"success": True, "exported_to": filepath}

    def _handle_import(self, args: list) -> dict:
        if not args:
            return {"error": "请指定文件路径"}
        filepath = args[0]
        if not os.path.exists(filepath):
            return {"error": f"文件不存在: {filepath}"}
        manager = _get_manager()
        manager.storage.import_from_json(filepath)
        return {"success": True, "imported_from": filepath}

    def _handle_debug(self, args: list) -> dict:
        sub = args[0] if args else "info"
        if sub == "info":
            manager = _get_manager()
            col_info = manager.storage.client.get_collection(manager.storage.collection_name)
            qmd_ok = os.path.exists(QMD_BIN)
            return {
                "version": "7.0.0",
                "qdrant_url": "http://localhost:6333",
                "collection": manager.storage.collection_name,
                "points_count": col_info.points_count,
                "compress_backend": f"oMLX/{OMLX_MODEL}",
                "omlx_url": OMLX_URL,
                "qmd_bin": QMD_BIN,
                "qmd_available": qmd_ok,
                "qmd_collection": QMD_COLLECTION,
            }
        return {"error": f"未知子命令: {sub}"}

    def _handle_help(self, args: list) -> dict:
        return {
            "success": True,
            "version": "7.0.0",
            "architecture": "双轨记忆：Qdrant（结构化）+ QMD（日记）",
            "compress_backend": f"oMLX/{OMLX_MODEL}（本地，零云端 token）",
            "commands": {
                "store <文本> [--importance high|medium|low|critical] [--tags t1,t2]": "存入 Qdrant",
                "search <查询> [-n N] [--threshold 0.55]": "Qdrant 语义搜索",
                "dual_search <查询> [-n N]": "双轨搜索（Qdrant + QMD 合并）",
                "auto_capture <文本>": "自动捕获（过滤闲聊，after_response 调用）",
                "compress <文本> [--ratio 0.3]": "oMLX 本地压缩",
                "list [N]": "列出最近记忆",
                "stats": "统计信息",
                "optimize [--force]": "优化记忆库",
                "export [路径]": "导出 JSON",
                "import <路径>": "导入 JSON",
                "clear CONFIRM_CLEAR": "清空集合",
                "debug info": "调试信息",
            },
        }


# ── HTTP server 入口 ──────────────────────────────────────────────────────────

_skill = AtlasSkill()


def handle_atlas_command(command: str, args: list) -> dict:
    return _skill.handle_command(command, args)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: atlas_skill.py <command|--server> [args...]"}))
        sys.exit(1)

    if sys.argv[1] == "--server":
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import urllib.parse as _urlparse

        PORT = 16334

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                parsed = _urlparse.urlparse(self.path)
                params = dict(_urlparse.parse_qsl(parsed.query))
                cmd = parsed.path.lstrip("/")
                args_str = params.get("args", "")
                args = args_str.split("\x00") if args_str else []
                result = _skill.handle_command(cmd, args)
                body = json.dumps(result, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            _get_manager()
            print(f"[atlas-skill] server ready on :{PORT}", flush=True)
        except Exception as _e:
            print(f"[atlas-skill] warmup failed: {_e}", flush=True)

        HTTPServer(("127.0.0.1", PORT), _Handler).serve_forever()
    else:
        _cmd = sys.argv[1]
        _args = sys.argv[2:]
        _result = _skill.handle_command(_cmd, _args)
        print(json.dumps(_result, ensure_ascii=False))
