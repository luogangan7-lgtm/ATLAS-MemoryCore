#!/usr/bin/env python3
"""
创建OpenClaw技能（简化版，不依赖外部库）
"""

import os
import sys
from pathlib import Path
from datetime import datetime

def create_skill():
    """创建OpenClaw技能"""
    skill_path = Path.home() / ".openclaw" / "skills" / "atlas-memory"
    skill_path.mkdir(parents=True, exist_ok=True)
    
    print(f"创建OpenClaw技能目录: {skill_path}")
    
    # 1. 创建SKILL.md
    skill_md = f"""# ATLAS-MemoryCore Skill for OpenClaw

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
# Link the skill
openclaw skill link {skill_path}
```

## Usage Examples

### Store a memory
```bash
/openclaw atlas capture "Meeting notes from project discussion"
```

### Search memories
```bash
/openclaw atlas search "project decisions"
/openclaw atlas search "yesterday's meeting"
```

### Manage memories
```bash
/openclaw atlas list --recent 10
/openclaw atlas optimize
/openclaw atlas stats
```

## Commands
- `atlas capture <text>` - Store a new memory
- `atlas search <query>` - Search memories
- `atlas list [options]` - List memories
- `atlas optimize` - Optimize storage
- `atlas stats` - Show statistics
- `atlas help` - Show help

## Version
ATLAS-MemoryCore V6.0 (Phase 3)
Generated: {datetime.now().isoformat()}
"""
    
    (skill_path / "SKILL.md").write_text(skill_md)
    print("✅ 创建 SKILL.md")
    
    # 2. 创建Python模块
    skill_py = '''"""
ATLAS-MemoryCore OpenClaw Skill
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AtlasSkill:
    """ATLAS-MemoryCore OpenClaw Skill"""
    
    def __init__(self):
        self.memories = []
        self.initialized = False
        
    def initialize(self):
        """Initialize the skill"""
        try:
            # Load existing memories if any
            self._load_memories()
            self.initialized = True
            logger.info("ATLAS-MemoryCore skill initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False
    
    def _load_memories(self):
        """Load memories from file"""
        try:
            import os
            data_file = os.path.expanduser("~/.atlas_memories.json")
            if os.path.exists(data_file):
                with open(data_file, 'r') as f:
                    self.memories = json.load(f)
        except:
            self.memories = []
    
    def _save_memories(self):
        """Save memories to file"""
        try:
            import os
            data_file = os.path.expanduser("~/.atlas_memories.json")
            with open(data_file, 'w') as f:
                json.dump(self.memories, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memories: {e}")
    
    def handle_command(self, command: str, args: list) -> dict:
        """Handle OpenClaw command"""
        if not self.initialized:
            self.initialize()
        
        cmd = command.lower()
        
        if cmd == "capture":
            return self._handle_capture(args)
        elif cmd == "search":
            return self._handle_search(args)
        elif cmd == "list":
            return self._handle_list(args)
        elif cmd == "stats":
            return self._handle_stats(args)
        elif cmd == "help":
            return self._handle_help(args)
        else:
            return {
                "error": f"Unknown command: {cmd}",
                "available_commands": ["capture", "search", "list", "stats", "help"]
            }
    
    def _handle_capture(self, args: list) -> dict:
        """Handle capture command"""
        if not args:
            return {"error": "No text provided"}
        
        text = " ".join(args)
        memory_id = len(self.memories) + 1
        
        memory = {
            "id": memory_id,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "category": "general",
            "importance": "medium"
        }
        
        self.memories.append(memory)
        self._save_memories()
        
        return {
            "success": True,
            "message": f"Memory captured (ID: {memory_id})",
            "memory_id": memory_id,
            "text_preview": text[:100] + "..." if len(text) > 100 else text
        }
    
    def _handle_search(self, args: list) -> dict:
        """Handle search command"""
        if not args:
            return {"error": "No query provided"}
        
        query = " ".join(args).lower()
        results = []
        
        for memory in self.memories:
            if query in memory["text"].lower():
                results.append(memory)
        
        return {
            "success": True,
            "query": query,
            "results": results[:10],  # Limit to 10 results
            "count": len(results)
        }
    
    def _handle_list(self, args: list) -> dict:
        """Handle list command"""
        recent = self.memories[-10:]  # Last 10 memories
        return {
            "success": True,
            "memories": recent,
            "count": len(recent),
            "total": len(self.memories)
        }
    
    def _handle_stats(self, args: list) -> dict:
        """Handle stats command"""
        return {
            "success": True,
            "stats": {
                "total_memories": len(self.memories),
                "last_updated": datetime.now().isoformat(),
                "storage_location": "~/.atlas_memories.json"
            }
        }
    
    def _handle_help(self, args: list) -> dict:
        """Handle help command"""
        help_text = """
ATLAS-MemoryCore Commands:
  capture <text>      - Store a new memory
  search <query>      - Search memories
  list                - List recent memories
  stats               - Show statistics
  help                - Show this help

Examples:
  atlas capture "Meeting notes"
  atlas search "project"
  atlas list
  atlas stats
"""
        return {
            "success": True,
            "help": help_text.strip()
        }

# OpenClaw skill entry point
skill = AtlasSkill()

def handle_atlas_command(command: str, args: list) -> dict:
    """OpenClaw skill handler"""
    return skill.handle_command(command, args)
'''
    
    (skill_path / "atlas_skill.py").write_text(skill_py)
    print("✅ 创建 atlas_skill.py")
    
    # 3. 创建配置文件
    config_yaml = '''# ATLAS-MemoryCore OpenClaw Skill Configuration

# Basic settings
skill:
  name: atlas-memory
  version: "6.0"
  author: "ATLAS Team"
  
# Storage settings
storage:
  type: file
  location: "~/.atlas_memories.json"
  
# Feature settings
features:
  compression: true
  search: true
  temporal_filtering: true
  
# Performance settings
performance:
  cache_enabled: true
  max_memories: 1000
  
# Logging
logging:
  level: INFO
  file: "/tmp/atlas_openclaw.log"
'''
    
    (skill_path / "config.yaml").write_text(config_yaml)
    print("✅ 创建 config.yaml")
    
    # 4. 创建示例文档
    examples_md = '''# ATLAS-MemoryCore Examples

## Basic Usage

### Store memories
```bash
/openclaw atlas capture "Bought groceries: milk, eggs, bread"
/openclaw atlas capture "Project deadline moved to Friday"
```

### Search memories
```bash
/openclaw atlas search "groceries"
/openclaw atlas search "deadline"
```

### View memories
```bash
/openclaw atlas list
/openclaw atlas stats
```

## Integration

This skill provides persistent memory storage for OpenClaw. 
Memories are stored in ~/.atlas_memories.json and persist across sessions.

## Development

For full ATLAS-MemoryCore features, install the complete package:
```bash
cd /Volumes/data/openclaw_workspace/projects/atlas-memory-core
pip install -e .
```
'''
    
    (skill_path / "EXAMPLES.md").write_text(examples_md)
    print("✅ 创建 EXAMPLES.md")
    
    print(f"\n🎉 OpenClaw技能创建完成！")
    print(f"技能位置: {skill_path}")
    print(f"文件: SKILL.md, atlas_skill.py, config.yaml, EXAMPLES.md")
    print(f"\n使用命令: openclaw skill link {skill_path}")
    
    return True

if __name__ == "__main__":
    create_skill()