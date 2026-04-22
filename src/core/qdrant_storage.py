"""
Qdrant存储模块 - 零Token捕获层的核心实现
基于Aegis-Cortex Token经济学架构
"""

import json
import math
import time
import hashlib
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance, VectorParams, HnswConfigDiff,
    ScalarQuantization, ScalarQuantizationConfig, ScalarType,
)


class MemoryCategory(Enum):
    """记忆分类枚举"""
    PERSONAL = "personal"  # 个人信息
    WORK = "work"          # 工作相关
    LEARNING = "learning"  # 学习内容
    PROJECT = "project"    # 项目相关
    SYSTEM = "system"      # 系统配置
    CONVERSATION = "conversation"  # 对话历史


class MemoryImportance(Enum):
    """记忆重要性级别"""
    LOW = "low"        # 低重要性
    MEDIUM = "medium"  # 中等重要性
    HIGH = "high"      # 高重要性
    CRITICAL = "critical"  # 关键重要性


@dataclass
class MemoryMetadata:
    """记忆元数据"""
    category: MemoryCategory
    importance: MemoryImportance
    created_at: float
    last_accessed: float
    access_count: int = 0
    tags: List[str] = None
    source: str = "openclaw"
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "category": self.category.value,
            "importance": self.importance.value,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "tags": self.tags,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MemoryMetadata':
        """从字典创建"""
        return cls(
            category=MemoryCategory(data["category"]),
            importance=MemoryImportance(data["importance"]),
            created_at=data["created_at"],
            last_accessed=data["last_accessed"],
            access_count=data.get("access_count", 0),
            tags=data.get("tags", []),
            source=data.get("source", "openclaw")
        )


@dataclass
class MemoryRecord:
    """记忆记录"""
    id: str
    text: str
    embedding: List[float]
    metadata: MemoryMetadata
    score: float = 0.0  # 记忆评分
    
    def to_qdrant_point(self) -> models.PointStruct:
        """转换为Qdrant点"""
        return models.PointStruct(
            id=self.id,
            vector=self.embedding,
            payload={
                "text": self.text,
                "metadata": self.metadata.to_dict(),
                "score": self.score,
                "created_at": self.metadata.created_at
            }
        )
    
    @classmethod
    def from_qdrant_point(cls, point: models.ScoredPoint) -> 'MemoryRecord':
        """从Qdrant点创建"""
        payload = point.payload
        return cls(
            id=str(point.id),
            text=payload["text"],
            embedding=point.vector,
            metadata=MemoryMetadata.from_dict(payload["metadata"]),
            score=payload.get("score", 0.0)
        )


