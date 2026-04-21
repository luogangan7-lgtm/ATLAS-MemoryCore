"""
记忆生命周期管理器 - 融合架构核心
结合自优化记忆体和Aegis-Cortex Token经济学
"""

import time
import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
from datetime import datetime, timedelta

from .qdrant_storage import QdrantMemoryStorage, MemoryCategory, MemoryImportance, MemoryRecord
from .embedding_v2 import EnhancedEmbeddingModel, get_embedding_model


class MemoryLifecycleStage(Enum):
    """记忆生命周期阶段"""
    CREATED = "created"        # 创建
    SCORED = "scored"          # 评分
    CLASSIFIED = "classified"  # 分类
    UPGRADED = "upgraded"      # 升级到QMD
    ARCHIVED = "archived"      # 归档
    FORGOTTEN = "forgotten"    # 遗忘


@dataclass
class LifecycleEvent:
    """生命周期事件"""
    memory_id: str
    stage: MemoryLifecycleStage
    timestamp: float
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "memory_id": self.memory_id,
            "stage": self.stage.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


class EnhancedScoringEngine:
    """
    增强评分引擎 - 5维度智能评分
    基于艾宾浩斯遗忘曲线 + 使用模式分析
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._default_config()
        
        # 权重配置
        self.weights = {
            "relevance": 0.30,      # 相关性权重
            "time_decay": 0.25,     # 时间衰减权重
            "usage_frequency": 0.20,  # 使用频率权重
            "result_value": 0.15,   # 结果价值权重
            "complexity": 0.10      # 复杂度权重
        }
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            "half_life_days": 30,      # 半衰期（天）
            "max_age_days": 365,       # 最大年龄（天）
            "usage_boost_factor": 0.1,  # 使用频率提升因子
            "complexity_penalty": 0.05,  # 复杂度惩罚
            "min_score": 0.0,          # 最小分数
            "max_score": 1.0           # 最大分数
        }
    
    def calculate_score(self, memory_data: Dict) -> float:
        """
        计算综合评分
        
        Args:
            memory_data: 记忆数据，包含：
                - text: 文本内容
                - metadata: 元数据
                - usage_history: 使用历史
                - created_at: 创建时间
                - last_accessed: 最后访问时间
                - access_count: 访问次数
                
        Returns:
            综合评分 (0-1)
        """
        # 提取数据
        metadata = memory_data.get("metadata", {})
        usage_history = memory_data.get("usage_history", [])
        created_at = metadata.get("created_at", time.time())
        last_accessed = metadata.get("last_accessed", time.time())
        access_count = metadata.get("access_count", 0)
        importance = metadata.get("importance", "medium")
        
        # 计算各维度分数
        relevance_score = self._calculate_relevance(memory_data)
        time_decay_score = self._calculate_time_decay(created_at, last_accessed)
        usage_frequency_score = self._calculate_usage_frequency(access_count, usage_history)
        result_value_score = self._calculate_result_value(memory_data)
        complexity_score = self._calculate_complexity(memory_data)
        
        # 重要性加成
        importance_boost = self._get_importance_boost(importance)
        
        # 加权综合评分
        weighted_score = (
            relevance_score * self.weights["relevance"] +
            time_decay_score * self.weights["time_decay"] +
            usage_frequency_score * self.weights["usage_frequency"] +
            result_value_score * self.weights["result_value"] +
            complexity_score * self.weights["complexity"]
        )
        
        # 应用重要性加成
        final_score = min(1.0, weighted_score + importance_boost)
        
        # 确保在有效范围内
        return max(self.config["min_score"], min(self.config["max_score"], final_score))
    
    def _calculate_relevance(self, memory_data: Dict) -> float:
        """计算相关性分数"""
        # 基于文本长度、关键词密度等
        text = memory_data.get("text", "")
        metadata = memory_data.get("metadata", {})
        
        score = 0.5  # 基础分数
        
        # 文本长度影响
        text_length = len(text)
        if text_length > 200:
            score += 0.2
        elif text_length > 100:
            score += 0.1
        elif text_length < 20:
            score -= 0.1
        
        # 重要性加成
        importance = metadata.get("importance", "medium")
        if importance == "critical":
            score += 0.3
        elif importance == "high":
            score += 0.2
        elif importance == "low":
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _calculate_time_decay(self, created_at: float, last_accessed: float) -> float:
        """计算时间衰减分数（基于艾宾浩斯遗忘曲线）"""
        now = time.time()
        
        # 计算年龄（天）
        age_days = (now - created_at) / (24 * 3600)
        last_access_days = (now - last_accessed) / (24 * 3600)
        
        # 基础衰减（基于创建时间）
        half_life = self.config["half_life_days"]
        base_decay = np.exp(-np.log(2) * age_days / half_life)
        
        # 访问衰减（基于最后访问时间）
        access_decay = np.exp(-np.log(2) * last_access_days / (half_life / 2))
        
        # 综合衰减
        decay_factor = 0.7 * base_decay + 0.3 * access_decay
        
        return max(0.0, min(1.0, decay_factor))
    
    def _calculate_usage_frequency(self, access_count: int, usage_history: List) -> float:
        """计算使用频率分数"""
        if access_count == 0:
            return 0.3  # 基础分数
        
        # 基于访问次数
        usage_score = min(1.0, access_count * 0.1)
        
        # 基于使用历史模式
        if usage_history:
            recent_usage = len([h for h in usage_history 
                              if time.time() - h.get("timestamp", 0) < 7 * 24 * 3600])
            recent_score = min(0.3, recent_usage * 0.05)
            usage_score += recent_score
        
        return max(0.0, min(1.0, usage_score))
    
    def _calculate_result_value(self, memory_data: Dict) -> float:
        """计算结果价值分数"""
        # 基于记忆的实际价值（需要业务逻辑）
        # 这里使用简单的启发式规则
        
        text = memory_data.get("text", "").lower()
        metadata = memory_data.get("metadata", {})
        category = metadata.get("category", "")
        
        score = 0.5
        
        # 关键词检测
        value_keywords = ["成功", "完成", "解决", "优化", "提升", "重要", "关键"]
        penalty_keywords = ["失败", "错误", "问题", "bug", "修复"]
        
        for keyword in value_keywords:
            if keyword in text:
                score += 0.05
        
        for keyword in penalty_keywords:
            if keyword in text:
                score -= 0.03
        
        # 分类加成
        if category in ["work", "project", "critical"]:
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _calculate_complexity(self, memory_data: Dict) -> float:
        """计算复杂度分数（复杂度越高，记忆难度越大）"""
        text = memory_data.get("text", "")
        
        # 简单启发式：文本越长、句子越多，复杂度越高
        text_length = len(text)
        sentence_count = text.count("。") + text.count(".") + text.count("!") + text.count("?")
        
        complexity = 0.5
        
        if text_length > 500:
            complexity += 0.3
        elif text_length > 200:
            complexity += 0.2
        elif text_length < 50:
            complexity -= 0.1
        
        if sentence_count > 5:
            complexity += 0.1
        
        # 复杂度越高，分数越低（因为更难记忆）
        # 但我们希望复杂度高的记忆有更高价值，所以这里做反向处理
        complexity_score = 1.0 - (complexity * self.config["complexity_penalty"])
        
        return max(0.0, min(1.0, complexity_score))
    
    def _get_importance_boost(self, importance: str) -> float:
        """获取重要性加成"""
        importance_map = {
            "critical": 0.3,
            "high": 0.2,
            "medium": 0.1,
            "low": 0.0
        }
        return importance_map.get(importance, 0.1)
    
    def time_decay(self, age_days: float, half_life_days: float = None) -> float:
        """
        计算时间衰减因子
        
        Args:
            age_days: 年龄（天）
            half_life_days: 半衰期（天）
            
        Returns:
            衰减因子 (0-1)
        """
        if half_life_days is None:
            half_life_days = self.config["half_life_days"]
        
        if half_life_days <= 0:
            return 0.0
        
        decay = np.exp(-np.log(2) * age_days / half_life_days)
        return max(0.0, min(1.0, decay))


class MemoryLifecycleManager:
    """
    记忆生命周期管理器
    负责记忆的创建、评分、升级、遗忘全周期管理
    """
    
    def __init__(self, storage_path: str = None, qmd_path: str = None):
        """
        初始化生命周期管理器
        
        Args:
            storage_path: Qdrant存储路径
            qmd_path: QMD文件路径
        """
        # 初始化组件
        self.storage = QdrantMemoryStorage(storage_path=storage_path)
        self.embedding_model = get_embedding_model()
        self.scoring_engine = EnhancedScoringEngine()
        
        # QMD配置
        self.qmd_path = qmd_path or "~/.atlas_memory/qmd_memories.md"
        
        # 生命周期事件记录
        self.lifecycle_events = []
        
        # 配置
        self.config = {
            "upgrade_threshold": 0.85,      # 升级到QMD的阈值
            "forget_threshold": 0.3,        # 遗忘阈值
            "max_age_days": 7,              # 最大年龄（天）
            "min_access_count": 3,          # 最小访问次数
            "auto_optimize_interval": 86400,  # 自动优化间隔（秒）
            "last_optimization": 0
        }
    
    def capture_memory(self, text: str, category: MemoryCategory, 
                      importance: MemoryImportance, tags: List[str] = None) -> str:
        """
        捕获记忆 - 零Token捕获层入口
        
        Args:
            text: 记忆文本
            category: 记忆分类
            importance: 重要性级别
            tags: 标签列表
            
        Returns:
            记忆ID
        """
        # 1. 生成嵌入向量（零Token成本）
        embedding = self.embedding_model.encode_single(text)
        
        # 2. 存储到Qdrant
        memory_id = self.storage.store_memory(
            text=text,
            embedding=embedding,
            category=category,
            importance=importance,
            tags=tags or []
        )
        
        # 3. 记录生命周期事件
        self._record_lifecycle_event(
            memory_id=memory_id,
            stage=MemoryLifecycleStage.CREATED,
            metadata={
                "text_length": len(text),
                "category": category.value,
                "importance": importance.value,
                "tags": tags or []
            }
        )
        
        print(f"📝 记忆捕获完成: ID={memory_id[:8]}, 分类={category.value}, 重要性={importance.value}")
        
        return memory_id
    
    def retrieve_memories(self, query: str, limit: int = 5, 
                         category: Optional[MemoryCategory] = None,
                         similarity_threshold: float = 0.82) -> List[MemoryRecord]:
        """
        检索记忆 - 惰性检索引擎
        
        Args:
            query: 查询文本
            limit: 返回数量
            category: 分类过滤
            similarity_threshold: 相似度阈值
            
        Returns:
            记忆记录列表
        """
        # 1. 生成查询嵌入
        query_embedding = self.embedding_model.encode_single(query)
        
        # 2. 从Qdrant搜索
        memories = self.storage.search_memories(
            query_embedding=query_embedding,
            limit=limit,
            category=category,
            similarity_threshold=similarity_threshold
        )
        
        # 3. 按评分排序
        memories.sort(key=lambda x: x.score, reverse=True)
        
        # 4. 记录检索事件
        for memory in memories:
            self._record_lifecycle_event(
                memory_id=memory.id,
                stage=MemoryLifecycleStage.SCORED,
                metadata={
                    "query": query,
                    "similarity_threshold": similarity_threshold,
                    "retrieved_at": time.time()
                }
            )
        
        print(f"🔍 记忆检索完成: 查询='{query[:30]}...', 找到{len(memories)}条记忆")
        
        return memories
    
    def _record_lifecycle_event(self, memory_id: str, stage: MemoryLifecycleStage, 
                               metadata: Dict = None):
        """记录生命周期事件"""
        event = LifecycleEvent(
            memory_id=memory_id,
            stage=stage,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        self.lifecycle_events.append(event)
        
        # 限制事件数量
        if len(self.lifecycle_events) > 1000:
            self.lifecycle_events = self.lifecycle_events[-1000:]
    
    def optimize_memories(self, force: bool = False):
        """
        优化记忆 - 夜间自净化循环
        
        Args:
            force: 强制优化（忽略时间间隔）
        """
        now = time.time()
        last_opt = self.config["last_optimization"]
        interval = self.config["auto_optimize_interval"]
        
        if not force and (now - last_opt) < interval:
            print(f"⏰ 距离上次优化不足{interval/3600:.1f}小时，跳过")
            return
        
        print("🔄 开始记忆优化循环...")
        
        # 1. 自动遗忘低价值记忆
        self._auto_forget_low_value_memories()
        
        # 2. 自动升级高价值记忆到QMD
        self._auto_upgrade_high_value_memories()
        
        # 3. 重新评分所有记忆
        self._recalculate_all_scores()
        
        # 4. 清理过期事件
        self._cleanup_old_events()
        
        # 更新最后优化时间
        self.config["last_optimization"] = now
        
        print(f"✅ 记忆优化完成")
    
    def _auto_forget_low_value_memories(self):
        """自动遗忘低价值记忆"""
        threshold = self.config["forget_threshold"]
        max_age_days = self.config["max_age_days"]
        
        # 获取低评分记忆
        low_score_memories = self.storage.get_low_score_memories(
            threshold=threshold,
            max_age_days=max_age_days
        )
        
        print(f"🗑️  找到{len(low_score_memories)}条低价值记忆（评分<{threshold}, 年龄>{max_age_days}天）")
        
        # 遗忘记忆
        forgotten_count = 0
        for memory in low_score_memories:
            if self.storage.delete_memory(memory.id):
                self._record_lifecycle_event(
                    memory_id=memory.id,
                    stage=MemoryLifecycleStage.FORGOTTEN,
                    metadata={
                        "score": memory.score,
                        "text_preview": memory.text[:50]
                    }
                )
                forgotten_count += 1
        
        print(f"  已遗忘{forgotten_count}条记忆")
    
    def _auto_upgrade_high_value_memories(self):
        """自动升级高价值记忆到QMD"""
        threshold = self.config["upgrade_threshold"]
        
        # 获取高评分记忆
        high_score_memories = self.storage.get_high_score_memories(threshold=threshold)
        
        print(f"⬆️  找到{len(high_score_memories)}条高价值记忆（评分>={threshold}）")
        
        # 升级到QMD
        upgraded_count = 0
        for memory in high_score_memories:
            if self._upgrade_to_qmd(memory):
                # 从Qdrant中删除（已升级到永久存储）
                self.storage.delete_memory(memory.id)
                
                self._record_lifecycle_event(
                    memory_id=memory.id,
                    stage=MemoryLifecycleStage.UPGRADED,
                    metadata={
                        "score": memory.score,
                        "text_preview": memory.text[:50],
                        "upgraded_at": time.time()
                    }
                )
                upgraded_count += 1
        
        print(f"  已升级{upgraded_count}条记忆到QMD")
    
    def _upgrade_to_qmd(self, memory: MemoryRecord) -> bool:
        """升级记忆到QMD文件"""
        try:
            import os
            
            # 确保QMD目录存在
            qmd_dir = os.path.dirname(os.path.expanduser(self.qmd_path))
            os.makedirs(qmd_dir, exist_ok=True)
            
            # 准备QMD条目
            timestamp = datetime.fromtimestamp(memory.metadata.created_at).strftime('%Y-%m-%d %H:%M:%S')
            category = memory.metadata.category.value
            importance = memory.metadata.importance.value
            score = memory.score
            
            qmd_entry = f"""
