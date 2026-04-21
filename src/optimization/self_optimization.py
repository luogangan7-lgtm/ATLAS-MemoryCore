"""
夜间自优化循环 - 基于评分系统的记忆生命周期管理
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..core.scoring import MemoryScoringEngine, get_default_scoring_engine
from ..core.storage import MemoryStorage, get_default_storage

logger = logging.getLogger(__name__)


class SelfOptimizationLoop:
    """自优化循环管理器"""
    
    def __init__(self, 
                 storage: Optional[MemoryStorage] = None,
                 scoring_engine: Optional[MemoryScoringEngine] = None):
        self.storage = storage or get_default_storage()
        self.scoring_engine = scoring_engine or get_default_scoring_engine()
        self.optimization_log = []
    
    async def run_full_optimization(self) -> Dict[str, Any]:
        """
        运行完整的优化循环
        
        Returns:
            优化统计信息
        """
        logger.info("开始夜间自优化循环")
        
        stats = {
            "total_memories": 0,
            "upgraded_to_qmd": 0,
            "forgotten": 0,
            "demoted": 0,
            "errors": 0,
            "start_time": datetime.now().isoformat(),
        }
        
        try:
            # 1. 获取所有记忆
            memories = await self.storage.search_memories(
                query="",  # 空查询获取所有
                limit=1000,
                score_threshold=0.0
            )
            
            stats["total_memories"] = len(memories)
            
            # 2. 对每个记忆进行评分和优化
            for memory in memories:
                try:
                    await self._optimize_single_memory(memory, stats)
                except Exception as e:
                    logger.error(f"优化记忆失败: {e}")
                    stats["errors"] += 1
            
            # 3. 记录优化日志
            self._log_optimization(stats)
            
            logger.info(f"优化完成: {stats}")
            
        except Exception as e:
            logger.error(f"优化循环失败: {e}")
            stats["errors"] += 1
        
        stats["end_time"] = datetime.now().isoformat()
        return stats
    
    async def _optimize_single_memory(self, memory: Dict[str, Any], stats: Dict[str, Any]):
        """优化单个记忆"""
        memory_id = memory.get("id")
        text = memory.get("text", "")
        metadata = memory.get("metadata", {})
        
        # 计算当前评分
        memory_data = {
            "text": text,
            "metadata": metadata,
            "usage_history": metadata.get("usage_history", [])
        }
        
        score = self.scoring_engine.calculate_score(memory_data)
        
        # 判断优化动作
        if self.scoring_engine.should_upgrade_to_qmd(score):
            # 升级到QMD
            await self._upgrade_to_qmd(memory_id, text, metadata, score)
            stats["upgraded_to_qmd"] += 1
            logger.info(f"记忆升级到QMD: {memory_id[:8]} (分数: {score:.2f})")
            
        elif self.scoring_engine.should_forget(score):
            # 遗忘（删除）
            await self.storage.delete_memory(memory_id)
            stats["forgotten"] += 1
            logger.info(f"记忆遗忘: {memory_id[:8]} (分数: {score:.2f})")
            
        elif score < 0.5:
            # 降权（降低重要性）
            await self._demote_memory(memory_id, metadata, score)
            stats["demoted"] += 1
            logger.debug(f"记忆降权: {memory_id[:8]} (分数: {score:.2f})")
        
        # 更新记忆评分
        metadata["last_score"] = score
        metadata["last_optimized"] = datetime.now().isoformat()
        await self.storage.update_memory_metadata(memory_id, metadata)
    
    async def _upgrade_to_qmd(self, memory_id: str, text: str, 
                             metadata: Dict[str, Any], score: float):
        """将记忆升级到QMD文件系统"""
        try:
            # 1. 创建QMD目录结构
            qmd_dir = Path("/Volumes/data/openclaw_workspace/memory/qmd")
            qmd_dir.mkdir(parents=True, exist_ok=True)
            
            # 2. 按类别组织
            category = metadata.get("category", "other")
            category_dir = qmd_dir / category
            category_dir.mkdir(exist_ok=True)
            
            # 3. 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{category}_{timestamp}_{memory_id[:8]}.md"
            filepath = category_dir / filename
            
            # 4. 写入QMD文件
            qmd_content = self._format_qmd_content(text, metadata, score)
            filepath.write_text(qmd_content, encoding="utf-8")
            
            # 5. 在Qdrant中标记为已升级
            metadata["qmd_upgraded"] = True
            metadata["qmd_path"] = str(filepath)
            metadata["qmd_upgraded_at"] = datetime.now().isoformat()
            
            # 6. 可选：从Qdrant中删除原始记忆（保留元数据）
            # await self.storage.delete_memory(memory_id)
            
            logger.info(f"QMD升级完成: {filepath}")
            
        except Exception as e:
            logger.error(f"QMD升级失败: {e}")
            raise
    
    def _format_qmd_content(self, text: str, metadata: Dict[str, Any], score: float) -> str:
        """格式化QMD文件内容"""
        category = metadata.get("category", "other")
        created_at = metadata.get("created_at", datetime.now().isoformat())
        importance = metadata.get("importance", 0.5)
        tags = metadata.get("tags", [])
        
        content = f"""# 记忆升级记录

