"""
Aegis-Cortex V6.2 配置模块
支持TurboQuant压缩、四级过滤、Token经济等新功能
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CompressionAlgorithm(str, Enum):
    """压缩算法类型"""
    TURBOQUANT = "turboquant"  # Google Research 2026算法
    QUANTIZATION = "quantization"  # 传统量化
    PRUNING = "pruning"  # 剪枝
    DISTILLATION = "distillation"  # 知识蒸馏


class MemoryLayer(str, Enum):
    """记忆层级"""
    WORKING = "working"  # 工作记忆 (最近)
    SHORT_TERM = "short_term"  # 短期记忆 (1天内)
    MEDIUM_TERM = "medium_term"  # 中期记忆 (7天内)
    LONG_TERM = "long_term"  # 长期记忆 (全部)


@dataclass
class TurboQuantConfig:
    """TurboQuant压缩配置"""
    
    enabled: bool = True
    compression_ratio: float = 0.25  # 目标压缩率 (25%保留)
    quantization_bits: int = 4  # 量化位数
    group_size: int = 128  # 分组大小
    prune_threshold: float = 0.01  # 剪枝阈值
    
    # 性能参数
    use_gpu: bool = False
    batch_size: int = 32
    cache_enabled: bool = True
    
    # 质量参数
    preserve_attention_patterns: bool = True
    maintain_relative_magnitudes: bool = True


@dataclass
class FourStageFilterConfig:
    """四级过滤配置"""
    
    enabled: bool = True
    
    # 阶段1: 元数据预过滤
    metadata_filters: Dict[str, Any] = field(default_factory=dict)
    require_all_metadata: bool = False
    
    # 阶段2: 向量相似度过滤
    similarity_threshold: float = 0.82
    max_candidates_per_stage: int = 1000
    
    # 阶段3: 重要性分数过滤
    importance_threshold: float = 0.5
    min_importance_for_recall: Dict[MemoryLayer, float] = field(default_factory=lambda: {
        MemoryLayer.WORKING: 0.0,      # 工作记忆：全部召回
        MemoryLayer.SHORT_TERM: 0.3,   # 短期记忆：重要性>0.3
        MemoryLayer.MEDIUM_TERM: 0.5,  # 中期记忆：重要性>0.5
        MemoryLayer.LONG_TERM: 0.7     # 长期记忆：重要性>0.7
    })
    
    # 阶段4: 时间衰减调整
    use_ebbinghaus_decay: bool = True
    half_life_days: float = 1.0
    recency_weight: float = 0.25
    
    # 分层记忆参数
    working_memory_limit: int = 10
    short_term_days: int = 1
    medium_term_days: int = 7
    long_term_all: bool = True
    
    # 性能参数
    enable_caching: bool = True
    cache_ttl_seconds: int = 300


@dataclass
class TokenEconomyConfig:
    """Token经济配置"""
    
    enabled: bool = True
    
    # 监控参数
    enable_token_monitoring: bool = True
    token_cost_warning_threshold: float = 50.0  # 人民币警告阈值
    daily_token_budget: Optional[float] = None  # 每日Token预算
    
    # 压缩参数
    max_tokens_per_query: int = 1000
    target_compression_ratio: float = 0.25
    
    # 自动降级参数
    auto_downgrade_enabled: bool = True
    downgrade_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "critical": 0.9,   # 90%预算使用后降级
        "high": 0.75,      # 75%预算使用后降级
        "medium": 0.5,     # 50%预算使用后降级
    })
    
    # 报告参数
    daily_report_enabled: bool = True
    weekly_report_enabled: bool = True
    alert_channels: List[str] = field(default_factory=lambda: ["log", "email"])


@dataclass
class NocturnalOptimizationConfig:
    """夜间净化配置"""
    
    enabled: bool = True
    optimization_time: str = "03:00"  # 凌晨3点
    optimization_batch_size: int = 1000
    
    # 遗忘参数
    forget_threshold: float = 0.3
    forget_batch_size: int = 100
    
    # 升级参数
    upgrade_threshold: float = 0.85
    upgrade_batch_size: int = 50
    
    # 压缩参数
    compression_enabled: bool = True
    compression_batch_size: int = 200
    
    # 监控参数
    enable_progress_tracking: bool = True
    send_completion_notification: bool = True


@dataclass
class KnowledgeGraphConfig:
    """知识图谱配置"""
    
    enabled: bool = False  # 默认关闭，高级功能
    
    # 实体识别
    entity_recognition_enabled: bool = True
    entity_types: List[str] = field(default_factory=lambda: [
        "PERSON", "ORGANIZATION", "LOCATION", "DATE", 
        "MONEY", "PRODUCT", "EVENT", "SKILL"
    ])
    
    # 关系提取
    relation_extraction_enabled: bool = True
    relation_types: List[str] = field(default_factory=lambda: [
        "works_for", "located_in", "created_at", 
        "related_to", "part_of", "similar_to"
    ])
    
    # 图谱存储
    graph_database: str = "neo4j"  # 或 "networkx"
    graph_host: str = "localhost"
    graph_port: int = 7687
    
    # 性能参数
    batch_size: int = 100
    cache_enabled: bool = True


@dataclass
class AegisCortexConfig:
    """Aegis-Cortex V6.2 完整配置"""
    
    # 版本信息
    version: str = "6.2.0"
    architecture: str = "Aegis-Cortex V6.2"
    
    # 核心组件配置
    turboquant: TurboQuantConfig = field(default_factory=TurboQuantConfig)
    four_stage_filter: FourStageFilterConfig = field(default_factory=FourStageFilterConfig)
    token_economy: TokenEconomyConfig = field(default_factory=TokenEconomyConfig)
    nocturnal_optimization: NocturnalOptimizationConfig = field(default_factory=NocturnalOptimizationConfig)
    knowledge_graph: KnowledgeGraphConfig = field(default_factory=KnowledgeGraphConfig)
    
    # 系统参数
    debug_mode: bool = False
    log_level: str = "INFO"
    enable_metrics: bool = True
    metrics_port: int = 9091
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "version": self.version,
            "architecture": self.architecture,
            "turboquant": {
                "enabled": self.turboquant.enabled,
                "compression_ratio": self.turboquant.compression_ratio,
                "quantization_bits": self.turboquant.quantization_bits,
                "group_size": self.turboquant.group_size,
            },
            "four_stage_filter": {
                "enabled": self.four_stage_filter.enabled,
                "similarity_threshold": self.four_stage_filter.similarity_threshold,
                "importance_threshold": self.four_stage_filter.importance_threshold,
                "use_ebbinghaus_decay": self.four_stage_filter.use_ebbinghaus_decay,
            },
            "token_economy": {
                "enabled": self.token_economy.enabled,
                "max_tokens_per_query": self.token_economy.max_tokens_per_query,
                "auto_downgrade_enabled": self.token_economy.auto_downgrade_enabled,
            },
            "nocturnal_optimization": {
                "enabled": self.nocturnal_optimization.enabled,
                "optimization_time": self.nocturnal_optimization.optimization_time,
                "forget_threshold": self.nocturnal_optimization.forget_threshold,
                "upgrade_threshold": self.nocturnal_optimization.upgrade_threshold,
            },
            "knowledge_graph": {
                "enabled": self.knowledge_graph.enabled,
            },
            "system": {
                "debug_mode": self.debug_mode,
                "log_level": self.log_level,
                "enable_metrics": self.enable_metrics,
            }
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "AegisCortexConfig":
        """从字典创建配置"""
        config = cls()
        
        # 更新TurboQuant配置
        if "turboquant" in config_dict:
            turboquant_dict = config_dict["turboquant"]
            config.turboquant.enabled = turboquant_dict.get("enabled", config.turboquant.enabled)
            config.turboquant.compression_ratio = turboquant_dict.get("compression_ratio", config.turboquant.compression_ratio)
            config.turboquant.quantization_bits = turboquant_dict.get("quantization_bits", config.turboquant.quantization_bits)
            config.turboquant.group_size = turboquant_dict.get("group_size", config.turboquant.group_size)
        
        # 更新四级过滤配置
        if "four_stage_filter" in config_dict:
            filter_dict = config_dict["four_stage_filter"]
            config.four_stage_filter.enabled = filter_dict.get("enabled", config.four_stage_filter.enabled)
            config.four_stage_filter.similarity_threshold = filter_dict.get("similarity_threshold", config.four_stage_filter.similarity_threshold)
            config.four_stage_filter.importance_threshold = filter_dict.get("importance_threshold", config.four_stage_filter.importance_threshold)
            config.four_stage_filter.use_ebbinghaus_decay = filter_dict.get("use_ebbinghaus_decay", config.four_stage_filter.use_ebbinghaus_decay)
        
        # 更新Token经济配置
        if "token_economy" in config_dict:
            economy_dict = config_dict["token_economy"]
            config.token_economy.enabled = economy_dict.get("enabled", config.token_economy.enabled)
            config.token_economy.max_tokens_per_query = economy_dict.get("max_tokens_per_query", config.token_economy.max_tokens_per_query)
            config.token_economy.auto_downgrade_enabled = economy_dict.get("auto_downgrade_enabled", config.token_economy.auto_downgrade_enabled)
        
        # 更新夜间净化配置
        if "nocturnal_optimization" in config_dict:
            nocturnal_dict = config_dict["nocturnal_optimization"]
            config.nocturnal_optimization.enabled = nocturnal_dict.get("enabled", config.nocturnal_optimization.enabled)
            config.nocturnal_optimization.optimization_time = nocturnal_dict.get("optimization_time", config.nocturnal_optimization.optimization_time)
            config.nocturnal_optimization.forget_threshold = nocturnal_dict.get("forget_threshold", config.nocturnal_optimization.forget_threshold)
            config.nocturnal_optimization.upgrade_threshold = nocturnal_dict.get("upgrade_threshold", config.nocturnal_optimization.upgrade_threshold)
        
        # 更新系统参数
        if "system" in config_dict:
            system_dict = config_dict["system"]
            config.debug_mode = system_dict.get("debug_mode", config.debug_mode)
            config.log_level = system_dict.get("log_level", config.log_level)
            config.enable_metrics = system_dict.get("enable_metrics", config.enable_metrics)
        
        return config
    
    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        
        # 验证TurboQuant配置
        if self.turboquant.enabled:
            if not 0 < self.turboquant.compression_ratio <= 1:
                errors.append("TurboQuant压缩率必须在0到1之间")
            if not 1 <= self.turboquant.quantization_bits <= 16:
                errors.append("TurboQuant量化位数必须在1到16之间")
            if self.turboquant.group_size <= 0:
                errors.append("TurboQuant分组大小必须大于0")
        
        # 验证四级过滤配置
        if self.four_stage_filter.enabled:
            if not 0 <= self.four_stage_filter.similarity_threshold <= 1:
                errors.append("相似度阈值必须在0到1之间")
            if not 0 <= self.four_stage_filter.importance_threshold <= 1:
                errors.append("重要性阈值必须在0到1之间")
            if self.four_stage_filter.half_life_days <= 0:
                errors.append("半衰期必须大于0")
        
        # 验证Token经济配置
        if self.token_economy.enabled:
            if self.token_economy.max_tokens_per_query <= 0:
                errors.append("每查询最大Token数必须大于0")
            if self.token_economy.token_cost_warning_threshold < 0:
                errors.append("Token成本警告阈值不能为负数")
        
        # 验证夜间净化配置
        if self.nocturnal_optimization.enabled:
            try:
                from datetime import datetime
                datetime.strptime(self.nocturnal_optimization.optimization_time, "%H:%M")
            except ValueError:
                errors.append("优化时间格式必须为HH:MM")
            
            if not 0 <= self.nocturnal_optimization.forget_threshold <= 1:
                errors.append("遗忘阈值必须在0到1之间")
            if not 0 <= self.nocturnal_optimization.upgrade_threshold <= 1:
                errors.append("升级阈值必须在0到1之间")
        
        return errors


# 默认配置实例
DEFAULT_CONFIG = AegisCortexConfig()

def load_config(config_path: Optional[str] = None) -> AegisCortexConfig:
    """加载配置文件"""
    import json
    import yaml
    
    if config_path is None:
        logger.info("使用默认Aegis-Cortex配置")
        return DEFAULT_CONFIG
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.endswith('.json'):
                config_dict = json.load(f)
            elif config_path.endswith(('.yaml', '.yml')):
                config_dict = yaml.safe_load(f)
            else:
                logger.warning(f"不支持的配置文件格式: {config_path}")
                return DEFAULT_CONFIG
        
        config = AegisCortexConfig.from_dict(config_dict)
        
        # 验证配置
        errors = config.validate()
        if errors:
            logger.warning(f"配置验证警告: {errors}")
        
        logger.info(f"从 {config_path} 加载Aegis-Cortex配置成功")
        return config
    
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return DEFAULT_CONFIG