## {timestamp} - {category} ({importance})

**评分**: {score:.3f}
**标签**: {', '.join(memory.metadata.tags) if memory.metadata.tags else '无'}
**访问次数**: {memory.metadata.access_count}

{memory.text}

---
"""
            
            # 追加到QMD文件
            with open(os.path.expanduser(self.qmd_path), 'a', encoding='utf-8') as f:
                f.write(qmd_entry)
            
            return True
            
        except Exception as e:
            print(f"❌ QMD升级失败: {e}")
            return False
    
    def _recalculate_all_scores(self):
        """重新计算所有记忆的评分"""
        # 获取所有记忆
        all_points = self.storage.client.scroll(
            collection_name=self.storage.collection_name,
            limit=10000
        )[0]
        
        print(f"📊 重新评分{len(all_points)}条记忆")
        
        updated_count = 0
        for point in all_points:
            try:
                payload = point.payload
                metadata = payload.get("metadata", {})
                
                # 准备记忆数据
                memory_data = {
                    "text": payload.get("text", ""),
                    "metadata": metadata,
                    "usage_history": [],  # 实际使用时需要记录使用历史
                    "created_at": metadata.get("created_at", time.time()),
                    "last_accessed": metadata.get("last_accessed", time.time()),
                    "access_count": metadata.get("access_count", 0)
                }
                
                # 计算新评分
                new_score = self.scoring_engine.calculate_score(memory_data)
                
                # 更新评分
                payload["score"] = new_score
                
                # 更新到Qdrant
                self.storage.client.upsert(
                    collection_name=self.storage.collection_name,
                    points=[self.storage.client.http.models.PointStruct(
                        id=point.id,
                        vector=point.vector,
                        payload=payload
                    )]
                )
                
                updated_count += 1
                
                # 记录评分事件
                self._record_lifecycle_event(
                    memory_id=str(point.id),
                    stage=MemoryLifecycleStage.SCORED,
                    metadata={
                        "old_score": payload.get("score", 0.5),
                        "new_score": new_score,
                        "recalculated_at": time.time()
                    }
                )
                
            except Exception as e:
                print(f"❌ 重新评分失败: {e}")
        
        print(f"  已更新{updated_count}条记忆的评分")
    
    def _cleanup_old_events(self):
        """清理旧的生命周期事件"""
        # 保留最近30天的事件
        cutoff_time = time.time() - (30 * 24 * 3600)
        
        original_count = len(self.lifecycle_events)
        self.lifecycle_events = [
            event for event in self.lifecycle_events
            if event.timestamp > cutoff_time
        ]
        
        removed_count = original_count - len(self.lifecycle_events)
        if removed_count > 0:
            print(f"🧹 清理了{removed_count}个旧的生命周期事件")
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        # 存储统计
        storage_stats = self.storage.get_statistics()
        
        # 生命周期事件统计
        stage_counts = {}
        for event in self.lifecycle_events:
            stage = event.stage.value
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        
        # 嵌入模型信息
        embedding_info = self.embedding_model.get_model_info()
        
        return {
            "storage": storage_stats,
            "lifecycle_events": {
                "total": len(self.lifecycle_events),
                "by_stage": stage_counts
            },
            "embedding_model": embedding_info,
            "config": self.config,
            "last_optimization": datetime.fromtimestamp(self.config["last_optimization"]).strftime('%Y-%m-%d %H:%M:%S') if self.config["last_optimization"] > 0 else "从未"
        }
    
    def export_backup(self, backup_dir: str):
        """导出备份"""
        import os
        import json
        
        os.makedirs(backup_dir, exist_ok=True)
        
        # 1. 导出Qdrant数据
        qdrant_file = os.path.join(backup_dir, "qdrant_backup.json")
        self.storage.export_to_json(qdrant_file)
        
        # 2. 导出生命周期事件
        events_file = os.path.join(backup_dir, "lifecycle_events.json")
        events_data = [event.to_dict() for event in self.lifecycle_events]
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, ensure_ascii=False, indent=2)
        
        # 3. 导出配置
        config_file = os.path.join(backup_dir, "config.json")
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        
        print(f"💾 备份已导出到: {backup_dir}")
    
    def import_backup(self, backup_dir: str):
        """导入备份"""
        import os
        import json
        
        # 1. 导入Qdrant数据
        qdrant_file = os.path.join(backup_dir, "qdrant_backup.json")
        if os.path.exists(qdrant_file):
            self.storage.import_from_json(qdrant_file)
        
        # 2. 导入生命周期事件
        events_file = os.path.join(backup_dir, "lifecycle_events.json")
        if os.path.exists(events_file):
            with open(events_file, 'r', encoding='utf-8') as f:
                events_data = json.load(f)
            
            self.lifecycle_events = []
            for event_dict in events_data:
                event = LifecycleEvent(
                    memory_id=event_dict["memory_id"],
                    stage=MemoryLifecycleStage(event_dict["stage"]),
                    timestamp=event_dict["timestamp"],
                    metadata=event_dict.get("metadata", {})
                )
                self.lifecycle_events.append(event)
        
        # 3. 导入配置
        config_file = os.path.join(backup_dir, "config.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config.update(json.load(f))
        
        print(f"📥 备份已从{backup_dir}导入")


def test_lifecycle_manager():
    """测试生命周期管理器"""
    print("🧪 测试记忆生命周期管理器...")
    
    # 创建管理器
    manager = MemoryLifecycleManager()
    
    # 测试记忆捕获
    print("\n📝 测试记忆捕获:")
    memory_id = manager.capture_memory(
        text="ATLAS记忆系统开发完成第一阶段，基础框架已就绪",
        category=MemoryCategory.PROJECT,
        importance=MemoryImportance.HIGH,
        tags=["atlas", "memory", "development"]
    )
    print(f"  记忆ID: {memory_id}")
    
    # 测试记忆检索
    print("\n🔍 测试记忆检索:")
    memories = manager.retrieve_memories(
        query="ATLAS记忆系统",
        limit=3
    )
    print(f"  找到{len(memories)}条相关记忆")
    for i, memory in enumerate(memories):
        print(f"  {i+1}. {memory.text[:50]}... (评分: {memory.score:.3f})")
    
    # 测试统计信息
    print("\n📊 测试统计信息:")
    stats = manager.get_statistics()
    print(f"  存储统计: {stats['storage']}")
    print(f"  生命周期事件: {stats['lifecycle_events']['total']}个")
    
    # 测试优化循环
    print("\n🔄 测试优化循环:")
    manager.optimize_memories(force=True)
    
    # 再次获取统计
    stats = manager.get_statistics()
    print(f"  优化后统计: {stats['storage']}")
    
    print("\n✅ 生命周期管理器测试完成")


if __name__ == "__main__":
    test_lifecycle_manager()