## 基本信息
- **ID**: {metadata.get('id', 'unknown')}
- **类别**: {category}
- **评分**: {score:.2f}
- **重要性**: {importance:.2f}
- **创建时间**: {created_at}
- **升级时间**: {datetime.now().isoformat()}

## 标签
{', '.join(tags) if tags else '无'}

## 原始内容
{text}

## 上下文信息
- **来源**: {metadata.get('source', 'unknown')}
- **创建者**: {metadata.get('created_by', 'unknown')}
- **使用次数**: {len(metadata.get('usage_history', []))}

## 优化说明
此记忆因评分达到升级阈值({score:.2f} ≥ 0.85)而被升级到QMD长期存储。
"""
        return content
    
    async def _demote_memory(self, memory_id: str, metadata: Dict[str, Any], score: float):
        """降权记忆（降低重要性）"""
        current_importance = metadata.get("importance", 0.5)
        new_importance = max(current_importance * 0.7, 0.1)  # 降低30%，最低0.1
        
        metadata["importance"] = new_importance
        metadata["demoted_at"] = datetime.now().isoformat()
        metadata["demotion_reason"] = f"低评分: {score:.2f}"
        
        await self.storage.update_memory_metadata(memory_id, metadata)
    
    def _log_optimization(self, stats: Dict[str, Any]):
        """记录优化日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "stats": stats,
            "optimization_log": self.optimization_log
        }
        
        # 保存到日志文件
        log_dir = Path("/Volumes/data/openclaw_workspace/logs/optimization")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"optimization_{date_str}.json"
        
        # 读取现有日志或创建新日志
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                existing_logs = json.load(f)
        else:
            existing_logs = []
        
        # 添加新日志
        existing_logs.append(log_entry)
        
        # 保存（只保留最近30天）
        if len(existing_logs) > 30:
            existing_logs = existing_logs[-30:]
        
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(existing_logs, f, indent=2, ensure_ascii=False)
    
    async def schedule_nightly_optimization(self):
        """调度夜间优化任务"""
        # 计算到凌晨3点的时间
        now = datetime.now()
        target_time = now.replace(hour=3, minute=0, second=0, microsecond=0)
        
        if now >= target_time:
            target_time += timedelta(days=1)
        
        wait_seconds = (target_time - now).total_seconds()
        
        logger.info(f"调度夜间优化，等待 {wait_seconds:.0f} 秒")
        
        # 等待到目标时间
        await asyncio.sleep(wait_seconds)
        
        # 运行优化
        await self.run_full_optimization()


def get_default_optimization_loop() -> SelfOptimizationLoop:
    """获取默认优化循环"""
    return SelfOptimizationLoop()