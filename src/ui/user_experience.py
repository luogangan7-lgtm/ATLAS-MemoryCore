"""
用户体验改进模块 - Phase 3 核心模块
提供友好的CLI界面、进度指示、错误处理和帮助系统
"""

import sys
import os
import time
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import threading
from pathlib import Path

# 尝试导入富文本显示库
try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.syntax import Syntax
    from rich.prompt import Prompt, Confirm
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    logging.warning("Rich not available, using basic console output")

class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class OutputFormat(Enum):
    """输出格式"""
    TEXT = "text"
    JSON = "json"
    TABLE = "table"
    MARKDOWN = "markdown"
    YAML = "yaml"

@dataclass
class UXConfig:
    """用户体验配置"""
    use_color: bool = True
    show_progress: bool = True
    show_timestamps: bool = True
    log_level: LogLevel = LogLevel.INFO
    output_format: OutputFormat = OutputFormat.TEXT
    max_line_width: int = 80
    indent_size: int = 2
    animation_speed: float = 0.1  # 动画速度（秒）
    
    # 交互设置
    confirm_destructive: bool = True
    ask_before_exit: bool = False
    save_history: bool = True
    history_file: str = "~/.atlas_history"
    
    # 显示设置
    show_banner: bool = True
    show_help_hints: bool = True
    truncate_long_output: bool = True
    max_truncate_length: int = 500

class ProgressIndicator:
    """进度指示器"""
    
    def __init__(self, config: UXConfig):
        self.config = config
        self.console = Console() if RICH_AVAILABLE else None
        self.current_task = None
        self.task_start_time = None
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_index = 0
        
    def start_task(self, description: str, total: Optional[int] = None):
        """开始任务"""
        self.current_task = description
        self.task_start_time = time.time()
        
        if self.console and self.config.show_progress and RICH_AVAILABLE:
            if total:
                # 有总进度的任务
                self.progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeElapsedColumn(),
                    console=self.console
                )
                self.task_id = self.progress.add_task(description, total=total)
                self.progress.start()
            else:
                # 无总进度的任务（spinner）
                self.console.print(f"[cyan]{self._get_spinner()}[/cyan] {description}", end="")
        elif self.config.show_progress:
            # 基本控制台输出
            print(f"⏳ {description}...", end="", flush=True)
    
    def update_progress(self, completed: int = 1):
        """更新进度"""
        if self.console and hasattr(self, 'progress') and RICH_AVAILABLE:
            self.progress.update(self.task_id, advance=completed)
        elif self.config.show_progress and not RICH_AVAILABLE:
            # 基本进度显示
            print(".", end="", flush=True)
    
    def end_task(self, success: bool = True, message: Optional[str] = None):
        """结束任务"""
        elapsed = time.time() - self.task_start_time if self.task_start_time else 0
        
        if self.console and self.config.show_progress and RICH_AVAILABLE:
            if hasattr(self, 'progress'):
                self.progress.stop()
            
            status = "✅" if success else "❌"
            msg = message or self.current_task
            self.console.print(f"{status} {msg} ({elapsed:.2f}s)")
        
        elif self.config.show_progress:
            status = "✓" if success else "✗"
            msg = message or self.current_task
            print(f"\n{status} {msg} ({elapsed:.2f}s)")
        
        self.current_task = None
        self.task_start_time = None
    
    def _get_spinner(self) -> str:
        """获取spinner字符"""
        char = self.spinner_chars[self.spinner_index]
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
        return char

class ErrorHandler:
    """错误处理器"""
    
    def __init__(self, config: UXConfig):
        self.config = config
        self.console = Console() if RICH_AVAILABLE else None
        self.error_count = 0
        self.warning_count = 0
        
    def handle_error(self, error: Exception, context: str = "", show_traceback: bool = False):
        """处理错误"""
        self.error_count += 1
        
        error_msg = str(error)
        error_type = type(error).__name__
        
        if self.console and RICH_AVAILABLE:
            # 使用rich显示错误
            error_panel = Panel(
                f"[bold red]{error_type}:[/bold red] {error_msg}\n\n"
                f"[dim]Context: {context}[/dim]",
                title="Error",
                border_style="red"
            )
            self.console.print(error_panel)
            
            if show_traceback:
                self.console.print_exception()
        
        else:
            # 基本错误显示
            print(f"\n❌ ERROR: {error_type}")
            print(f"   Message: {error_msg}")
            if context:
                print(f"   Context: {context}")
            
            if show_traceback:
                import traceback
                traceback.print_exc()
        
        # 记录到日志
        logging.error(f"{context}: {error_type} - {error_msg}")
    
    def handle_warning(self, warning: str, context: str = ""):
        """处理警告"""
        self.warning_count += 1
        
        if self.console and RICH_AVAILABLE:
            warning_panel = Panel(
                f"[bold yellow]Warning:[/bold yellow] {warning}\n\n"
                f"[dim]Context: {context}[/dim]",
                title="Warning",
                border_style="yellow"
            )
            self.console.print(warning_panel)
        
        else:
            print(f"\n⚠️  WARNING: {warning}")
            if context:
                print(f"   Context: {context}")
        
        logging.warning(f"{context}: {warning}")
    
    def get_stats(self) -> Dict[str, int]:
        """获取错误统计"""
        return {
            'errors': self.error_count,
            'warnings': self.warning_count
        }
    
    def reset_stats(self):
        """重置统计"""
        self.error_count = 0
        self.warning_count = 0

