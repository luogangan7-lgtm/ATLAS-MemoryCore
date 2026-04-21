"""
配置管理模块 - Configuration Management Module
支持动态配置和模型替换
Supports dynamic configuration and model replacement
"""

import os
import yaml
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EmbeddingProvider(str, Enum):
    """嵌入模型提供者 - Embedding Model Providers"""

    NOMIC = "nomic"  # nomic-ai/nomic-embed-text-v1.5
    SENTENCE_TRANSFORMERS = "sentence-transformers"  # 通用Sentence Transformers
    OPENAI = "openai"  # OpenAI API (需要Token)
    CUSTOM = "custom"  # 自定义模型


class LocalModelType(str, Enum):
    """本地模型类型 - Local Model Types"""

    QWEN2_5_7B = "qwen2.5-7b"  # Qwen2.5 7B模型
    LLAMA3_8B = "llama3-8b"  # Llama3 8B模型
    CUSTOM = "custom"  # 自定义本地模型


@dataclass
class EmbeddingConfig:
    """嵌入模型配置 - Embedding Model Configuration"""

    provider: EmbeddingProvider = EmbeddingProvider.NOMIC
    model_name: str = "nomic-ai/nomic-embed-text-v1.5"
    device: str = "cpu"  # cpu or cuda
    cache_dir: Optional[str] = None
    normalize: bool = True
    batch_size: int = 32
    api_key: Optional[str] = None  # 用于OpenAI等需要API key的模型

    # 自定义模型配置
    custom_model_path: Optional[str] = None
    custom_dimension: Optional[int] = None


@dataclass
class LocalModelConfig:
    """本地模型配置 - Local Model Configuration"""

    enabled: bool = False
    model_type: LocalModelType = LocalModelType.QWEN2_5_7B
    model_path: Optional[str] = None
    device: str = "cpu"
    quantized: bool = True  # 是否使用量化版本
    max_tokens: int = 2048
    temperature: float = 0.1

    # 自定义模型配置
    custom_model_config: Optional[Dict[str, Any]] = None


@dataclass
class StorageConfig:
    """存储配置 - Storage Configuration"""

    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "atlas_memories"
    vector_size: int = 768  # nomic-embed-text维度
    max_memories: int = 10000  # 最大记忆数量

    # 持久化配置
    persist_dir: str = "~/.atlas-memory"
    backup_enabled: bool = True
    backup_interval_hours: int = 24


@dataclass
class RetrievalConfig:
    """检索配置 - Retrieval Configuration"""

    similarity_threshold: float = 0.82  # 相似度阈值
    max_results: int = 10  # 最大返回结果数
    use_metadata_filter: bool = True  # 是否使用元数据过滤
    use_hybrid_search: bool = True  # 是否使用混合搜索

    # 缓存配置
    cache_enabled: bool = True
    cache_size: int = 1000
    cache_ttl_seconds: int = 3600  # 缓存过期时间


@dataclass
class OptimizationConfig:
    """优化配置 - Optimization Configuration"""

    auto_optimize: bool = True
    optimization_time: str = "03:00"  # 每天优化时间 (HH:MM)
    optimization_interval_hours: int = 24

    # 评分配置
    importance_decay_days: int = 30  # 重要性衰减天数
    min_score_to_keep: float = 0.3  # 保留的最低分数
    max_score_to_promote: float = 0.85  # 升级到QMD的分数

    # 清理配置
    auto_cleanup: bool = True
    cleanup_age_days: int = 7  # 清理超过7天的低分记忆


@dataclass
class SystemConfig:
    """系统配置 - System Configuration"""

    log_level: str = "INFO"
    log_file: Optional[str] = None
    debug_mode: bool = False

    # 性能配置
    max_workers: int = 4  # 最大工作线程数
    timeout_seconds: int = 30  # 操作超时时间

    # 监控配置
    enable_monitoring: bool = True
    metrics_port: int = 9090  # 监控指标端口


