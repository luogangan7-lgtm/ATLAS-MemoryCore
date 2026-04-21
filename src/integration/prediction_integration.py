#!/usr/bin/env python3
"""
ATLAS-MemoryCore 预测模块集成脚本
将预测分析模块集成到主系统中
"""

import os
import sys
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.memory_manager import MemoryManager
from src.core.advanced_retrieval import AdvancedRetrieval
from src.optimization.fusion_compressor import FusionCompressor

class PredictionIntegration:
    """预测模块集成器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化集成器"""
        self.project_root = project_root
        self.prediction_src = Path("/Users/luolimo/.openclaw/workspace/projects/atlas-memory-core/src/prediction")
        
        # 加载配置
        self.config = self._load_config(config_path)
        
        # 初始化核心组件
        self.memory_manager = None
        self.advanced_retrieval = None
        self.fusion_compressor = None
        
        # 预测模块组件
        self.prediction_engine = None
        
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置"""
        default_config = {
            "integration": {
                "copy_source_files": True,
                "update_imports": True,
                "create_integration_layer": True,
                "update_main_entry": True,
                "run_tests": True
            },
            "prediction": {
                "learning_rate": 0.1,
                "prediction_threshold": 0.7,
                "enable_behavior_prediction": True,
                "enable_trend_analysis": True
            }
        }
        
        if config_path and Path(config_path).exists():
            try:
                import yaml
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f)
                # 合并配置
                self._merge_configs(default_config, user_config)
            except Exception as e:
                print(f"⚠️ 配置文件加载失败，使用默认配置: {e}")
        
        return default_config
    
    def _merge_configs(self, base: Dict[str, Any], update: Dict[str, Any]):
        """递归合并配置"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_configs(base[key], value)
            else:
                base[key] = value
    
    def initialize_core_components(self):
        """初始化核心组件"""
        print("🔧 初始化核心组件...")
        
        try:
            # 初始化内存管理器
            self.memory_manager = MemoryManager()
            print("  ✅ 内存管理器初始化成功")
            
            # 初始化高级检索
            self.advanced_retrieval = AdvancedRetrieval(self.memory_manager)
            print("  ✅ 高级检索初始化成功")
            
            # 初始化融合压缩器
            self.fusion_compressor = FusionCompressor()
            print("  ✅ 融合压缩器初始化成功")
            
            return True
            
        except Exception as e:
            print(f"  ❌ 核心组件初始化失败: {e}")
            return False
    
    def copy_prediction_files(self):
        """复制预测模块文件"""
        if not self.config["integration"]["copy_source_files"]:
            print("⏭️  跳过文件复制")
            return True
        
        print("📁 复制预测模块文件...")
        
        # 目标目录
        prediction_target = self.project_root / "src" / "prediction"
        prediction_target.mkdir(exist_ok=True)
        
        files_to_copy = [
            ("prediction_engine.py", "预测引擎"),
            ("__init__.py", "初始化文件")
        ]
        
        success_count = 0
        for filename, description in files_to_copy:
            source_file = self.prediction_src / filename
            target_file = prediction_target / filename
            
            if source_file.exists():
                try:
                    shutil.copy2(source_file, target_file)
                    print(f"  ✅ 复制 {description}: {filename}")
                    success_count += 1
                except Exception as e:
                    print(f"  ❌ 复制失败 {filename}: {e}")
            else:
                print(f"  ⚠️  源文件不存在: {source_file}")
        
        return success_count == len(files_to_copy)
    
    def create_integration_layer(self):
        """创建集成层"""
        if not self.config["integration"]["create_integration_layer"]:
            print("⏭️  跳过集成层创建")
            return True
        
        print("🔗 创建集成层...")
        
        integration_code = '''"""
预测模块集成层
连接预测模块与ATLAS-MemoryCore主系统
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import json

# 添加主系统路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.prediction.prediction_engine import PredictionEngine
    PREDICTION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 预测模块导入失败: {e}")
    PREDICTION_AVAILABLE = False
    PredictionEngine = None

class PredictionIntegrationLayer:
    """预测集成层"""
    
    def __init__(self, memory_manager, config: Optional[Dict[str, Any]] = None):
        """初始化集成层"""
        self.memory_manager = memory_manager
        self.config = config or {}
        
        # 初始化预测组件
        self.prediction_engine = None
        
        if PREDICTION_AVAILABLE:
            self._initialize_prediction_components()
    
    def _initialize_prediction_components(self):
        """初始化预测组件"""
        try:
            # 初始化预测引擎
            prediction_config = self.config.get('prediction', {})
            self.prediction_engine = PredictionEngine(
                learning_rate=prediction_config.get('learning_rate', 0.1),
                prediction_threshold=prediction_config.get('prediction_threshold', 0.7)
            )
            
            print("✅ 预测引擎初始化成功")
            
        except Exception as e:
            print(f"❌ 预测组件初始化失败: {e}")
            self.prediction_engine = None
    
    def predict_user_behavior(self, user_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """预测用户行为"""
        if not self.prediction_engine:
            return {"error": "预测引擎未初始化"}
        
        try:
            # 获取用户历史记忆
            user_memories = self.memory_manager.get_user_memories(user_id, limit=50)
            
            # 准备预测数据
            prediction_data = {
                "user_id": user_id,
                "context": context,
                "recent_memories": user_memories,
                "timestamp": json.dumps({"iso": "2026-04-21T10:00:00Z"})
            }
            
            # 执行预测
            prediction_result = self.prediction_engine.predict(prediction_data)
            
            return {
                "success": True,
                "predictions": prediction_result.get("predictions", []),
                "confidence": prediction_result.get("confidence", 0.0),
                "recommendations": prediction_result.get("recommendations", []),
                "explanation": prediction_result.get("explanation", "")
            }
            
        except Exception as e:
            return {"error": f"预测失败: {e}"}
    
    def analyze_trends(self, time_range: str = "7d") -> Dict[str, Any]:
        """分析趋势"""
        if not self.prediction_engine:
            return {"error": "预测引擎未初始化"}
        
        try:
            # 获取系统范围内的记忆
            all_memories = self.memory_manager.get_recent_memories(limit=200)
            
            # 分析趋势
            trend_analysis = self.prediction_engine.analyze_trends(all_memories, time_range)
            
            return {
                "success": True,
                "trends": trend_analysis.get("trends", []),
                "patterns": trend_analysis.get("patterns", []),
                "anomalies": trend_analysis.get("anomalies", []),
                "insights": trend_analysis.get("insights", [])
            }
            
        except Exception as e:
            return {"error": f"趋势分析失败: {e}"}
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            "prediction_available": PREDICTION_AVAILABLE,
            "prediction_engine_initialized": self.prediction_engine is not None,
            "config": self.config.get('prediction', {})
        }
        
        if self.prediction_engine:
            status.update({
                "engine_status": "active",
                "learning_rate": self.prediction_engine.learning_rate,
                "prediction_threshold": self.prediction_engine.prediction_threshold
            })
        
        return status

# 全局集成层实例
_global_integration_layer = None

def get_global_integration_layer(memory_manager=None, config=None):
    """获取全局集成层实例"""
    global _global_integration_layer
    
    if _global_integration_layer is None and memory_manager is not None:
        _global_integration_layer = PredictionIntegrationLayer(memory_manager, config)
    
    return _global_integration_layer

def initialize_prediction_module(memory_manager, config=None):
    """初始化预测模块"""
    global _global_integration_layer
    
    if _global_integration_layer is None:
        _global_integration_layer = PredictionIntegrationLayer(memory_manager, config)
    
    return _global_integration_layer
'''
        
        integration_file = self.project_root / "src" / "prediction" / "integration_layer.py"
        integration_file.parent.mkdir(exist_ok=True)
        
        try:
            integration_file.write_text(integration_code, encoding='utf-8')
            print(f"  ✅ 集成层创建成功: {integration_file}")
            return True
        except Exception as e:
            print(f"  ❌ 集成层创建失败: {e}")
            return False
    
    def update_main_entry(self):
        """更新主系统入口"""
        if not self.config["integration"]["update_main_entry"]:
            print("⏭️  跳过主系统入口更新")
            return True
        
        print("🔌 更新主系统入口...")
        
        # 主系统入口文件路径
        main_entry = self.project_root / "src" / "main.py"
        
        if not main_entry.exists():
            print(f"  ⚠️  主系统入口文件不存在: {main_entry}")
            return False
        
        try:
            # 读取现有内容
            with open(main_entry, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否已包含预测模块
            if "prediction" in content.lower() and "PredictionIntegrationLayer" in content:
                print("  ✅ 预测模块已集成到主系统")
                return True
            
            # 查找合适的位置插入预测模块初始化
            # 这里简化处理，实际需要根据具体代码结构调整
            insert_point = content.find("def main():")
            if insert_point == -1:
                print("  ⚠️  未找到main函数，跳过更新")
                return False
            
            # 在main函数开始后插入预测模块初始化
            insert_code = '''
    # 初始化预测模块
    try:
        from src.prediction.integration_layer import initialize_prediction_module
        prediction_layer = initialize_prediction_module(memory_manager, config)
        print("✅ 预测模块初始化成功")
    except ImportError as e:
        print(f"⚠️ 预测模块导入失败: {e}")
        prediction_layer = None
    except Exception as e:
        print(f"❌ 预测模块初始化失败: {e}")
        prediction_layer = None
'''
            
            # 找到main函数体开始的位置
            main_start = content.find("def main():")
            indent_start = content.find("\n", main_start) + 1
            
            # 确定缩进级别
            indent_level = 0
            for i in range(indent_start, len(content)):
                if content[i] != ' ':
                    break
                indent_level += 1
            
            indent = ' ' * indent_level
            
            # 插入代码
            insert_position = indent_start + indent_level
            new_content = content[:insert_position] + insert_code + content[insert_position:]
            
            # 写入更新后的内容
            with open(main_entry, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"  ✅ 主系统入口更新成功: {main_entry}")
            return True
            
        except Exception as e:
            print(f"  ❌ 主系统入口更新失败: {e}")
            return False
    
    def run_integration_tests(self):
        """运行集成测试"""
        if not self.config["integration"]["run_tests"]:
            print("⏭️  跳过集成测试")
            return True
        
        print("🧪 运行集成测试...")
        
        test_code = '''#!/usr/bin/env python3
"""
预测模块集成测试
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("预测模块集成测试")
print("=" * 60)

# 模拟内存管理器
class MockMemoryManager:
    def __init__(self):
        self.memories = []
    
    def get_user_memories(self, user_id, limit=50):
        return [
            {"content": f"用户{user_id}的记忆{i}", "importance": 0.5 + i*0.1}
            for i in range(min(limit, 10))
        ]
    
    def get_recent_memories(self, limit=200):
        return [
            {"content": f"系统记忆{i}", "importance": 0.6, "timestamp": f"2026-04-{20+i:02d}"}
            for i in range(min(limit, 20))
        ]

def test_prediction_availability():
    """测试预测模块可用性"""
    print("\\n1. 测试预测模块可用性...")
    
    try:
        from src.prediction.integration_layer import PREDICTION_AVAILABLE
        print(f"  预测模块可用: {PREDICTION_AVAILABLE}")
        return PREDICTION_AVAILABLE
    except ImportError as e:
        print(f"  导入失败: {e}")
        return False

def test_integration_layer():
    """测试集成层"""
    print("\\n2. 测试集成层...")
    
    try:
        from src.prediction.integration_layer import PredictionIntegrationLayer
        
        # 创建模拟内存管理器
        mock_memory = MockMemoryManager()
        
        # 创建集成层实例
        config = {
            "prediction": {
                "learning_rate": 0.1,
                "prediction_threshold": 0.7
            }
        }
        
        integration_layer = PredictionIntegrationLayer(mock_memory, config)
        
        # 测试系统状态
        status = integration_layer.get_system_status()
        print(f"  系统状态: {status}")
        
        return integration_layer
        
    except Exception as e:
        print(f"  集成层测试失败: {e}")
        return None

def test_behavior_prediction(integration_layer):
    """测试行为预测"""
    print("\\n3. 测试行为预测...")
    
    if not integration_layer or not integration_layer.prediction_engine:
        print("  预测引擎不可用，跳过测试")
        return
    
    try:
        context = {
            "time_of_day": "morning",
            "user_activity": "working",
            "recent_interactions": ["email", "calendar"]
        }
        
        result = integration_layer.predict_user_behavior("test_user_001", context)
        print(f"  预测结果: {result}")
        
        if "error" not in result:
            print("  ✅ 行为预测测试通过")
        else:
            print(f"  ❌ 行为预测失败: {result['error']}")
            
    except Exception as e:
        print(f"  ❌ 行为预测异常: {e}")

def test_trend_analysis(integration_layer):
    """测试趋势分析"""
    print("\\n4. 测试趋势分析...")
    
    if not integration_layer or not integration_layer.prediction_engine:
        print("  预测引擎不可用，跳过测试")
        return
    
    try:
        result = integration_layer.analyze_trends("7d")
        print(f"  趋势分析结果: {result}")
        
        if "error" not in result:
            print("  ✅ 趋势分析测试通过")
        else:
            print(f"  ❌ 趋势分析失败: {result['error']}")
            
    except Exception as e:
        print(f"  ❌ 趋势分析异常: {e}")

def main():
    """主测试函数"""
    # 测试预测模块可用性
    available = test_prediction_availability()
    
    if not available:
        print("\\n❌ 预测模块不可用，测试终止")
        return False
    
    # 测试集成层
    integration_layer = test_integration_layer()
    
    if not integration_layer:
        print("\\n❌ 集成层初始化失败")
        return False
    
    # 测试功能
    test_behavior_prediction(integration_layer)
    test_trend_analysis(integration_layer)
    
    print("\\n" + "=" * 60)
    print("✅ 预测模块集成测试完成")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
        
        test_file = self.project_root / "tests