"""
Qdrant存储模块 - 零Token捕获层的核心实现
基于Aegis-Cortex Token经济学架构
"""

import json
import time
import hashlib
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams


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
                 storage_path: str = None):
        """
        初始化Qdrant存储
        
        Args:
            collection_name: 集合名称
            vector_size: 向量维度
            storage_path: 存储路径，None表示内存模式
        """
        self.collection_name = collection_name
        self.vector_size = vector_size
        
        # 初始化Qdrant客户端
        try:
            if storage_path:
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
                    distance=Distance.COSINE
                )
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
    
    def _calculate_initial_score(self, importance: MemoryImportance) -> float:
        """计算初始评分"""
        importance_map = {
            MemoryImportance.LOW: 0.3,
            MemoryImportance.MEDIUM: 0.5,
            MemoryImportance.HIGH: 0.7,
            MemoryImportance.CRITICAL: 0.9
        }
        return importance_map.get(importance, 0.5)
    
    def search_memories(self, query_embedding: List[float], 
                       limit: int = 10,
                       category: Optional[MemoryCategory] = None,
                       min_score: float = 0.0,
                       similarity_threshold: float = 0.82) -> List[MemoryRecord]:
        """
        搜索记忆 - 惰性检索引擎
        
        Args:
            query_embedding: 查询向量
            limit: 返回数量限制
            category: 分类过滤
            min_score: 最小评分阈值
            similarity_threshold: 相似度阈值
            
        Returns:
            记忆记录列表
        """
        # 构建过滤器
        filter_condition = None
        if category:
            filter_condition = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value=category.value)
                    )
                ]
            )
        
        # 执行搜索 - 使用query_points方法
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=filter_condition,
            limit=limit * 2,  # 多取一些用于过滤
            score_threshold=similarity_threshold,
            with_payload=True,
            with_vectors=True
        )
        
        # 过滤和排序
        memories = []
        if hasattr(search_result, 'points'):
            scored_points = search_result.points
        else:
            scored_points = search_result
        
        for scored_point in scored_points:
            record = MemoryRecord.from_qdrant_point(scored_point)
            
            # 应用评分阈值
            if record.score >= min_score:
                # 更新访问信息
                self._update_access_info(record.id)
                memories.append(record)
            
            if len(memories) >= limit:
                break
        
        return memories
    
    def _update_access_info(self, memory_id: str):
        """更新访问信息"""
        try:
            # 获取当前记录
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[memory_id]
            )
            
            if points:
                point = points[0]
                payload = point.payload
                metadata_dict = payload["metadata"]
                
                # 更新访问信息
                metadata_dict["last_accessed"] = time.time()
                metadata_dict["access_count"] = metadata_dict.get("access_count", 0) + 1
                
                # 更新评分（基于访问频率）
                new_score = self._update_score_based_on_access(
                    payload.get("score", 0.5),
                    metadata_dict["access_count"]
                )
                payload["score"] = new_score
                
                # 更新到Qdrant
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=[models.PointStruct(
                        id=point.id,
                        vector=point.vector,
                        payload=payload
                    )]
                )
        except Exception as e:
            print(f"更新访问信息失败: {e}")
    
    def _update_score_based_on_access(self, current_score: float, access_count: int) -> float:
        """基于访问次数更新评分"""
        # 访问次数越多，评分越高，但有上限
        boost = min(0.2, access_count * 0.02)
        return min(1.0, current_score + boost)
    
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
    
    def get_low_score_memories(self, threshold: float = 0.3, 
                              max_age_days: float = 7) -> List[MemoryRecord]:
        """获取低评分记忆（用于自动遗忘）"""
        now = time.time()
        max_age_seconds = max_age_days * 24 * 3600
        
        # 搜索所有记忆
        all_points = self.client.scroll(
            collection_name=self.collection_name,
            limit=1000
        )[0]
        
        low_score_memories = []
        for point in all_points:
            payload = point.payload
            metadata = payload.get("metadata", {})
            score = payload.get("score", 0.5)
            created_at = metadata.get("created_at", now)
            last_accessed = metadata.get("last_accessed", now)
            
            # 检查条件：低评分 + 长时间未访问
            age = now - created_at
            last_access_age = now - last_accessed
            
            if (score < threshold and 
                age > max_age_seconds and 
                last_access_age > max_age_seconds):
                
                scored_point = models.ScoredPoint(
                    id=point.id,
                    version=0,
                    score=score,
                    payload=payload,
                    vector=point.vector
                )
                record = MemoryRecord.from_qdrant_point(scored_point)
                low_score_memories.append(record)
        
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
                "collection_status": collection_info.status,
                "vectors_count": collection_info.vectors_count
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