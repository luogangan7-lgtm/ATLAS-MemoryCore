"""
分层记忆系统核心模块 - 最简化实现
目标: 减少云端Token消耗，本地完成所有记忆处理
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from .embedding import EmbeddingModel
from .scoring import MemoryScoringEngine

logger = logging.getLogger(__name__)


@dataclass
class MemoryLayerConfig:
    """记忆层级配置"""

    name: str
    capacity: int
    retention_days: int
    compression_ratio: float
    retrieval_priority: int


class HierarchicalMemorySystem:
    """分层记忆系统 - 最简化实现"""

    def __init__(self):
        self.embedding_model = EmbeddingModel()
        self.scoring_engine = MemoryScoringEngine()

        # 定义四层记忆配置
        self.layers = {
            "working": MemoryLayerConfig(
                name="working",
                capacity=100,  # 100条记忆
                retention_days=0.1,  # 2.4小时
                compression_ratio=0.3,  # 压缩70%
                retrieval_priority=1,
            ),
            "short_term": MemoryLayerConfig(
                name="short_term",
                capacity=500,  # 500条记忆
                retention_days=7,  # 7天
                compression_ratio=0.5,  # 压缩50%
                retrieval_priority=2,
            ),
            "medium_term": MemoryLayerConfig(
                name="medium_term",
                capacity=2000,  # 2000条记忆
                retention_days=30,  # 30天
                compression_ratio=0.7,  # 压缩30%
                retrieval_priority=3,
            ),
            "long_term": MemoryLayerConfig(
                name="long_term",
                capacity=10000,  # 10000条记忆
                retention_days=365,  # 1年
                compression_ratio=0.9,  # 压缩10%
                retrieval_priority=4,
            ),
        }

        # 初始化存储
        self.storage_dir = Path("/Volumes/data/openclaw_workspace/memory_data")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self.memory_cache = {layer: [] for layer in self.layers.keys()}

        logger.info("分层记忆系统初始化完成")

    async def process_memory(self, text: str, metadata: Dict[str, Any] = None) -> str:
        """
        处理记忆 - 核心入口函数
        返回: 压缩后的记忆摘要
        """
        if metadata is None:
            metadata = {}

        # 1. 生成嵌入向量
        embedding = self.embedding_model.encode(text)

        # 2. 计算记忆评分
        memory_data = {"text": text, "metadata": metadata, "usage_history": []}
        score = self.scoring_engine.calculate_score(memory_data)

        # 3. 确定存储层级
        target_layer = self._determine_layer(score, metadata)

        # 4. 压缩记忆
        compressed_text = self._compress_memory(text, target_layer)

        # 5. 存储记忆
        memory_id = await self._store_memory(
            text=compressed_text,
            original_text=text,
            embedding=embedding,
            score=score,
            layer=target_layer,
            metadata=metadata,
        )

        # 6. 清理过期记忆
        await self._cleanup_expired_memories()

        logger.info(
            f"记忆处理完成: ID={memory_id[:8]}, 层级={target_layer}, 评分={score:.2f}"
        )

        return compressed_text

    def _determine_layer(self, score: float, metadata: Dict[str, Any]) -> str:
        """根据评分确定存储层级"""
        importance = metadata.get("importance", 0.5)

        if score >= 0.85 or importance >= 0.9:
            return "long_term"
        elif score >= 0.7 or importance >= 0.7:
            return "medium_term"
        elif score >= 0.5 or importance >= 0.5:
            return "short_term"
        else:
            return "working"

    def _compress_memory(self, text: str, layer: str) -> str:
        """压缩记忆文本"""
        config = self.layers[layer]

        # 简单压缩策略
        if len(text) <= 100:
            return text

        # 提取关键信息
        lines = text.split("\n")

        if len(lines) >= 3:
            # 保留开头和结尾
            compressed = lines[0] + "\n...\n" + lines[-1]
        else:
            # 截断中间部分
            mid_point = len(text) // 2
            compressed = (
                text[:50]
                + "..."
                + text[mid_point : mid_point + 50]
                + "..."
                + text[-50:]
            )

        # 应用压缩比例
        target_length = int(len(text) * config.compression_ratio)
        if len(compressed) > target_length:
            compressed = compressed[:target_length] + "..."

        return compressed

    async def _store_memory(
        self,
        text: str,
        original_text: str,
        embedding: List[float],
        score: float,
        layer: str,
        metadata: Dict[str, Any],
    ) -> str:
        """存储记忆"""
        memory_id = (
            f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(text) % 10000:04d}"
        )

        memory_record = {
            "id": memory_id,
            "text": text,
            "original_text": original_text,
            "embedding": embedding,
            "score": score,
            "layer": layer,
            "metadata": {
                **metadata,
                "created_at": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
                "access_count": 0,
            },
        }

        # 存储到文件
        layer_dir = self.storage_dir / layer
        layer_dir.mkdir(exist_ok=True)

        file_path = layer_dir / f"{memory_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(memory_record, f, ensure_ascii=False, indent=2)

        # 更新缓存
        self.memory_cache[layer].append(memory_record)

        # 限制缓存大小
        if len(self.memory_cache[layer]) > self.layers[layer].capacity:
            self.memory_cache[layer] = self.memory_cache[layer][
                -self.layers[layer].capacity :
            ]

        return memory_id

    async def retrieve_relevant_memories(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        检索相关记忆 - 智能减少Token消耗
        返回: 压缩后的相关记忆列表
        """
        # 1. 生成查询嵌入
        query_embedding = self.embedding_model.encode(query)

        # 2. 分层检索
        all_memories = []

        for layer in ["working", "short_term", "medium_term", "long_term"]:
            layer_memories = await self._retrieve_from_layer(
                query_embedding, layer, limit // 4
            )
            all_memories.extend(layer_memories)

        # 3. 按相关性排序
        sorted_memories = sorted(
            all_memories, key=lambda x: x.get("relevance_score", 0), reverse=True
        )

        # 4. 智能选择最相关记忆 (减少Token)
        selected_memories = self._select_optimal_memories(sorted_memories, limit)

        # 5. 更新访问记录
        for memory in selected_memories:
            await self._update_access_record(memory["id"])

        logger.info(
            f"检索完成: 查询='{query[:50]}...', 返回{len(selected_memories)}条记忆"
        )

        return selected_memories

    async def _retrieve_from_layer(
        self, query_embedding: List[float], layer: str, limit: int
    ) -> List[Dict[str, Any]]:
        """从指定层级检索记忆"""
        layer_dir = self.storage_dir / layer

        if not layer_dir.exists():
            return []

        memories = []

        # 从缓存或文件加载
        if self.memory_cache[layer]:
            layer_memories = self.memory_cache[layer]
        else:
            layer_memories = []
            for file_path in layer_dir.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        memory = json.load(f)
                        layer_memories.append(memory)
                except:
                    continue

        # 计算相关性
        for memory in layer_memories:
            embedding = memory.get("embedding", [])
            if embedding:
                # 简单余弦相似度
                similarity = self._cosine_similarity(query_embedding, embedding)
                memory["relevance_score"] = similarity
                memory["layer"] = layer
                memories.append(memory)

        # 按相关性排序并限制数量
        memories.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return memories[:limit]

    def _select_optimal_memories(
        self, memories: List[Dict[str, Any]], target_count: int
    ) -> List[Dict[str, Any]]:
        """
        智能选择最优记忆集合 - 最大化信息密度，最小化Token消耗
        """
        if len(memories) <= target_count:
            return memories

        selected = []
        used_texts = set()

        for memory in memories:
            text = memory.get("text", "")

            # 检查重复内容
            is_duplicate = False
            for used_text in used_texts:
                if self._text_similarity(text, used_text) > 0.8:
                    is_duplicate = True
                    break

            if not is_duplicate:
                selected.append(memory)
                used_texts.add(text[:100])  # 只比较前100字符

            if len(selected) >= target_count:
                break

        return selected

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _text_similarity(self, text1: str, text2: str) -> float:
        """简单文本相似度计算"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    async def _update_access_record(self, memory_id: str):
        """更新记忆访问记录"""
        # 查找记忆文件
        for layer in self.layers.keys():
            layer_dir = self.storage_dir / layer
            file_path = layer_dir / f"{memory_id}.json"

            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        memory = json.load(f)

                    memory["metadata"]["last_accessed"] = datetime.now().isoformat()
                    memory["metadata"]["access_count"] = (
                        memory["metadata"].get("access_count", 0) + 1
                    )

                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(memory, f, ensure_ascii=False, indent=2)

                    break
                except:
                    continue

    async def _cleanup_expired_memories(self):
        """清理过期记忆"""
        for layer_name, config in self.layers.items():
            if config.retention_days <= 0:
                continue

            layer_dir = self.storage_dir / layer_name
            if not layer_dir.exists():
                continue

            cutoff_time = datetime.now() - timedelta(days=config.retention_days)

            for file_path in layer_dir.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        memory = json.load(f)

                    created_at_str = memory["metadata"].get("created_at")
                    if created_at_str:
                        created_at = datetime.fromisoformat(
                            created_at_str.replace("Z", "+00:00")
                        )

                        if created_at < cutoff_time:
                            # 检查重要性
                            score = memory.get("score", 0)
                            importance = memory["metadata"].get("importance", 0.5)

                            if score < 0.3 and importance < 0.3:
                                # 删除低重要性过期记忆
                                file_path.unlink()
                                logger.debug(f"清理过期记忆: {file_path.name}")
                except:
                    continue

    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计信息"""
        stats = {
            "total_memories": 0,
            "layer_counts": {},
            "average_compression_ratio": 0.0,
            "total_token_saved": 0,
            "last_cleanup": datetime.now().isoformat(),
        }

        total_original_length = 0
        total_compressed_length = 0

        for layer_name in self.layers.keys():
            layer_dir = self.storage_dir / layer_name

            if layer_dir.exists():
                count = len(list(layer_dir.glob("*.json")))
                stats["layer_counts"][layer_name] = count
                stats["total_memories"] += count

                # 计算压缩率
                for file_path in list(layer_dir.glob("*.json"))[:10]:  # 采样10个文件
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            memory = json.load(f)

                        original = memory.get("original_text", "")
                        compressed = memory.get("text", "")

                        if original and compressed:
                            total_original_length += len(original)
                            total_compressed_length += len(compressed)
                    except:
                        continue

        # 计算平均压缩率
        if total_original_length > 0:
            stats["average_compression_ratio"] = (
                total_compressed_length / total_original_length
            )
            stats["total_token_saved"] = total_original_length - total_compressed_length

        return stats


# 全局实例
_hierarchical_memory_system = None


def get_hierarchical_memory_system() -> HierarchicalMemorySystem:
    """获取分层记忆系统实例"""
    global _hierarchical_memory_system
    if _hierarchical_memory_system is None:
        _hierarchical_memory_system = HierarchicalMemorySystem()
    return _hierarchical_memory_system
