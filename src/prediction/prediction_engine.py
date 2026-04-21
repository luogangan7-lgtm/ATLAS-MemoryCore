"""
ATLAS-MemoryCore 预测分析引擎
基于用户行为模式进行智能预测和主动服务
"""

import json
import time
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import pickle
import hashlib
from pathlib import Path

# 机器学习相关
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import pandas as pd

# 本地导入
from ..core.memory_manager import MemoryManager
from ..core.advanced_retrieval import AdvancedRetrieval

@dataclass
class PredictionResult:
    """预测结果数据结构"""
    prediction_type: str  # 预测类型：reminder, suggestion, answer, action
    confidence: float  # 置信度 0-1
    predicted_value: Any  # 预测值
    explanation: str  # 解释说明
    trigger_context: Dict[str, Any]  # 触发上下文
    timestamp: str  # 预测时间
    
@dataclass
class BehaviorPattern:
    """用户行为模式"""
    pattern_id: str
    pattern_type: str  # daily, weekly, context_based, sequence
    features: Dict[str, float]  # 特征向量
    frequency: int  # 出现频率
    last_observed: str  # 最后观察时间
    confidence: float  # 模式置信度
    metadata: Dict[str, Any]  # 元数据

class PredictionEngine:
    """预测分析引擎"""
    
    def __init__(self, memory_manager: MemoryManager, config_path: Optional[str] = None):
        """
        初始化预测引擎
        
        Args:
            memory_manager: 记忆管理器实例
            config_path: 配置文件路径
        """
        self.memory_manager = memory_manager
        self.retrieval = AdvancedRetrieval(memory_manager)
        
        # 配置
        self.config = {
            'prediction_enabled': True,
            'learning_rate': 0.1,
            'history_window_days': 30,
            'min_pattern_frequency': 3,
            'prediction_threshold': 0.7,
            'max_patterns': 100,
            'behavior_tracking': True,
            'real_time_learning': True
        }
        
        # 加载配置
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                self.config.update(user_config)
        
        # 数据存储
        self.patterns_file = Path.home() / '.atlas_prediction_patterns.pkl'
        self.behavior_log_file = Path.home() / '.atlas_behavior_log.jsonl'
        
        # 初始化数据结构
        self.behavior_patterns: Dict[str, BehaviorPattern] = {}
        self.prediction_models: Dict[str, Any] = {}
        self.behavior_history: deque = deque(maxlen=1000)
        self.feature_scaler = StandardScaler()
        
        # 加载已有模式
        self._load_patterns()
        
        # 初始化模型
        self._initialize_models()
        
    def _load_patterns(self):
        """加载已有的行为模式"""
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, 'rb') as f:
                    patterns_data = pickle.load(f)
                    for pattern_id, pattern_data in patterns_data.items():
                        self.behavior_patterns[pattern_id] = BehaviorPattern(**pattern_data)
                print(f"加载了 {len(self.behavior_patterns)} 个行为模式")
            except Exception as e:
                print(f"加载行为模式失败: {e}")
                self.behavior_patterns = {}
    
    def _save_patterns(self):
        """保存行为模式"""
        try:
            patterns_data = {
                pid: asdict(pattern) 
                for pid, pattern in self.behavior_patterns.items()
            }
            with open(self.patterns_file, 'wb') as f:
                pickle.dump(patterns_data, f)
        except Exception as e:
            print(f"保存行为模式失败: {e}")
    
    def _initialize_models(self):
        """初始化预测模型"""
        # 时间序列预测模型
        self.prediction_models['time_series'] = GradientBoostingRegressor(
            n_estimators=100, learning_rate=0.1, max_depth=5
        )
        
        # 分类预测模型
        self.prediction_models['classification'] = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42
        )
        
        # 聚类模型（行为模式发现）
        self.prediction_models['clustering'] = KMeans(n_clusters=10, random_state=42)
    
    def log_behavior(self, behavior_type: str, context: Dict[str, Any], 
                    metadata: Optional[Dict[str, Any]] = None):
        """
        记录用户行为
        
        Args:
            behavior_type: 行为类型
            context: 行为上下文
            metadata: 额外元数据
        """
        if not self.config['behavior_tracking']:
            return
            
        behavior_record = {
            'timestamp': datetime.now().isoformat(),
            'behavior_type': behavior_type,
            'context': context,
            'metadata': metadata or {}
        }
        
        # 添加到内存历史
        self.behavior_history.append(behavior_record)
        
        # 保存到文件
        try:
            with open(self.behavior_log_file, 'a') as f:
                f.write(json.dumps(behavior_record) + '\n')
        except Exception as e:
            print(f"保存行为记录失败: {e}")
        
        # 实时学习
        if self.config['real_time_learning']:
            self._analyze_behavior_pattern(behavior_record)
    
    def _analyze_behavior_pattern(self, behavior_record: Dict[str, Any]):
        """分析行为模式"""
        # 提取特征
        features = self._extract_features(behavior_record)
        
        # 查找相似模式
        similar_pattern = self._find_similar_pattern(features)
        
        if similar_pattern:
            # 更新现有模式
            self._update_pattern(similar_pattern, features, behavior_record)
        else:
            # 创建新模式
            self._create_new_pattern(features, behavior_record)
    
    def _extract_features(self, behavior_record: Dict[str, Any]) -> Dict[str, float]:
        """从行为记录中提取特征"""
        features = {}
        
        # 时间特征
        timestamp = datetime.fromisoformat(behavior_record['timestamp'])
        features['hour_of_day'] = timestamp.hour / 24.0
        features['day_of_week'] = timestamp.weekday() / 7.0
        features['day_of_month'] = timestamp.day / 31.0
        
        # 上下文特征
        context = behavior_record['context']
        features['context_length'] = len(str(context)) / 1000.0
        
        # 行为类型编码
        behavior_type = behavior_record['behavior_type']
        type_hash = int(hashlib.md5(behavior_type.encode()).hexdigest()[:8], 16)
        features['behavior_type_hash'] = (type_hash % 1000) / 1000.0
        
        # 记忆相关特征
        if 'query' in context:
            features['query_length'] = len(context['query']) / 100.0
        
        return features
    
    def _find_similar_pattern(self, features: Dict[str, float]) -> Optional[BehaviorPattern]:
        """查找相似的行为模式"""
        if not self.behavior_patterns:
            return None
            
        # 计算特征向量
        feature_vector = np.array(list(features.values()))
        
        best_pattern = None
        best_similarity = 0
        
        for pattern in self.behavior_patterns.values():
            pattern_vector = np.array(list(pattern.features.values()))
            
            # 计算余弦相似度
            similarity = np.dot(feature_vector, pattern_vector) / (
                np.linalg.norm(feature_vector) * np.linalg.norm(pattern_vector) + 1e-10
            )
            
            if similarity > best_similarity and similarity > 0.8:
                best_similarity = similarity
                best_pattern = pattern
        
        return best_pattern if best_similarity > 0.8 else None
    
    def _update_pattern(self, pattern: BehaviorPattern, features: Dict[str, float], 
                       behavior_record: Dict[str, Any]):
        """更新现有模式"""
        # 更新特征（加权平均）
        alpha = self.config['learning_rate']
        for key in features:
            if key in pattern.features:
                pattern.features[key] = (1 - alpha) * pattern.features[key] + alpha * features[key]
            else:
                pattern.features[key] = features[key]
        
        # 更新统计信息
        pattern.frequency += 1
        pattern.last_observed = behavior_record['timestamp']
        pattern.confidence = min(1.0, pattern.confidence + 0.05)
        
        # 保存更新
        self._save_patterns()
    
    def _create_new_pattern(self, features: Dict[str, float], 
                           behavior_record: Dict[str, Any]):
        """创建新模式"""
        pattern_id = f"pattern_{len(self.behavior_patterns)}_{int(time.time())}"
        
        pattern = BehaviorPattern(
            pattern_id=pattern_id,
            pattern_type='emerging',
            features=features,
            frequency=1,
            last_observed=behavior_record['timestamp'],
            confidence=0.5,
            metadata={
                'first_observed': behavior_record['timestamp'],
                'behavior_type': behavior_record['behavior_type'],
                'context_summary': str(behavior_record['context'])[:100]
            }
        )
        
        self.behavior_patterns[pattern_id] = pattern
        
        # 如果模式太多，删除低频模式
        if len(self.behavior_patterns) > self.config['max_patterns']:
            self._prune_patterns()
        
        self._save_patterns()
    
    def _prune_patterns(self):
        """修剪低频模式"""
        patterns_to_keep = sorted(
            self.behavior_patterns.values(),
            key=lambda p: (p.frequency, p.confidence),
            reverse=True
        )[:self.config['max_patterns']]
        
        self.behavior_patterns = {
            p.pattern_id: p for p in patterns_to_keep
        }
    
    def predict_next_action(self, current_context: Dict[str, Any]) -> List[PredictionResult]:
        """
        预测下一个可能的动作
        
        Args:
            current_context: 当前上下文
            
        Returns:
            预测结果列表
        """
        if not self.config['prediction_enabled']:
            return []
        
        predictions = []
        
        # 1. 基于时间模式的预测
        time_predictions = self._predict_based_on_time(current_context)
        predictions.extend(time_predictions)
        
        # 2. 基于上下文模式的预测
        context_predictions = self._predict_based_on_context(current_context)
        predictions.extend(context_predictions)
        
        # 3. 基于序列模式的预测
        sequence_predictions = self._predict_based_on_sequence(current_context)
        predictions.extend(sequence_predictions)
        
        # 过滤低置信度预测
        filtered_predictions = [
            p for p in predictions 
            if p.confidence >= self.config['prediction_threshold']
        ]
        
        # 按置信度排序
        filtered_predictions.sort(key=lambda x: x.confidence, reverse=True)
        
        return filtered_predictions[:5]  # 返回前5个预测
    
    def _predict_based_on_time(self, context: Dict[str, Any]) -> List[PredictionResult]:
        """基于时间模式预测"""
        predictions = []
        current_time = datetime.now()
        
        # 分析历史行为中的时间模式
        time_patterns = [
            p for p in self.behavior_patterns.values() 
            if p.pattern_type in ['daily', 'weekly']
        ]
        
        for pattern in time_patterns:
            # 提取时间特征
            pattern_hour = pattern.features.get('hour_of_day', 0) * 24
            pattern_day = pattern.features.get('day_of_week', 0) * 7
            
            current_hour = current_time.hour
            current_day = current_time.weekday()
            
            # 计算时间相似度
            hour_diff = abs(pattern_hour - current_hour)
            day_diff = abs(pattern_day - current_day)
            
            time_similarity = max(0, 1 - (hour_diff / 6 + day_diff / 3.5) / 2)
            
            if time_similarity > 0.7 and pattern.frequency >= self.config['min_pattern_frequency']:
                prediction = PredictionResult(
                    prediction_type='reminder',
                    confidence=pattern.confidence * time_similarity,
                    predicted_value=pattern.metadata.get('context_summary', '常规活动'),
                    explanation=f"基于您通常在此时进行的活动",
                    trigger_context=context,
                    timestamp=current_time.isoformat()
                )
                predictions.append(prediction)
        
        return predictions
    
    def _predict_based_on_context(self, context: Dict[str, Any]) -> List[PredictionResult]:
        """基于上下文模式预测"""
        predictions = []
        
        # 提取当前上下文特征
        current_features = self._extract_features({
            'timestamp': datetime.now().isoformat(),
            'behavior_type': 'prediction_query',
            'context': context
        })
        
        # 查找相似上下文模式
        for pattern in self.behavior_patterns.values():
            if pattern.pattern_type != 'context_based':
                continue
                
            # 计算特征相似度
            pattern_vector = np.array(list(pattern.features.values()))
            current_vector = np.array(list(current_features.values()))
            
            similarity = np.dot(pattern_vector, current_vector) / (
                np.linalg.norm(pattern_vector) * np.linalg.norm(current_vector) + 1e-10
            )
            
            if similarity > 0.8 and pattern.frequency >= 3:
                # 基于模式预测
                predicted_action = self._infer_action_from_pattern(pattern, context)
                
                if predicted_action:
                    prediction = PredictionResult(
                        prediction_type='suggestion',
                        confidence=pattern.confidence * similarity,
                        predicted_value=predicted_action,
                        explanation=f"基于您在此类上下文中的历史行为",
                        trigger_context=context,
                        timestamp=datetime.now().isoformat()
                    )
                    predictions.append(prediction)
        
        return predictions
    
    def _predict_based_on_sequence(self, context: Dict[str, Any]) -> List[PredictionResult]:
        """基于序列模式预测"""
        predictions = []
        
        if len(self.behavior_history) < 2:
            return predictions
        
        # 分析最近的行为序列
        recent_behaviors = list(self.behavior_history)[-5:]  # 最近5个行为
        
        # 查找序列模式
        for pattern in self.behavior_patterns.values():
            if pattern.pattern_type != 'sequence':
                continue
                
            # 检查序列匹配
            sequence_match = self._check_sequence_match(pattern, recent_behaviors)
            
            if sequence_match > 0.7:
                # 预测下一个可能的行为
                next_prediction = self._predict_next_in_sequence(pattern, recent_behaviors)
                
                if next_prediction:
                    prediction = PredictionResult(
                        prediction_type='action',
                        confidence=pattern.confidence * sequence_match,
                        predicted_value=next_prediction,
                        explanation=f"基于您当前的行为序列",
                        trigger_context=context,
                        timestamp=datetime.now().isoformat()
                    )
                    predictions.append(prediction)
        
        return predictions
    
    def _check_sequence_match(self, pattern: BehaviorPattern, 
                            recent_behaviors: List[Dict[str, Any]]) -> float:
        """检查序列匹配度"""
        # 简化实现：检查行为类型序列
        pattern_sequence = pattern.metadata.get('behavior_sequence', [])
        current_sequence = [b['behavior_type'] for b in recent_behaviors]
        
        if not pattern_sequence:
            return 0.0
        
        # 计算序列相似度
        match_count = 0
        for i, behavior_type in enumerate(current_sequence):
            if i < len(pattern_sequence) and behavior_type == pattern_sequence[i]:
                match_count += 1
        
        return match_count / max(len(pattern_sequence), len(current_sequence))
    
    def _predict_next_in_sequence(self, pattern: BehaviorPattern,
                                recent_behaviors: List[Dict[str, Any]]) -> Optional[str]:
        """预测序列中的下一个行为"""
        pattern_sequence = pattern.metadata.get('behavior_sequence', [])
        if not pattern_sequence:
            return None
        
        current_sequence = [b['behavior_type'] for b in recent_behaviors]
        
        # 查找当前序列在模式序列中的位置
        for i in range(len(pattern_sequence) - len(current_sequence) + 1):
            if pattern_sequence[i:i+len(current_sequence)] == current_sequence:
                if i + len(current_sequence) < len(pattern_sequence):
                    return pattern_sequence[i + len(current_sequence)]
        
        return None
    
    def _infer_action_from_pattern(self, pattern: BehaviorPattern, 
                                 context: Dict[str, Any]) -> Optional[str]:
        """从模式推断可能的动作"""
        # 基于模式元数据推断
        common_actions = pattern.metadata.get('common_actions', [])
        if common_actions:
            # 返回最常见的动作
            return max(set(common_actions), key=common_actions.count)
        
        # 基于行为类型推断
        behavior_type = pattern.metadata.get('behavior_type', '')
        if behavior_type:
            return f"继续{behavior_type}相关操作"
        
        return None
    
    def generate_proactive_help(self) -> List[Dict[str, Any]]:
        """
        生成主动帮助建议
        
        Returns:
            主动帮助建议列表
        """
        proactive_suggestions = []
        current_time = datetime