@dataclass
class AtlasMemoryConfig:
    """ATLAS记忆系统完整配置 - Complete ATLAS Memory System Configuration"""

    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    local_model: LocalModelConfig = field(default_factory=LocalModelConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    system: SystemConfig = field(default_factory=SystemConfig)

    # 版本信息
    version: str = "0.1.0"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典 - Convert to dictionary"""
        return {
            "embedding": asdict(self.embedding),
            "local_model": asdict(self.local_model),
            "storage": asdict(self.storage),
            "retrieval": asdict(self.retrieval),
            "optimization": asdict(self.optimization),
            "system": asdict(self.system),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasMemoryConfig":
        """从字典创建 - Create from dictionary"""
        config = cls()

        # 更新嵌入配置
        if "embedding" in data:
            embedding_data = data["embedding"]
            if "provider" in embedding_data:
                embedding_data["provider"] = EmbeddingProvider(
                    embedding_data["provider"]
                )
            config.embedding = EmbeddingConfig(**embedding_data)

        # 更新本地模型配置
        if "local_model" in data:
            local_model_data = data["local_model"]
            if "model_type" in local_model_data:
                local_model_data["model_type"] = LocalModelType(
                    local_model_data["model_type"]
                )
            config.local_model = LocalModelConfig(**local_model_data)

        # 更新其他配置
        if "storage" in data:
            config.storage = StorageConfig(**data["storage"])
        if "retrieval" in data:
            config.retrieval = RetrievalConfig(**data["retrieval"])
        if "optimization" in data:
            config.optimization = OptimizationConfig(**data["optimization"])
        if "system" in data:
            config.system = SystemConfig(**data["system"])

        if "version" in data:
            config.version = data["version"]

        return config


class ConfigManager:
    """配置管理器 - Configuration Manager"""

    DEFAULT_CONFIG_PATHS = [
        "~/.atlas-memory/config.yaml",
        "~/.atlas-memory/config.json",
        "./config/config.yaml",
        "./config.json",
    ]

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config = AtlasMemoryConfig()
        self._load_config()

    def _load_config(self):
        """加载配置 - Load configuration"""
        # 如果指定了配置文件路径
        if self.config_path:
            if os.path.exists(self.config_path):
                self._load_from_file(self.config_path)
                return

        # 尝试从默认路径加载
        for path in self.DEFAULT_CONFIG_PATHS:
            expanded_path = os.path.expanduser(path)
            if os.path.exists(expanded_path):
                self._load_from_file(expanded_path)
                self.config_path = expanded_path
                logger.info(f"从默认路径加载配置: {expanded_path}")
                return

        # 使用默认配置
        logger.info("未找到配置文件，使用默认配置")

    def _load_from_file(self, filepath: str):
        """从文件加载配置 - Load configuration from file"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.endswith(".yaml") or filepath.endswith(".yml"):
                    data = yaml.safe_load(f)
                elif filepath.endswith(".json"):
                    data = json.load(f)
                else:
                    raise ValueError(f"不支持的配置文件格式: {filepath}")

            self.config = AtlasMemoryConfig.from_dict(data)
            logger.info(f"配置文件加载成功: {filepath}")

        except Exception as e:
            logger.error(f"加载配置文件失败 {filepath}: {e}")
            raise

    def save_config(self, filepath: Optional[str] = None):
        """保存配置到文件 - Save configuration to file"""
        save_path = filepath or self.config_path
        if not save_path:
            save_path = os.path.expanduser("~/.atlas-memory/config.yaml")

        # 确保目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        try:
            config_dict = self.config.to_dict()

            if save_path.endswith(".yaml") or save_path.endswith(".yml"):
                with open(save_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        config_dict, f, default_flow_style=False, allow_unicode=True
                    )
            elif save_path.endswith(".json"):
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(config_dict, f, ensure_ascii=False, indent=2)
            else:
                # 默认使用YAML
                save_path = save_path + ".yaml" if "." not in save_path else save_path
                with open(save_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        config_dict, f, default_flow_style=False, allow_unicode=True
                    )

            logger.info(f"配置保存成功: {save_path}")
            return save_path

        except Exception as e:
            logger.error(f"保存配置文件失败 {save_path}: {e}")
            raise

    def update_config(self, updates: Dict[str, Any]):
        """更新配置 - Update configuration"""

        # 递归更新配置
        def _update_dict(target: Dict, source: Dict):
            for key, value in source.items():
                if (
                    key in target
                    and isinstance(target[key], dict)
                    and isinstance(value, dict)
                ):
                    _update_dict(target[key], value)
                else:
                    target[key] = value

        config_dict = self.config.to_dict()
        _update_dict(config_dict, updates)
        self.config = AtlasMemoryConfig.from_dict(config_dict)

    def get_embedding_dimension(self) -> int:
        """获取嵌入维度 - Get embedding dimension"""
        if self.config.embedding.custom_dimension:
            return self.config.embedding.custom_dimension

        # 默认维度
        if self.config.embedding.provider == EmbeddingProvider.NOMIC:
            return 768  # nomic-embed-text-v1.5维度
        elif self.config.embedding.provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
            return 384  # 通用模型默认维度
        elif self.config.embedding.provider == EmbeddingProvider.OPENAI:
            return 1536  # OpenAI text-embedding-3-small
        else:
            return 768  # 默认维度

    def create_default_config_file(self) -> str:
        """创建默认配置文件 - Create default configuration file"""
        default_config = AtlasMemoryConfig()

        # 设置合理的默认值
        default_config.storage.persist_dir = os.path.expanduser("~/.atlas-memory")

        # 保存到默认位置
        config_dir = os.path.expanduser("~/.atlas-memory")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "config.yaml")

        self.config = default_config
        self.save_config(config_path)

        return config_path


# 全局配置管理器实例 - Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """获取配置管理器实例 - Get configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager


def get_config() -> AtlasMemoryConfig:
    """获取当前配置 - Get current configuration"""
    return get_config_manager().config
