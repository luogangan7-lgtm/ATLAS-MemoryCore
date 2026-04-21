"""
ATLAS Memory Core - Zero-Token intelligent memory system for OpenClaw.
"""

__version__ = "0.1.0"
__author__ = "ATLAS (OpenClaw AI Assistant)"
__license__ = "MIT"

from .core.embedding import EmbeddingModel
from .core.storage import MemoryStorage
from .core.retrieval import MemoryRetrieval
from .core.scoring import MemoryScoringEngine
# from .integration.openclaw import AtlasMemorySkill  # TODO: 待实现

__all__ = [
    "EmbeddingModel",
    "MemoryStorage", 
    "MemoryRetrieval",
    "MemoryScoringEngine",
    # "AtlasMemorySkill",  # TODO: 待实现
]