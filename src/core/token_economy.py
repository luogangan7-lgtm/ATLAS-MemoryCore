"""
Token经济监控模块 - Aegis-Cortex V6.2核心组件
实时监控Token消耗，成本预测，自动降级策略
"""

import time
import json
import hashlib
from typing import Dict, List, Tuple, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from enum import Enum

from .aegis_config import TokenEconomyConfig, AegisCortexConfig

logger = logging.getLogger(__name__)


class TokenOperation(str, Enum):
    """Token操作类型"""
    CAPTURE = "capture"  # 记忆捕获
    RETRIEVAL = "retrieval"  # 记忆检索
    COMPRESSION = "compression"  # 压缩
    GENERATION = "generation"  # 响应生成
    OPTIMIZATION = "optimization"  # 夜间优化


class CostLevel(str, Enum):
    """成本级别"""
    LOW = "low"  # 低成本
    MEDIUM = "medium"  # 中等成本
    HIGH = "high"  # 高成本
    CRITICAL = "critical"  # 临界成本


@dataclass
class TokenUsage:
    """Token使用记录"""
    
    operation: TokenOperation
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_rmb: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "operation": self.operation.value,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_rmb": self.cost_rmb,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


@dataclass
class CostPrediction:
    """成本预测"""
    
    predicted_daily_cost: float
    predicted_weekly_cost: float
    predicted_monthly_cost: float
    confidence: float  # 预测置信度 (0-1)
    based_on_days: int  # 基于多少天的数据
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "predicted_daily_cost": self.predicted_daily_cost,
            "predicted_weekly_cost": self.predicted_weekly_cost,
            "predicted_monthly_cost": self.predicted_monthly_cost,
            "confidence": self.confidence,
            "based_on_days": self.based_on_days,
            "timestamp": self.timestamp
        }