class QdrantMemoryStorage:
    """Qdrant记忆存储 - 零Token捕获层核心"""
    
    def __init__(self, collection_name: str = "atlas_memories",
                 vector_size: int = 768,  # nomic-embed-text-v1.5维度
                 storage_path: str = None,
                 url: str = None):
        """
        初始化Qdrant存储

        Args:
            collection_name: 集合名称
            vector_size: 向量维度
            storage_path: 本地文件存储路径
            url: Qdrant HTTP服务地址，如 http://localhost:6333
        """
        self.collection_name = collection_name
        self.vector_size = vector_size

        # 初始化Qdrant客户端
        try:
            if url:
                self.client = QdrantClient(url=url)
            elif storage_path:
                self.client = QdrantClient(path=storage_path)
            else:
                self.client = QdrantClient(":memory:")
        except Exception as e:
            print(f"⚠️ Qdrant客户端初始化失败: {e}")
            print("⚠️ 使用内存模式")
            self.client = QdrantClient(":memory:")
        
        # 创建集合（如果不存在）
        self._ensure_collection()
    
    def _ensure_collection(self):
        """确保集合存在"""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                    # HNSW: m=16 平衡内存与召回率，ef_construct=100 保证索引质量
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                ),
                # INT8 标量量化：~4x 内存压缩，rescore 恢复精度
                quantization_config=ScalarQuantizationConfig(
                    scalar=ScalarQuantization(
                        type=ScalarType.INT8,
                        quantile=0.99,
                        always_ram=True,
                    )
                ),
            )
            # 创建 payload 索引，加速分类过滤
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="metadata.category",
                field_schema="keyword",
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="metadata.importance",
                field_schema="keyword",
            )
    
    def _generate_id(self, text: str, metadata: MemoryMetadata) -> str:
        """生成唯一ID"""
        content = f"{text}_{metadata.category.value}_{metadata.importance.value}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def store_memory(self, text: str, embedding: List[float], 
                    category: MemoryCategory, importance: MemoryImportance,
                    tags: List[str] = None) -> str:
        """
        存储记忆 - 零Token捕获
        
        Args:
            text: 记忆文本
            embedding: 嵌入向量
            category: 记忆分类
            importance: 重要性级别
            tags: 标签列表
            
        Returns:
            记忆ID
        """
        # 创建元数据
        now = time.time()
        metadata = MemoryMetadata(
            category=category,
            importance=importance,
            created_at=now,
            last_accessed=now,
            tags=tags or [],
            source="openclaw"
        )
        
        # 生成ID
        memory_id = self._generate_id(text, metadata)
        
        # 创建记忆记录
        record = MemoryRecord(
            id=memory_id,
            text=text,
            embedding=embedding,
            metadata=metadata,
            score=self._calculate_initial_score(importance)
        )
        
        # 存储到Qdrant
        point = record.to_qdrant_point()
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        
        return memory_id
    
    # 重要性等级 → 数值映射（用于 Ebbinghaus 公式）
    _IMPORTANCE_VALUES = {
        MemoryImportance.LOW: 0.2,
        MemoryImportance.MEDIUM: 0.5,
        MemoryImportance.HIGH: 0.8,
        MemoryImportance.CRITICAL: 1.0,
    }

    @staticmethod
    def _memory_strength(importance_value: float, days_since_access: float, recall_count: int) -> float:
        """
        Ebbinghaus 遗忘曲线衰减强度（2025 最佳实践）：
          strength = importance × e^(−λ_eff × days) × access_boost
          λ_eff = 0.16 × (1 − importance × 0.8)

        重要性与半衰期对应关系：
          critical(1.0) → λ=0.032 → ~6个月
          high(0.8)     → λ=0.054 → ~3周
          medium(0.5)   → λ=0.096 → ~7天
          low(0.2)      → λ=0.144 → ~5天
        """
        λ_eff = 0.16 * (1.0 - importance_value * 0.8)
        decay = math.exp(-λ_eff * max(0.0, days_since_access))
        access_boost = 1.0 + min(recall_count * 0.2, 4.0)   # 最大 5x 加成
        return min(1.0, max(0.0, importance_value * decay * access_boost))

    def _calculate_initial_score(self, importance: MemoryImportance) -> float:
        """新记忆初始强度（刚创建，days_since_access=0，recall_count=0）"""
        iv = self._IMPORTANCE_VALUES.get(importance, 0.5)
        return self._memory_strength(iv, 0.0, 0)
    
    def search_memories(self, query_embedding: List[float],
                       limit: int = 10,
                       category: Optional[MemoryCategory] = None,
                       min_score: float = 0.0,
                       similarity_threshold: float = 0.65) -> List[MemoryRecord]:
        """
        搜索记忆：两阶段管道
          Stage 1 — Qdrant 向量检索（余弦相似度 ≥ similarity_threshold），多取 limit*4 候选
          Stage 2 — Python 端用 Ebbinghaus 强度重排，返回最终 top-N

        Args:
            query_embedding: 查询向量（L2 归一化）
            limit: 最终返回数量
            category: 分类过滤
            min_score: 最小 Ebbinghaus 强度阈值（pruning_threshold=0.05）
            similarity_threshold: 余弦相似度下限（nomic-embed-text-v1.5 建议 0.65-0.70）
        """
        filter_condition = None
        if category:
            filter_condition = models.Filter(must=[
                models.FieldCondition(
                    key="metadata.category",
                    match=models.MatchValue(value=category.value),
                )
            ])

        # Stage 1: 多取候选（limit*4，最少 20）供重排
        candidate_limit = max(20, limit * 4)
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=filter_condition,
            limit=candidate_limit,
            score_threshold=similarity_threshold,
            with_payload=True,
            with_vectors=True,
            search_params=models.SearchParams(
                hnsw_ef=128,       # 查询时提高精度
                exact=False,
            ),
        )

        scored_points = search_result.points if hasattr(search_result, 'points') else search_result
        now = time.time()

        # Stage 2: 计算 Ebbinghaus 强度并重排
        candidates = []
        for sp in scored_points:
            record = MemoryRecord.from_qdrant_point(sp)
            md = record.metadata
            iv = self._IMPORTANCE_VALUES.get(md.importance, 0.5)
            days_since = (now - md.last_accessed) / 86400.0
            strength = self._memory_strength(iv, days_since, md.access_count)
            if strength >= max(min_score, 0.05):   # 剪枝：强度 < 0.05 直接丢弃
                candidates.append((strength, record))

        # 按强度降序，取 top-N
        candidates.sort(key=lambda x: x[0], reverse=True)
        memories = []
        for strength, record in candidates[:limit]:
            record.score = strength           # 用真实 Ebbinghaus 分覆盖 payload 分
            self._update_access_info(record.id)
            memories.append(record)

        return memories
    
    def _update_access_info(self, memory_id: str):
        """访问后：重置衰减时钟并重算 Ebbinghaus 强度"""
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[memory_id],
                with_vectors=True,
            )
            if not points:
                return
            point = points[0]
            payload = point.payload
            metadata_dict = payload["metadata"]

            now = time.time()
            metadata_dict["last_accessed"] = now
            recall_count = metadata_dict.get("access_count", 0) + 1
            metadata_dict["access_count"] = recall_count

            # 重算 Ebbinghaus 强度（访问重置衰减时钟：days_since_access=0）
            importance_str = metadata_dict.get("importance", "medium")
            importance_enum = MemoryImportance(importance_str)
            iv = self._IMPORTANCE_VALUES.get(importance_enum, 0.5)
            payload["score"] = self._memory_strength(iv, 0.0, recall_count)

            self.client.upsert(
                collection_name=self.collection_name,
                points=[models.PointStruct(
                    id=point.id,
                    vector=point.vector,
                    payload=payload,
                )],
            )
        except Exception as e:
            print(f"更新访问信息失败: {e}")
    
    def get_memory_by_id(self, memory_id: str) -> Optional[MemoryRecord]:
        """根据ID获取记忆"""
        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[memory_id]
        )
        
        if points:
            point = points[0]
            # 转换为ScoredPoint以便使用from_qdrant_point
            scored_point = models.ScoredPoint(
                id=point.id,
                version=0,
                score=1.0,
                payload=point.payload,
                vector=point.vector
            )
            return MemoryRecord.from_qdrant_point(scored_point)
        return None
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[memory_id]
                )
            )
            return True
        except Exception as e:
            print(f"删除记忆失败: {e}")
            return False
    
    def update_memory(self, memory_id: str, text: str, embedding: List[float],
                      importance: MemoryImportance, tags: List[str] = None) -> str:
        """
        更新现有记忆（Mem0 UPDATE 路径）：覆盖文本、向量、重要性和标签，
        保留原始 created_at，重置 last_accessed（Ebbinghaus 时钟归零）。
        若记忆不存在则降级为 store_memory。
        """
        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[memory_id],
            with_vectors=True,
        )
        if not points:
            return self.store_memory(
                text=text, embedding=embedding,
                category=MemoryCategory.PERSONAL,
                importance=importance, tags=tags,
            )

        point = points[0]
        payload = dict(point.payload)
        metadata = dict(payload.get("metadata", {}))

        now = time.time()
        recall_count = metadata.get("access_count", 0) + 1
        metadata["last_accessed"] = now
        metadata["access_count"] = recall_count
        metadata["importance"] = importance.value
        metadata["tags"] = tags or []

        iv = self._IMPORTANCE_VALUES.get(importance, 0.5)
        payload["text"] = text
        payload["metadata"] = metadata
        payload["score"] = self._memory_strength(iv, 0.0, recall_count)

        self.client.upsert(
            collection_name=self.collection_name,
            points=[models.PointStruct(
                id=point.id,
                vector=embedding,
                payload=payload,
            )],
        )
        return memory_id

    def get_low_score_memories(self, strength_threshold: float = 0.05,
                              min_age_days: float = 1.0) -> List[MemoryRecord]:
        """
        返回 Ebbinghaus 强度低于阈值的记忆（用于自动遗忘）。
        默认强度阈值 0.05（研究建议的剪枝点）。
        min_age_days 避免刚创建的记忆被误删。
        """
        now = time.time()
        min_age_seconds = min_age_days * 86400.0

        all_points = self.client.scroll(
            collection_name=self.collection_name,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )[0]

        low_score_memories = []
        for point in all_points:
            payload = point.payload
            metadata = payload.get("metadata", {})
            created_at = metadata.get("created_at", now)

            if (now - created_at) < min_age_seconds:
                continue   # 太新，跳过

            importance_str = metadata.get("importance", "medium")
            try:
                iv = self._IMPORTANCE_VALUES.get(MemoryImportance(importance_str), 0.5)
            except ValueError:
                iv = 0.5

            last_accessed = metadata.get("last_accessed", created_at)
            recall_count = metadata.get("access_count", 0)
            days_since = (now - last_accessed) / 86400.0
            strength = self._memory_strength(iv, days_since, recall_count)

            if strength < strength_threshold:
                scored_point = models.ScoredPoint(
                    id=point.id, version=0,
                    score=strength, payload=payload, vector=None,
                )
                low_score_memories.append(MemoryRecord.from_qdrant_point(scored_point))

        return low_score_memories
    
    def get_high_score_memories(self, threshold: float = 0.85) -> List[MemoryRecord]:
        """获取高评分记忆（用于自动升级到QMD）"""
        # 搜索所有记忆
        all_points = self.client.scroll(
            collection_name=self.collection_name,
            limit=1000
        )[0]
        
        high_score_memories = []
        for point in all_points:
            payload = point.payload
            score = payload.get("score", 0.5)
            
            if score >= threshold:
                scored_point = models.ScoredPoint(
                    id=point.id,
                    version=0,
                    score=score,
                    payload=payload,
                    vector=point.vector
                )
                record = MemoryRecord.from_qdrant_point(scored_point)
                high_score_memories.append(record)
        
        return high_score_memories
    
    def get_statistics(self) -> Dict:
        """获取存储统计信息"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            
            # 获取所有点
            all_points = self.client.scroll(
                collection_name=self.collection_name,
                limit=1000
            )[0]
            
            # 计算统计信息
            total_memories = len(all_points)
            scores = []
            categories = {}
            importances = {}
            
            for point in all_points:
                payload = point.payload
                score = payload.get("score", 0.5)
                metadata = payload.get("metadata", {})
                category = metadata.get("category", "unknown")
                importance = metadata.get("importance", "unknown")
                
                scores.append(score)
                categories[category] = categories.get(category, 0) + 1
                importances[importance] = importances.get(importance, 0) + 1
            
            avg_score = sum(scores) / len(scores) if scores else 0
            
            return {
                "total_memories": total_memories,
                "average_score": round(avg_score, 3),
                "categories": categories,
                "importances": importances,
                "collection_status": str(collection_info.status),
                "vectors_count": collection_info.points_count or 0
            }
        except Exception as e:
            return {"error": str(e)}
    
    def export_to_json(self, filepath: str):
        """导出记忆到JSON文件（备份）"""
        all_points = self.client.scroll(
            collection_name=self.collection_name,
            limit=10000
        )[0]
        
        memories = []
        for point in all_points:
            payload = point.payload
            memories.append({
                "id": str(point.id),
                "text": payload.get("text", ""),
                "metadata": payload.get("metadata", {}),
                "score": payload.get("score", 0.5),
                "created_at": payload.get("created_at", time.time())
            })
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
    
    def import_from_json(self, filepath: str):
        """从JSON文件导入记忆（恢复）"""
        with open(filepath, 'r', encoding='utf-8') as f:
            memories = json.load(f)
        
        points = []
        for memory in memories:
            # 需要重新生成嵌入向量
            # 这里假设嵌入向量已经在内存中或可以重新计算
            # 实际使用时需要处理嵌入向量
            point = models.PointStruct(
                id=memory["id"],
                vector=[0.0] * self.vector_size,  # 占位向量
                payload={
                    "text": memory["text"],
                    "metadata": memory["metadata"],
                    "score": memory["score"],
                    "created_at": memory["created_at"]
                }
            )
            points.append(point)
        
        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )