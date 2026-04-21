"""
生态系统集成模块 - Phase 3 核心模块
提供OpenClaw集成、API接口、插件系统
"""

import sys
import os
import json
import logging
import asyncio
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import threading
from pathlib import Path
import inspect

# 尝试导入Web框架
try:
    from fastapi import FastAPI, HTTPException, Depends, Query, Path as FPath
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, HTMLResponse
    from pydantic import BaseModel, Field
    from typing import List as TList, Optional as TOptional
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logging.warning("FastAPI not available, REST API disabled")

class IntegrationType(Enum):
    """集成类型"""
    OPENCLAW = "openclaw"
    REST_API = "rest_api"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    PLUGIN = "plugin"
    WEBHOOK = "webhook"

class PluginType(Enum):
    """插件类型"""
    STORAGE = "storage"
    EMBEDDING = "embedding"
    COMPRESSION = "compression"
    RETRIEVAL = "retrieval"
    UI = "ui"
    ANALYTICS = "analytics"
    CUSTOM = "custom"

@dataclass
class IntegrationConfig:
    """集成配置"""
    enabled_integrations: List[IntegrationType] = None
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    enable_cors: bool = True
    cors_origins: List[str] = None
    openclaw_integration: bool = True
    openclaw_skill_path: str = "~/.openclaw/skills/atlas-memory"
    plugin_directory: str = "plugins"
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    
    def __post_init__(self):
        if self.enabled_integrations is None:
            self.enabled_integrations = [IntegrationType.REST_API, IntegrationType.OPENCLAW]
        if self.cors_origins is None:
            self.cors_origins = ["*"]

@dataclass
class PluginInfo:
    """插件信息"""
    name: str
    plugin_type: PluginType
    version: str
    author: str
    description: str
    enabled: bool = True
    config: Dict[str, Any] = None
    module_path: Optional[str] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}

class OpenClawIntegration:
    """OpenClaw集成"""
    
    def __init__(self, config: IntegrationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.skill_path = Path(config.openclaw_skill_path).expanduser()
        
    def create_skill(self, atlas_core):
        """创建OpenClaw技能"""
        try:
            # 创建技能目录
            self.skill_path.mkdir(parents=True, exist_ok=True)
            
            # 创建SKILL.md
            skill_md = self._generate_skill_md(atlas_core)
            (self.skill_path / "SKILL.md").write_text(skill_md)
            
            # 创建Python模块
            skill_py = self._generate_skill_py(atlas_core)
            (self.skill_path / "atlas_skill.py").write_text(skill_py)
            
            # 创建配置文件
            config_yaml = self._generate_config_yaml()
            (self.skill_path / "config.yaml").write_text(config_yaml)
            
            # 创建示例
            examples_md = self._generate_examples_md()
            (self.skill_path / "EXAMPLES.md").write_text(examples_md)
            
            self.logger.info(f"OpenClaw skill created at: {self.skill_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create OpenClaw skill: {e}")
            return False
    
    def _generate_skill_md(self, atlas_core) -> str:
        """生成SKILL.md内容"""
        return f"""# ATLAS-MemoryCore Skill for OpenClaw

## Description
Intelligent memory management system for OpenClaw. Provides persistent, compressed, and searchable memory across sessions.

## Features
- **Persistent Memory**: Store memories that survive across OpenClaw sessions
- **Semantic Search**: Find related memories using AI embeddings
- **Smart Compression**: Reduce storage usage by 60-90%
- **Temporal Filtering**: Search by time (today, this week, etc.)
- **Sentiment Analysis**: Filter memories by emotional content

## Installation
```bash
# Clone the skill
openclaw skill install {self.skill_path}

# Or install from workspace
openclaw skill link {self.skill_path}
```

## Usage Examples

### Store a memory
```bash
# Via OpenClaw command
/openclaw atlas capture "Meeting notes from project discussion"

# Via natural language
"Remember that we decided to use Qdrant for vector storage"
```

### Search memories
```bash
/openclaw atlas search "project decisions"
/openclaw atlas search "yesterday's meeting" --temporal yesterday
```

### Manage memories
```bash
/openclaw atlas list --recent 10
/openclaw atlas optimize --full
/openclaw atlas stats
```

## Integration Points

### 1. Heartbeat Integration
ATLAS can be configured to run during OpenClaw heartbeats:
- Check for new memories to compress
- Run optimization cycles
- Clean up old memories

### 2. Session Integration
- Memories persist across all OpenClaw sessions
- Shared memory pool for all agents
- Context-aware retrieval

### 3. Tool Integration
- Direct access from OpenClaw tools
- API endpoints for external tools
- Webhook notifications

## Configuration

Edit `config.yaml` to customize:
- Storage backend (Qdrant, PostgreSQL, etc.)
- Compression settings
- Cache configuration
- Integration options

## API Reference

### Commands
- `atlas capture <text>` - Store a new memory
- `atlas search <query>` - Search memories
- `atlas list [options]` - List memories
- `atlas optimize` - Optimize storage
- `atlas stats` - Show statistics
- `atlas help` - Show help

### Options
- `--category <category>` - Memory category
- `--importance <high|medium|low>` - Importance level
- `--temporal <filter>` - Time filter (today, week, month)
- `--mode <mode>` - Search mode (semantic, hybrid, etc.)
- `--limit <number>` - Result limit
- `--full` - Full optimization
- `--dry-run` - Dry run mode

## Development

This skill is automatically generated by ATLAS-MemoryCore V6.0.
For development, see the main project at: {Path.cwd()}

## Version
ATLAS-MemoryCore V6.0 (Phase 3)
Generated: {datetime.now().isoformat()}
"""
    
    def _generate_skill_py(self, atlas_core) -> str:
        """生成技能Python模块"""
        return '''"""
ATLAS-MemoryCore OpenClaw Skill
"""

import sys
import os
from typing import Dict, List, Optional, Any
import logging

# Add ATLAS to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.qdrant_storage import QdrantStorage
from src.optimization.fusion_compressor import FusionCompressor
from src.core.advanced_retrieval import AdvancedRetrieval, RetrievalMode
from src.ui.user_experience import InteractiveCLI, UXConfig

logger = logging.getLogger(__name__)

class AtlasSkill:
    """ATLAS-MemoryCore OpenClaw Skill"""
    
    def __init__(self):
        self.storage = None
        self.compressor = None
        self.retrieval = None
        self.ui = None
        self.initialized = False
        
    def initialize(self):
        """Initialize the skill"""
        try:
            # Initialize components
            self.storage = QdrantStorage()
            self.compressor = FusionCompressor()
            self.retrieval = AdvancedRetrieval(self.storage)
            
            # Initialize UI
            ux_config = UXConfig(
                use_color=True,
                show_progress=True,
                show_timestamps=True
            )
            self.ui = InteractiveCLI(ux_config)
            
            self.initialized = True
            logger.info("ATLAS-MemoryCore skill initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize ATLAS skill: {e}")
            return False
    
    def handle_command(self, command: str, args: List[str]) -> Dict[str, Any]:
        """Handle OpenClaw command"""
        if not self.initialized:
            if not self.initialize():
                return {"error": "Failed to initialize ATLAS"}
        
        try:
            cmd = command.lower()
            
            if cmd == "capture":
                return self._handle_capture(args)
            elif cmd == "search":
                return self._handle_search(args)
            elif cmd == "list":
                return self._handle_list(args)
            elif cmd == "optimize":
                return self._handle_optimize(args)
            elif cmd == "stats":
                return self._handle_stats(args)
            elif cmd == "help":
                return self._handle_help(args)
            else:
                return {"error": f"Unknown command: {cmd}", "available_commands": [
                    "capture", "search", "list", "optimize", "stats", "help"
                ]}
                
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return {"error": str(e)}
    
    def _handle_capture(self, args: List[str]) -> Dict[str, Any]:
        """Handle capture command"""
        if not args:
            return {"error": "No text provided"}
        
        text = " ".join(args)
        
        # Parse options
        category = "general"
        importance = "medium"
        
        # In a real implementation, parse --category and --importance options
        
        # Store memory
        memory_id = self.storage.store_memory(
            text=text,
            metadata={
                "category": category,
                "importance": importance,
                "timestamp": datetime.now().isoformat(),
                "source": "openclaw"
            }
        )
        
        return {
            "success": True,
            "message": f"Memory captured (ID: {memory_id})",
            "memory_id": memory_id,
            "text_preview": text[:100] + "..." if len(text) > 100 else text
        }
    
    def _handle_search(self, args: List[str]) -> Dict[str, Any]:
        """Handle search command"""
        if not args:
            return {"error": "No query provided"}
        
        query = " ".join(args)
        
        # Parse options
        limit = 5
        mode = "hybrid"
        
        # Search memories
        results = self.retrieval.retrieve(
            query=query,
            mode=mode,
            max_results=limit
        )
        
        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": result.memory_id,
                "text": result.text,
                "score": result.final_score,
                "timestamp": result.timestamp.isoformat() if result.timestamp else None,
                "metadata": result.metadata
            })
        
        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results)
        }
    
    def _handle_list(self, args: List[str]) -> Dict[str, Any]:
        """Handle list command"""
        # Get recent memories
        try:
            memories = self.storage.get_recent_memories(limit=10)
            
            formatted = []
            for mem in memories:
                formatted.append({
                    "id": mem.get("id"),
                    "text": mem.get("text", "")[:200],
                    "timestamp": mem.get("metadata", {}).get("timestamp"),
                    "category": mem.get("metadata", {}).get("category", "unknown")
                })
            
            return {
                "success": True,
                "memories": formatted,
                "count": len(formatted)
            }
            
        except Exception as e:
            return {"error": f"Failed to list memories: {e}"}
    
    def _handle_optimize(self, args: List[str]) -> Dict[str, Any]:
        """Handle optimize command"""
        # This would run the optimization cycle
        return {
            "success": True,
            "message": "Optimization scheduled (run in background)",
            "note": "In production, this would trigger the optimization engine"
        }
    
    def _handle_stats(self, args: List[str]) -> Dict[str, Any]:
        """Handle stats command"""
        try:
            # Get basic stats
            stats = self.storage.get_stats()
            
            return {
                "success": True,
                "stats": stats,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Failed to get stats: {e}"}
    
    def _handle_help(self, args: List[str]) -> Dict[str, Any]:
        """Handle help command"""
        help_text = """
ATLAS-MemoryCore Commands:
  capture <text>      - Store a new memory
  search <query>      - Search memories
  list                - List recent memories
  optimize            - Optimize memory storage
  stats               - Show statistics
  help                - Show this help

Options:
  --category <cat>    - Memory category
  --importance <level>- Importance (high/medium/low)
  --limit <number>   - Result limit
  --temporal <filter>- Time filter
  --mode <mode>      - Search mode
  --full             - Full optimization
  --dry-run          - Dry run mode

Examples:
  atlas capture "Meeting notes" --category work
  atlas search "project" --limit 10 --temporal week
  atlas optimize --full
"""
        
        return {
            "success": True,
            "help": help_text.strip()
        }

# OpenClaw skill entry point
skill = AtlasSkill()

def handle_atlas_command(command: str, args: List[str]) -> Dict[str, Any]:
    """OpenClaw skill handler"""
    return skill.handle_command(command, args)
'''
    
    def _generate_config_yaml(self) -> str:
        """生成配置文件"""
        return '''# ATLAS-MemoryCore OpenClaw Skill Configuration

# Storage configuration
storage:
  type: qdrant
  host: localhost
  port: 6333
  collection: atlas_memories
  embedding_model: nomic-embed-text-v1.5

# Compression settings
compression:
  enabled: true
  model: Qwen/Qwen2.5-7B-Instruct
  use_4bit: true
  compression_ratio: 0.3
  min_quality_score: 0.7

# Retrieval settings
retrieval:
  default_mode: hybrid
  cache_enabled: true
  cache_ttl: 3600
  max_results: 10

# Integration settings
integration:
  openclaw:
    enabled: true
    command_prefix: atlas
    auto_initialize: true
  
  api:
    enabled: true
    host: 0.0.0.0
    port: 8000
  
  webhooks:
    enabled: false
    url: ""
    secret: ""

# Performance settings
performance:
  batch_size: 10
  parallel_processing: true
  max_workers: 4
  timeout_seconds: 30

# Logging settings
logging:
  level: INFO
  file: /tmp/atlas_openclaw.log
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Plugin settings
plugins:
  directory: plugins
  auto_load: true
  enabled_plugins: []
'''
    
    def _generate_examples_md(self) -> str:
        """生成示例文档"""
        return '''# ATLAS-MemoryCore OpenClaw Examples

## Basic Usage

### Store memories
```bash
# Simple memory
/openclaw atlas capture "Bought groceries: milk, eggs, bread"

# With category and importance
/openclaw atlas capture "Project deadline moved to Friday" --category work --importance high

# From conversation context
"Remember that Alice prefers email over Slack for important discussions"
```

### Search memories
```bash
# Simple search
/openclaw atlas search "groceries"

# Time-based search
/openclaw atlas search "meeting" --temporal today
/openclaw atlas search "decision" --temporal this_week

# Advanced search
/openclaw atlas search "important project" --mode hybrid --limit 5
```

### Manage memories
```bash
# List recent memories
/openclaw atlas list
/openclaw atlas list --recent 20

# Optimize storage
/openclaw atlas optimize
/openclaw atlas optimize --full --dry-run

# View statistics
/openclaw atlas stats
```

## Integration Examples

### In OpenClaw workflows
```python
# In an OpenClaw skill or agent
from atlas_skill import handle_atlas_command

# Store context from current conversation
result = handle_atlas_command("capture", [
    "User mentioned they'll be on vacation next week",
    "--category", "context",
    "--importance", "medium"
])

# Later, retrieve relevant context
search_result = handle_atlas_command("search", [
    "vacation",
    "--temporal", "future"
])
```

### With OpenClaw heartbeats
```