class HelpSystem:
    """帮助系统"""
    
    def __init__(self, config: UXConfig):
        self.config = config
        self.console = Console() if RICH_AVAILABLE else None
        self.commands = {}
        
    def register_command(self, name: str, description: str, usage: str, examples: List[str] = None):
        """注册命令"""
        self.commands[name] = {
            'description': description,
            'usage': usage,
            'examples': examples or []
        }
    
    def show_help(self, command: Optional[str] = None):
        """显示帮助"""
        if command:
            self._show_command_help(command)
        else:
            self._show_general_help()
    
    def _show_general_help(self):
        """显示通用帮助"""
        if self.console and RICH_AVAILABLE:
            # 使用rich显示帮助
            table = Table(title="ATLAS-MemoryCore Commands", show_header=True, header_style="bold magenta")
            table.add_column("Command", style="cyan")
            table.add_column("Description", style="green")
            table.add_column("Usage", style="yellow")
            
            for cmd, info in sorted(self.commands.items()):
                table.add_row(cmd, info['description'], info['usage'])
            
            self.console.print(table)
            
            # 显示示例
            self.console.print("\n[bold]Examples:[/bold]")
            for cmd, info in self.commands.items():
                if info['examples']:
                    for example in info['examples'][:2]:  # 每个命令最多显示2个示例
                        self.console.print(f"  [cyan]$ atlas {cmd} {example}[/cyan]")
        
        else:
            # 基本帮助显示
            print("\nATLAS-MemoryCore Commands:")
            print("=" * 60)
            
            for cmd, info in sorted(self.commands.items()):
                print(f"\n{cmd}:")
                print(f"  Description: {info['description']}")
                print(f"  Usage: {info['usage']}")
                
                if info['examples']:
                    print(f"  Examples:")
                    for example in info['examples'][:2]:
                        print(f"    $ atlas {cmd} {example}")
            
            print("\n" + "=" * 60)
    
    def _show_command_help(self, command: str):
        """显示特定命令的帮助"""
        if command not in self.commands:
            print(f"Command '{command}' not found.")
            return
        
        info = self.commands[command]
        
        if self.console and RICH_AVAILABLE:
            # 使用rich显示命令帮助
            help_panel = Panel(
                f"[bold]Description:[/bold] {info['description']}\n\n"
                f"[bold]Usage:[/bold] {info['usage']}\n\n"
                f"[bold]Examples:[/bold]\n" + "\n".join([
                    f"  [cyan]$ atlas {command} {example}[/cyan]"
                    for example in info['examples']
                ]),
                title=f"Help: {command}",
                border_style="blue"
            )
            self.console.print(help_panel)
        
        else:
            # 基本命令帮助显示
            print(f"\nHelp for command: {command}")
            print("=" * 60)
            print(f"\nDescription: {info['description']}")
            print(f"\nUsage: {info['usage']}")
            
            if info['examples']:
                print(f"\nExamples:")
                for example in info['examples']:
                    print(f"  $ atlas {command} {example}")
            
            print("\n" + "=" * 60)
    
    def show_quick_start(self):
        """显示快速开始指南"""
        quick_start = """
# ATLAS-MemoryCore Quick Start

## 1. Installation
```bash
pip install -e .
```

## 2. Basic Usage

### Store a memory
```bash
atlas capture "Meeting notes from today's project discussion"
```

### Search memories
```bash
atlas search "project meeting"
```

### Optimize memories
```bash
atlas optimize --full
```

## 3. Advanced Features

### Use compression
```bash
atlas compress --ratio 0.3
```

### Advanced search
```bash
atlas search "important" --mode hybrid --temporal this_week
```

### Monitor performance
```bash
atlas stats --detailed
```

## 4. Getting Help
```bash
atlas help
atlas help <command>
```
"""
        
        if self.console and RICH_AVAILABLE:
            self.console.print(Markdown(quick_start))
        else:
            print(quick_start)