class TokenEconomyMonitor:
    """Token经济监控器"""
    
    def __init__(self, config: TokenEconomyConfig):
        self.config = config
        
        # 使用记录存储
        self.usage_records: List[TokenUsage] = []
        self.daily_costs: Dict[str, float] = {}  # 日期 -> 成本
        self.model_costs: Dict[str, float] = {}  # 模型 -> 总成本
        
        # 预测数据
        self.cost_predictions: List[CostPrediction] = []
        
        # 降级状态
        self.downgrade_level: CostLevel = CostLevel.LOW
        self.downgrade_reasons: List[str] = []
        
        # 监控状态
        self.start_time = time.time()
        self.total_cost = 0.0
        self.total_tokens = 0
        
        logger.info("Token经济监控器初始化完成")
    
    def record_usage(
        self,
        operation: TokenOperation,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_per_token: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TokenUsage:
        """
        记录Token使用
        
        Args:
            operation: 操作类型
            model: 模型名称
            input_tokens: 输入Token数
            output_tokens: 输出Token数
            cost_per_token: 每Token成本（人民币），如果为None则自动计算
            metadata: 额外元数据
            
        Returns:
            Token使用记录
        """
        # 计算总Token数
        total_tokens = input_tokens + output_tokens
        
        # 计算成本
        if cost_per_token is None:
            cost_per_token = self._get_cost_per_token(model, operation)
        
        cost_rmb = total_tokens * cost_per_token
        
        # 创建记录
        usage = TokenUsage(
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_rmb=cost_rmb,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        
        # 存储记录
        self.usage_records.append(usage)
        
        # 更新统计
        self.total_cost += cost_rmb
        self.total_tokens += total_tokens
        
        # 更新每日成本
        today = datetime.now().strftime("%Y-%m-%d")
        self.daily_costs[today] = self.daily_costs.get(today, 0.0) + cost_rmb
        
        # 更新模型成本
        self.model_costs[model] = self.model_costs.get(model, 0.0) + cost_rmb
        
        # 检查是否需要降级
        self._check_downgrade()
        
        # 检查警告阈值
        if self.config.token_cost_warning_threshold > 0:
            if cost_rmb > self.config.token_cost_warning_threshold:
                logger.warning(f"单次操作Token成本超过警告阈值: {cost_rmb:.2f}元 > {self.config.token_cost_warning_threshold}元")
        
        logger.debug(f"记录Token使用: {operation.value} - {model} - {total_tokens} tokens - {cost_rmb:.4f}元")
        
        return usage
    
    def _get_cost_per_token(self, model: str, operation: TokenOperation) -> float:
        """获取每Token成本（人民币）"""
        
        # 模型成本表（人民币/每千Token）
        # 注意：这是示例数据，实际成本可能不同
        model_costs = {
            # OpenAI模型
            "gpt-4": 0.42,  # 输入0.03美元/1K，输出0.06美元/1K，按7.0汇率
            "gpt-4-turbo": 0.21,
            "gpt-3.5-turbo": 0.007,
            
            # Anthropic模型
            "claude-3-opus": 0.105,
            "claude-3-sonnet": 0.021,
            "claude-3-haiku": 0.0014,
            
            # DeepSeek模型
            "deepseek-chat": 0.0014,
            "deepseek-coder": 0.0021,
            
            # 本地模型（近似成本，考虑电力和硬件折旧）
            "qwen2.5-7b": 0.00007,
            "llama3-8b": 0.0001,
            
            # 零Token操作
            "local-embedding": 0.0,
            "turboquant": 0.0,
        }
        
        # 获取基础成本
        base_cost = model_costs.get(model.lower(), 0.0014)  # 默认值
        
        # 根据操作类型调整
        operation_multipliers = {
            TokenOperation.CAPTURE: 0.0,  # 零Token捕获
            TokenOperation.RETRIEVAL: 0.1,  # 低Token检索
            TokenOperation.COMPRESSION: 0.05,  # 极低Token压缩
            TokenOperation.GENERATION: 1.0,  # 全成本生成
            TokenOperation.OPTIMIZATION: 0.0,  # 零Token优化
        }
        
        multiplier = operation_multipliers.get(operation, 1.0)
        
        return base_cost * multiplier / 1000  # 转换为每Token成本
    
    def _check_downgrade(self):
        """检查是否需要降级"""
        if not self.config.auto_downgrade_enabled:
            return
        
        # 计算预算使用率
        budget_usage = self._calculate_budget_usage()
        
        # 检查降级阈值
        new_level = self.downgrade_level
        
        if budget_usage >= self.config.downgrade_thresholds.get("critical", 0.9):
            new_level = CostLevel.CRITICAL
            reason = f"预算使用率超过临界阈值: {budget_usage:.1%}"
        elif budget_usage >= self.config.downgrade_thresholds.get("high", 0.75):
            new_level = CostLevel.HIGH
            reason = f"预算使用率超过高阈值: {budget_usage:.1%}"
        elif budget_usage >= self.config.downgrade_thresholds.get("medium", 0.5):
            new_level = CostLevel.MEDIUM
            reason = f"预算使用率超过中阈值: {budget_usage:.1%}"
        else:
            new_level = CostLevel.LOW
            reason = f"预算使用率正常: {budget_usage:.1%}"
        
        # 如果级别变化，记录原因
        if new_level != self.downgrade_level:
            self.downgrade_level = new_level
            self.downgrade_reasons.append(f"{datetime.now()}: {reason}")
            logger.info(f"Token经济降级到 {new_level.value} 级别: {reason}")
    
    def _calculate_budget_usage(self) -> float:
        """计算预算使用率"""
        if self.config.daily_token_budget is None:
            return 0.0
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_cost = self.daily_costs.get(today, 0.0)
        
        if self.config.daily_token_budget <= 0:
            return 0.0
        
        return today_cost / self.config.daily_token_budget
    
    def predict_costs(self) -> CostPrediction:
        """预测未来成本"""
        
        # 收集最近7天的数据
        recent_days = 7
        today = datetime.now()
        
        daily_costs_list = []
        for i in range(recent_days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            cost = self.daily_costs.get(date, 0.0)
            daily_costs_list.append(cost)
        
        # 计算平均每日成本
        if daily_costs_list:
            avg_daily_cost = sum(daily_costs_list) / len(daily_costs_list)
        else:
            avg_daily_cost = self.total_cost / max(1, (time.time() - self.start_time) / (24 * 3600))
        
        # 生成预测
        prediction = CostPrediction(
            predicted_daily_cost=avg_daily_cost,
            predicted_weekly_cost=avg_daily_cost * 7,
            predicted_monthly_cost=avg_daily_cost * 30,
            confidence=min(0.9, len(daily_costs_list) / 10),  # 基于数据量的置信度
            based_on_days=len(daily_costs_list),
            timestamp=time.time()
        )
        
        # 存储预测
        self.cost_predictions.append(prediction)
        
        # 限制预测记录数量
        if len(self.cost_predictions) > 100:
            self.cost_predictions = self.cost_predictions[-100:]
        
        logger.info(f"成本预测: 每日{avg_daily_cost:.2f}元, 每周{avg_daily_cost*7:.2f}元, 每月{avg_daily_cost*30:.2f}元")
        
        return prediction
    
    def get_daily_report(self, date: Optional[str] = None) -> Dict[str, Any]:
        """获取每日报告"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # 筛选当天的记录
        day_start = datetime.strptime(date, "%Y-%m-%d").timestamp()
        day_end = day_start + 24 * 3600
        
        day_records = [
            record for record in self.usage_records
            if day_start <= record.timestamp < day_end
        ]
        
        # 计算统计
        total_cost = sum(record.cost_rmb for record in day_records)
        total_tokens = sum(record.total_tokens for record in day_records)
        
        # 按操作类型分组
        by_operation: Dict[str, Dict[str, Any]] = {}
        for record in day_records:
            op = record.operation.value
            if op not in by_operation:
                by_operation[op] = {
                    "count": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "avg_tokens": 0.0,
                    "avg_cost": 0.0
                }
            
            by_operation[op]["count"] += 1
            by_operation[op]["total_tokens"] += record.total_tokens
            by_operation[op]["total_cost"] += record.cost_rmb
        
        # 计算平均值
        for op_data in by_operation.values():
            if op_data["count"] > 0:
                op_data["avg_tokens"] = op_data["total_tokens"] / op_data["count"]
                op_data["avg_cost"] = op_data["total_cost"] / op_data["count"]
        
        # 按模型分组
        by_model: Dict[str, Dict[str, Any]] = {}
        for record in day_records:
            model = record.model
            if model not in by_model:
                by_model[model] = {
                    "count": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0
                }
            
            by_model[model]["count"] += 1
            by_model[model]["total_tokens"] += record.total_tokens
            by_model[model]["total_cost"] += record.cost_rmb
        
        # 生成报告
        report = {
            "date": date,
            "summary": {
                "total_operations": len(day_records),
                "total_tokens": total_tokens,
                "total_cost_rmb": total_cost,
                "avg_cost_per_operation": total_cost / len(day_records) if day_records else 0,
                "avg_tokens_per_operation": total_tokens / len(day_records) if day_records else 0,
            },
            "by_operation": by_operation,
            "by_model": by_model,
            "downgrade_level": self.downgrade_level.value,
            "budget_usage": self._calculate_budget_usage(),
            "generated_at": datetime.now().isoformat()
        }
        
        return report
    
    def get_weekly_report(self) -> Dict[str, Any]:
        """获取每周报告"""
        today = datetime.now()
        
        # 获取最近7天的报告
        daily_reports = []
        weekly_cost = 0.0
        weekly_tokens = 0
        
        for i in range(7):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_report = self.get_daily_report(date)
            daily_reports.append(daily_report)
            
            weekly_cost += daily_report["summary"]["total_cost_rmb"]
            weekly_tokens += daily_report["summary"]["total_tokens"]
        
        # 生成趋势数据
        cost_trend = []
        token_trend = []
        
        for report in reversed(daily_reports):  # 从旧到新
            cost_trend.append(report["summary"]["total_cost_rmb"])
            token_trend.append(report["summary"]["total_tokens"])
        
        # 生成报告
        report = {
            "week_start": (today - timedelta(days=6)).strftime("%Y-%m-%d"),
            "week_end": today.strftime("%Y-%m-%d"),
            "summary": {
                "total_operations": sum(r["summary"]["total_operations"] for r in daily_reports),
                "total_tokens": weekly_tokens,
                "total_cost_rmb": weekly_cost,
                "avg_daily_cost": weekly_cost / 7,
                "avg_daily_tokens": weekly_tokens / 7,
            },
            "daily_reports": daily_reports,
            "trends": {
                "cost_trend": cost_trend,
                "token_trend": token_trend,
            },
            "predictions": self.predict_costs().to_dict() if self.cost_predictions else {},
            "downgrade_history": self.downgrade_reasons[-10:],  # 最近10次降级原因
            "generated_at": datetime.now().isoformat()
        }
        
        return report
    
    def get_recommendations(self) -> List[Dict[str, Any]]:
        """获取优化建议"""
        recommendations = []
        
        # 分析使用模式
        daily_report = self.get_daily_report()
        
        # 1. 检查高成本操作
        high_cost_ops = []
        for op, data in daily_report.get("by_operation", {}).items():
            if data["avg_cost"] > 0.1:  # 平均成本超过0.1元
                high_cost_ops.append({
                    "operation": op,
                    "avg_cost": data["avg_cost"],
                    "suggestion": f"考虑对{op}操作启用TurboQuant压缩"
                })
        
        if high_cost_ops:
            recommendations.extend(high_cost_ops)
        
        # 2.