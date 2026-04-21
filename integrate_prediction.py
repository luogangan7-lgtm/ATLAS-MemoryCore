#!/usr/bin/env python3
"""
ATLAS-MemoryCore 预测模块快速集成脚本
快速将预测分析模块集成到主系统中
"""

import os
import sys
import shutil
import json
from pathlib import Path

print("=" * 60)
print("ATLAS-MemoryCore 预测模块快速集成")
print("=" * 60)

# 路径定义
project_root = Path("/Volumes/data/openclaw_workspace/projects/atlas-memory-core")
prediction_src = Path("/Users/luolimo/.openclaw/workspace/projects/atlas-memory-core/src/prediction")

print(f"项目根目录: {project_root}")
print(f"预测模块源: {prediction_src}")

# 步骤1: 复制预测模块文件
print("\n📁 步骤1: 复制预测模块文件...")

prediction_target = project_root / "src" / "prediction"
prediction_target.mkdir(exist_ok=True)

files_to_copy = [
    ("prediction_engine.py", "预测引擎"),
    ("__init__.py", "初始化文件")
]

for filename, description in files_to_copy:
    source_file = prediction_src / filename
    target_file = prediction_target / filename
    
    if source_file.exists():
        shutil.copy2(source_file, target_file)
        print(f"  ✅ 复制 {description}: {filename}")
    else:
        print(f"  ❌ 文件不存在: {source_file}")

# 步骤2: 创建集成层
print("\n🔗 步骤2: 创建集成层...")

integration_layer = prediction_target / "integration_layer.py"
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

integration_layer.write_text(integration_code, encoding='utf-8')
print(f"  ✅ 创建集成层: {integration_layer}")

# 步骤3: 更新主配置文件
print("\n⚙️  步骤3: 更新主配置文件...")

config_file = project_root / "config" / "prediction_config.yaml"
config_content = '''# 预测模块配置

prediction:
  # 预测引擎配置
  learning_rate: 0.1
  prediction_threshold: 0.7
  enable_behavior_prediction: true
  enable_trend_analysis: true
  
  # 性能配置
  max_predictions_per_day: 1000
  cache_predictions: true
  cache_ttl_seconds: 3600
  
  # 监控配置
  enable_monitoring: true
  log_predictions: true
  alert_on_anomalies: true
  
  # 集成配置
  integrate_with_memory: true
  memory_retrieval_limit: 50
  trend_analysis_window: "7d"
'''

config_file.parent.mkdir(exist_ok=True)
config_file.write_text(config_content, encoding='utf-8')
print(f"  ✅ 创建配置文件: {config_file}")

# 步骤4: 创建测试脚本
print("\n🧪 步骤4: 创建测试脚本...")

test_script = project_root / "tests" / "test_prediction_integration.py"
test_script.parent.mkdir(exist_ok=True)

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

test_script.write_text(test_code, encoding='utf-8')
print(f"  ✅ 创建测试脚本: {test_script}")

# 步骤5: 更新主系统集成点
print("\n🔌 步骤5: 更新主系统集成点...")

main_integration_file = project_root / "src" / "integration" / "prediction_integration.py"
main_integration_file.parent.mkdir(exist_ok=True)

main_integration_code = '''"""
主系统预测模块集成
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class PredictionModuleIntegration:
    """主系统预测模块集成"""
    
    def __init__(self, memory_manager, config: Optional[Dict[str, Any]] = None):
        self.memory_manager = memory_manager
        self.config = config or {}
        self.prediction_layer = None
        
        # 尝试导入预测模块
        self._initialize_prediction_module()
    
    def _initialize_prediction_module(self):
        """初始化预测模块"""
        try:
            from src.prediction.integration_layer import initialize_prediction_module
            
            self.prediction_layer = initialize_prediction_module(
                self.memory_manager,
                self.config
            )
            
            print("✅ 预测模块集成成功")
            
        except ImportError as e:
            print(f"⚠️ 预测模块导入失败: {e}")
            self.prediction_layer = None
        except Exception as e:
            print(f"❌ 预测模块初始化失败: {e}")
            self.prediction_layer = None
    
    def is_available(self) -> bool:
        """检查预测模块是否可用"""
        return self.prediction_layer is not None
    
    def enhance_memory_retrieval(self, query: str, base_results: list) -> list:
        """增强记忆检索"""
        if not self.is_available():
            return base_results
        
        try:
            # 使用预测分析优化检索结果
            enhanced_results = self._apply_prediction_enhancement(query, base_results)
            return enhanced_results
            
        except Exception as e:
            print(f"⚠️ 记忆检索增强失败: {e}")
            return base_results
    
    def _apply_prediction_enhancement(self, query: str, base_results: list) -> list:
        """应用预测增强"""
        # 这里可以添加基于预测的排序和过滤逻辑
        # 例如：根据用户行为预测调整相关性分数
        
        # 暂时返回原始结果
        return base_results
    
    def provide_insights(self, user_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """提供洞察"""
        if not self.is_available():
            return {"available": False, "insights": []}
        
        try:
            # 获取预测结果
            prediction_result = self.prediction_layer.predict_user_behavior(user_id, context)
            
            if "error" in prediction_result:
                return {"available": True, "insights": [], "error": prediction_result["error"]}
            
            # 提取洞察
            insights = []
            
            if "predictions" in prediction_result:
                for pred in prediction_result["predictions"][:3]:  # 最多3个预测
                    insights.append({
                        "type": "prediction",
                        "content": pred,
                        "confidence": prediction_result.get("confidence", 0.0)
                    })
            
            if "recommendations" in prediction_result:
                for rec in prediction_result["recommendations"][:3]:  # 最多3个推荐
                    insights.append({
                        "type": "recommendation",
                        "content": rec
                    })
            
            return {
                "available": True,
                "insights": insights,
                "explanation": prediction_result.get("explanation", "")
            }
            
        except Exception as e:
            return {"available": True, "insights": [], "error": str(e)}
    
    def analyze_system_trends(self) -> Dict[str, Any]:
        """分析系统趋势"""
        if not self.is_available():
            return {"available": False, "trends": []}
        
        try:
            # 获取趋势分析
            trend_result = self.prediction_layer.analyze_trends("7d")
            
            if "error" in trend_result:
                return {"available": True, "trends": [], "error": trend_result["error"]}
            
            return {
                "available": True,
                "trends": trend_result.get("trends", []),
                "patterns": trend_result.get("patterns", []),
                "anomalies": trend_result.get("anomalies", []),
                "insights": trend_result.get("insights", [])
            }
            
        except Exception as e:
            return {"available": True, "trends": [], "error": str(e)}
    
    def get_module_status(self) -> Dict[str, Any]:
        """获取模块状态"""
        status = {
            "module": "prediction",
            "available": self.is_available(),
            "initialized": self.prediction_layer is not None
        }
        