class InteractiveCLI:
    """交互式CLI"""
    
    def __init__(self, config: UXConfig):
        self.config = config
        self.console = Console() if RICH_AVAILABLE else None
        self.progress = ProgressIndicator(config)
        self.error_handler = ErrorHandler(config)
        self.help_system = HelpSystem(config)
        self.running = False
        self.command_history = []
        
        # 注册默认命令
        self._register_default_commands()
    
    def _register_default_commands(self):
        """注册默认命令"""
        self.help_system.register_command(
            "capture",
            "Capture a new memory",
            "atlas capture <text> [--category <category>] [--importance <high|medium|low>]",
            ["'Meeting notes' --category work --importance high", "'Personal thought' --category personal"]
        )
        
        self.help_system.register_command(
            "search",
            "Search memories",
            "atlas search <query> [--limit <number>] [--mode <semantic|temporal|hybrid>]",
            ["'project meeting' --limit 5", "'important' --mode hybrid --temporal this_week"]
        )
        
        self.help_system.register_command(
            "optimize",
            "Optimize memory storage",
            "atlas optimize [--full] [--dry-run]",
            ["--full", "--dry-run"]
        )
        
        self.help_system.register_command(
            "stats",
            "Show system statistics",
            "atlas stats [--detailed]",
            ["", "--detailed"]
        )
        
        self.help_system.register_command(
            "help",
            "Show help information",
            "atlas help [command]",
            ["", "search", "capture"]
        )
    
    def start(self):
        """启动交互式CLI"""
        self.running = True
        
        if self.config.show_banner:
            self._show_banner()
        
        self.help_system.show_quick_start()
        
        while self.running:
            try:
                # 获取用户输入
                if self.console and RICH_AVAILABLE:
                    user_input = Prompt.ask("\n[bold cyan]atlas[/bold cyan]")
                else:
                    user_input = input("\natlas> ").strip()
                
                if not user_input:
                    continue
                
                # 添加到历史
                self.command_history.append(user_input)
                
                # 处理命令
                self._process_command(user_input)
                
            except KeyboardInterrupt:
                print("\n\nInterrupted. Use 'exit' or 'quit' to exit.")
            except EOFError:
                self.exit()
            except Exception as e:
                self.error_handler.handle_error(e, "CLI command processing")
    
    def _show_banner(self):
        """显示横幅"""
        banner = """
╔══════════════════════════════════════════════════════════╗
║                 ATLAS-MemoryCore V6.0                    ║
║         Intelligent Memory Management System             ║
║                  Phase 3: UX Enhanced                    ║
╚══════════════════════════════════════════════════════════╝
"""
        if self.console and RICH_AVAILABLE:
            self.console.print(Panel(banner, border_style="cyan"))
        else:
            print(banner)
    
    def _process_command(self, command: str):
        """处理命令"""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        # 内置命令
        if cmd in ['exit', 'quit']:
            self.exit()
        elif cmd == 'help':
            self.help_system.show_help(args[0] if args else None)
        elif cmd == 'history':
            self._show_history()
        elif cmd == 'clear':
            os.system('clear' if os.name == 'posix' else 'cls')
        elif cmd == 'version':
            self._show_version()
        else:
            # 外部命令处理
            self._execute_external_command(cmd, args)
    
    def _execute_external_command(self, command: str, args: List[str]):
        """执行外部命令"""
        # 这里应该调用实际的命令处理逻辑
        # 现在只是模拟
        
        self.progress.start_task(f"Executing: {command} {' '.join(args)}")
        time.sleep(0.5)  # 模拟处理时间
        
        # 模拟不同的命令结果
        if command == "capture":
            self.progress.end_task(True, f"Memory captured: {' '.join(args)}")
        elif command == "search":
            self.progress.end_task(True, f"Found 5 results for: {' '.join(args)}")
        elif command == "optimize":
            self.progress.end_task(True, "Memory optimization completed")
        elif command == "stats":
            self._show_stats()
        else:
            self.progress.end_task(False, f"Unknown command: {command}")
            self.help_system.show_help()
    
    def _show_history(self):
        """显示命令历史"""
        if not self.command_history:
            print("No command history.")
            return
        
        if self.console and RICH_AVAILABLE:
            table = Table(title="Command History", show_header=True)
            table.add_column("#", style="dim")
            table.add_column("Command", style="cyan")
            
            for i, cmd in enumerate(self.command_history[-10:], 1):  # 显示最近10条
                table.add_row(str(i), cmd)
            
            self.console.print(table)
        else:
            print("\nCommand History:")
            for i, cmd in enumerate(self.command_history[-10:], 1):
                print(f"  {i:2d}. {cmd}")
    
    def _show_version(self):
        """显示版本信息"""
        version_info = """
ATLAS