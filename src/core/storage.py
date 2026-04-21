"""
记忆存储模块 - Qdrant向量数据库集成
"""

import logging
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from .embedding import EmbeddingModel, get_default_embedding_model

logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    """记忆分类"""
    LEARNING = "learning"
    TRADING = "trading"
    CODE = "code"
    PERSONAL = "personal"
    WORK = "work"
    PROJECT = "project"
    OTHER = "other"


@dataclass
class MemoryMetadata:
    """记忆元数据"""
    category: MemoryCategory = MemoryCategory.OTHER
    importance: float = 0.5  # 0.0-1.0
    tags: List[str] = None
    source: str = "openclaw"
    created_by: str = "atlas"
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["category"] = self.category.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryMetadata":
        """从字典创建"""
        if "category" in data and isinstance(data["category"], str):
            data["category"] = MemoryCategory(data["category"])
        return cls(**data)


@dataclass
class MemoryRecord:
    """记忆记录"""
    id: str
    text: str
    vector: List[float]
    metadata: MemoryMetadata
    created_at: datetime
    updated_at: datetime
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    score: float = 0.5  # 当前评分
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "text": self.text,
            "vector": self.vector,
            "metadata": self.metadata.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "score": self.score,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        """从字典创建"""
        # 处理日期时间
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        last_accessed = None
        if data.get("last_accessed"):
            last_accessed = datetime.fromisoformat(data["last_accessed"].replace("Z", "+00:00"))
        
        # 处理元数据
        metadata = MemoryMetadata.from_dict(data["metadata"])
        
        return cls(
            id=data["id"],
            text=data["text"],
            vector=data["vector"],
            metadata=metadata,
            created_at=created_at,
            updated_at=updated_at,
            access_count=data.get("access_count", 0),
            last_accessed=last_accessed,
            score=data.get("score", 0.5),
        )


class MemoryStorage:
    """记忆存储管理器"""
    
    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "atlas_memories",
        embedding_model: Optional[EmbeddingModel] = None,
        vector_size: int = 768,  # nomic-embed-text维度
    ):
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.embedding_model = embedding_model or get_default_embedding_model()
        self.vector_size = vector_size
        
        # 初始化客户端
        self.client = QdrantClient(url=qdrant_url)
        
        # 确保集合存在
        self._ensure_collection()
    
    def _ensure_collection(self):
        """确保向量集合存在"""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"创建集合: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
            else:
                logger.info(f"集合已存在: {self.collection_name}")
        
        except Exception as e:
            logger.error(f"确保集合存在失败: {e}")
            raise
    
    def store(
        self,
        text: str,
        metadata: Optional[MemoryMetadata] = None,
        vector: Optional[List[float]] = None,
    ) -> str:
        """
        存储记忆
        
        Args:
            text: 记忆文本
            metadata: 元数据
            vector: 预计算的向量（可选）
            
        Returns:
            记忆ID
        """
        try:
            # 生成唯一ID
            memory_id = str(uuid.uuid4())
            
            # 创建元数据
            if metadata is None:
                metadata = MemoryMetadata()
            
            # 计算向量（如果未提供）
            if vector is None:
                vector = self.embedding_model.encode_single(text)
            
            # 创建记录
            now = datetime.now()
            record = MemoryRecord(
                id=memory_id,
                text=text,
                vector=vector,
                metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            
            # 存储到Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=memory_id,
                        vector=vector,
                        payload=record.to_dict(),
                    )
                ],
            )
            
            logger.info(f"记忆存储成功: {memory_id}")
            return memory_id
        
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")
            raise
    
    def retrieve(self, memory_id: str) -> Optional[MemoryRecord]:
        """
        检索单个记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            记忆记录或None
        """
        try:
            result = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[memory_id],
                with_payload=True,
                with_vectors=True,
            )
            
            if not result:
                return None
            
            point = result[0]
            payload = point.payload
            
            # 更新访问统计
            self._update_access_stats(memory_id)
            
            return MemoryRecord.from_dict(payload)
        
        except Exception as e:
            logger.error(f"检索记忆失败: {e}")
            return None
    
    def search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        filter_conditions: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryRecord]:
        """
        搜索相关记忆
        
        Args:
            query: 查询文本
            limit: 返回数量限制
            threshold: 相似度阈值
            filter_conditions: 过滤条件
            
        Returns:
            记忆记录列表
        """
        try:
            # 编码查询文本
            query_vector = self.embedding_model.encode_single(query)
            
            # 构建过滤器
            filter_ = None
            if filter_conditions:
                filter_ = self._build_filter(filter_conditions)
            
            # 执行搜索
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=filter_,
                limit=limit,
                score_threshold=threshold,
                with_payload=True,
                with_vectors=True,
            )
            
            # 转换结果
            records = []
            for hit in search_result:
                if hit.score >= threshold:
                    record = MemoryRecord.from_dict(hit.payload)
                    
                    # 更新访问统计
                    self._update_access_stats(record.id)
                    
                    records.append(record)
            
            logger.info(f"搜索完成，找到 {len(records)} 条相关记忆")
            return records
        
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            return []
    
    def _update_access_stats(self, memory_id: str):
        """更新访问统计"""
        try:
            # 获取当前记录
            result = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[memory_id],
                with_payload=True,
            )
            
            if not result:
                return
            
            point = result[0]
            payload = point.payload
            
            # 更新统计
            payload["access_count"] = payload.get("access_count", 0) + 1
            payload["last_accessed"] = datetime.now().isoformat()
            
            # 更新到数据库
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=memory_id,
                        vector=point.vector,
                        payload=payload,
                    )
                ],
            )
        
        except Exception as e:
            logger.warning(f"更新访问统计失败: {e}")
    
    def _build_filter(self, conditions: Dict[str, Any]) -> models.Filter:
        """构建Qdrant过滤器"""
        must_conditions = []
        
        for key, value in conditions.items():
            if isinstance(value, list):
                # 列表条件
                must_conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{key}",
                        match=models.MatchAny(any=value),
                    )
                )
            else:
                # 单值条件
                must_conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{key}",
                        match=models.MatchValue(value=value),
                    )
                )
        
        return models.Filter(must=must_conditions)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            # 获取集合信息
            collection_info = self.client.get_collection(self.collection_name)
            
            # 获取点数量
            count_result = self.client.count(
                collection_name=self.collection_name,
                exact=True,
            )
            
            return {
                "collection_name": self.collection_name,
                "vector_size": self.vector_size,
                "total_memories": count_result.count,
                "vectors_count": collection_info.vectors_count,
                "status": collection_info.status,
                "optimizer_status": collection_info.optimizer_status,
            }
        
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[memory_id]),
            )
            logger.info(f"记忆删除成功: {memory_id}")
            return True
        
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False
    
    def clear_all(self) -> bool:
        """清空所有记忆"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(must=[])
                ),
            )
            logger.info("所有记忆已清空")
            return True
        
        except Exception as e:
            logger.error(f"清空记忆失败: {e}")
            return False


# 全局实例
_default_storage = None

def get_default_storage() -> MemoryStorage:
    """获取默认存储实例"""
    global _default_storage
    if _default_storage is None:
        _default_storage = MemoryStorage()
    return _default_storage