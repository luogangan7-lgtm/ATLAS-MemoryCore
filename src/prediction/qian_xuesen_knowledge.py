            r'([^。]*用于[^。]*)',
            r'([^。]*场景[^。]*)',
            r'([^。]*实例[^。]*)'
        ]
        
        for pattern in application_patterns:
            matches = re.findall(pattern, text)
            applications.extend(matches)
        
        return list(set(applications))[:5]  # 去重，最多返回5个
    
    def _find_concept_by_name(self, concept_name: str) -> Optional[QianXuesenConcept]:
        """通过名称查找概念"""
        for concept in self.concepts.values():
            if concept.concept_name == concept_name:
                return concept
        return None
    
    def _update_concept(self, concept: QianXuesenConcept, new_info: Dict[str, Any]):
        """更新概念"""
        # 更新描述（如果新描述更详细）
        if 'description' in new_info and len(new_info['description']) > len(concept.description):
            concept.description = new_info['description']
        
        # 添加新原则
        if 'principles' in new_info:
            for principle in new_info['principles']:
                if principle not in concept.key_principles:
                    concept.key_principles.append(principle)
        
        # 添加新应用
        if 'applications' in new_info:
            for application in new_info['applications']:
                if application not in concept.modern_ai_applications:
                    concept.modern_ai_applications.append(application)
        
        # 更新置信度
        concept.confidence_level = min(1.0, concept.confidence_level + 0.05)
        concept.last_updated = datetime.now().isoformat()
    
    def _create_concept_from_info(self, concept_name: str, concept_info: Dict[str, Any]) -> Optional[QianXuesenConcept]:
        """从信息创建概念"""
        concept_id = f"qx_{len(self.concepts)+1:03d}"
        
        # 确定类别
        category = self._determine_category(concept_name)
        
        concept = QianXuesenConcept(
            concept_id=concept_id,
            concept_name=concept_name,
            category=category,
            description=concept_info.get('description', f'{concept_name}的描述'),
            key_principles=concept_info.get('principles', []),
            modern_ai_applications=concept_info.get('applications', []),
            related_frameworks=self._suggest_frameworks(concept_name),
            confidence_level=concept_info.get('confidence', 0.7),
            last_updated=datetime.now().isoformat()
        )
        
        return concept
    
    def _determine_category(self, concept_name: str) -> str:
        """确定概念类别"""
        category_mapping = {
            '系统': '系统科学',
            '工程': '工程科学', 
            '智慧': '哲学与认知',
            '集成': '方法论',
            '研讨': '协作系统',
            '控制': '工程科学'
        }
        
        for keyword, category in category_mapping.items():
            if keyword in concept_name:
                return category
        
        return '其他'
    
    def _suggest_frameworks(self, concept_name: str) -> List[str]:
        """根据概念名称建议相关框架"""
        framework_mapping = {
            '系统': ['LangGraph', '多智能体系统', '复杂系统框架'],
            '集成': ['LangChain', 'Qwen-Agent', '综合集成框架'],
            '智慧': ['多模态LLM', '创造性AI', '知识融合系统'],
            '工程': ['MLOps', 'AI系统工程', '自动化管道'],
            '研讨': ['协作AI框架', '分布式学习', '群体智能系统']
        }
        
        for keyword, frameworks in framework_mapping.items():
            if keyword in concept_name:
                return frameworks
        
        return ['通用AI框架']
    
    def _extract_integration_patterns(self, text: str) -> List[Dict[str, Any]]:
        """从文本中提取集成模式"""
        patterns = []
        
        # 查找包含"集成"、"结合"、"应用"的段落
        integration_keywords = ['集成', '结合', '应用', '融合', '整合']
        
        sentences = re.split(r'[。！？]', text)
        for sentence in sentences:
            if any(keyword in sentence for keyword in integration_keywords):
                # 尝试提取集成模式信息
                pattern_info = self._parse_integration_sentence(sentence)
                if pattern_info:
                    patterns.append(pattern_info)
        
        return patterns
    
    def _parse_integration_sentence(self, sentence: str) -> Optional[Dict[str, Any]]:
        """解析集成句子"""
        # 简单的模式匹配
        pattern_templates = [
            r'将(.+?)与(.+?)相结合',
            r'(.+?)在(.+?)中的应用',
            r'基于(.+?)的(.+?)集成',
            r'(.+?)与(.+?)的融合'
        ]
        
        for template in pattern_templates:
            match = re.search(template, sentence)
            if match:
                # 假设第一个匹配是钱学森概念，第二个是AI框架
                qian_concept = match.group(1).strip()
                ai_framework = match.group(2).strip()
                
                pattern_info = {
                    'qian_concept': qian_concept,
                    'ai_framework': ai_framework,
                    'integration_method': sentence,
                    'use_cases': ['待补充'],
                    'implementation_guidelines': ['待补充'],
                    'success_metrics': {'待评估': 0.5}
                }
                return pattern_info
        
        return None
    
    def _create_pattern_from_info(self, pattern_info: Dict[str, Any]) -> Optional[IntegrationPattern]:
        """从信息创建集成模式"""
        pattern_id = f"ip_{len(self.integration_patterns)+1:03d}"
        pattern_name = f"{pattern_info['qian_concept']}与{pattern_info['ai_framework']}集成"
        
        pattern = IntegrationPattern(
            pattern_id=pattern_id,
            pattern_name=pattern_name,
            qian_concept=pattern_info['qian_concept'],
            ai_framework=pattern_info['ai_framework'],
            integration_method=pattern_info['integration_method'],
            use_cases=pattern_info['use_cases'],
            implementation_guidelines=pattern_info['implementation_guidelines'],
            success_metrics=pattern_info['success_metrics']
        )
        
        return pattern
    
    def get_concept_summary(self) -> Dict[str, Any]:
        """获取概念摘要"""
        summary = {
            'total_concepts': len(self.concepts),
            'concepts_by_category': {},
            'confidence_distribution': {
                'high': 0,
                'medium': 0,
                'low': 0
            },
            'recently_updated': []
        }
        
        # 按类别统计
        for concept in self.concepts.values():
            category = concept.category
            if category not in summary['concepts_by_category']:
                summary['concepts_by_category'][category] = 0
            summary['concepts_by_category'][category] += 1
            
            # 置信度分布
            if concept.confidence_level >= 0.8:
                summary['confidence_distribution']['high'] += 1
            elif concept.confidence_level >= 0.6:
                summary['confidence_distribution']['medium'] += 1
            else:
                summary['confidence_distribution']['low'] += 1
        
        # 最近更新的概念
        recent_concepts = sorted(
            self.concepts.values(),
            key=lambda c: c.last_updated,
            reverse=True
        )[:5]
        
        summary['recently_updated'] = [
            {
                'name': c.concept_name,
                'category': c.category,
                'last_updated': c.last_updated
            }
            for c in recent_concepts
        ]
        
        return summary
    
    def get_integration_recommendations(self, target_framework: str = None) -> List[Dict[str, Any]]:
        """
        获取集成推荐
        
        Args:
            target_framework: 目标AI框架
            
        Returns:
            集成推荐列表
        """
        recommendations = []
        
        for pattern in self.integration_patterns.values():
            if target_framework and target_framework not in pattern.ai_framework:
                continue
            
            recommendation = {
                'pattern_name': pattern.pattern_name,
                'qian_concept': pattern.qian_concept,
                'ai_framework': pattern.ai_framework,
                'integration_method': pattern.integration_method,
                'use_cases': pattern.use_cases[:3],  # 前3个用例
                'implementation_difficulty': self._assess_difficulty(pattern),
                'expected_benefits': list(pattern.success_metrics.keys())
            }
            recommendations.append(recommendation)
        
        # 按难度排序（从易到难）
        recommendations.sort(key=lambda x: x['implementation_difficulty'])
        
        return recommendations
    
    def _assess_difficulty(self, pattern: IntegrationPattern) -> str:
        """评估实施难度"""
        # 简单的难度评估逻辑
        framework_complexity = {
            'LangChain': '中等',
            'LangGraph': '中等',
            'AutoGPT': '高',
            'Qwen-Agent': '中等',
            '多智能体系统': '高',
            '多模态LLM': '高'
        }
        
        concept_complexity = {
            '开放的复杂巨系统': '高',
            '综合集成法': '中等',
            '大成智慧学': '高',
            '系统工程': '中等',
            '综合集成研讨厅': '高'
        }
        
        framework_diff = framework_complexity.get(pattern.ai_framework, '中等')
        concept_diff = concept_complexity.get(pattern.qian_concept, '中等')
        
        # 综合评估
        if framework_diff == '高' or concept_diff == '高':
            return '高'
        elif framework_diff == '中等' or concept_diff == '中等':
            return '中等'
        else:
            return '低'
    
    def search_concepts(self, query: str) -> List[Dict[str, Any]]:
        """
        搜索概念
        
        Args:
            query: 搜索查询
            
        Returns:
            匹配的概念列表
        """
        results = []
        
        for concept in self.concepts.values():
            relevance_score = self._calculate_relevance(concept, query)
            
            if relevance_score > 0.3:  # 相关性阈值
                result = {
                    'concept_name': concept.concept_name,
                    'category': concept.category,
                    'description': concept.description[:100] + '...' if len(concept.description) > 100 else concept.description,
                    'key_principles': concept.key_principles[:3],
                    'relevance_score': relevance_score,
                    'confidence': concept.confidence_level
                }
                results.append(result)
        
        # 按相关性排序
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return results
    
    def _calculate_relevance(self, concept: QianXuesenConcept, query: str) -> float:
        """计算相关性"""
        relevance = 0.0
        
        # 检查概念名称
        if query in concept.concept_name:
            relevance += 0.5
        
        # 检查描述
        if query in concept.description:
            relevance += 0.3
        
        # 检查原则
        for principle in concept.key_principles:
            if query in principle:
                relevance += 0.2
        
        # 检查应用
        for application in concept.modern_ai_applications:
            if query in application:
                relevance += 0.1
        
        return min(1.0, relevance)
    
    def export_knowledge(self, format: str = 'json') -> str:
        """
        导出知识
        
        Args:
            format: 导出格式
            
        Returns:
            导出的知识字符串
        """
        if format == 'json':
            export_data = {
                'concepts': {cid: asdict(c) for cid, c in self.concepts.items()},
                'integration_patterns': {pid: asdict(p) for pid, p in self.integration_patterns.items()},
                'learning_progress': self.learning_progress,
                'export_timestamp': datetime.now().isoformat(),
                'total_concepts': len(self.concepts),
                'total_patterns': len(self.integration_patterns)
            }
            return json.dumps(export_data, ensure_ascii=False, indent=2)
        
        elif format == 'markdown':
            md_lines = ["# 钱学森知识体系学习报告\n"]
            md_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            md_lines.append("## 学习进度\n")
            md_lines.append(f"- 已学习概念: {self.learning_progress['concepts_learned']}个")
            md_lines.append(f"- 集成模式: {self.learning_progress['integration_patterns_created']}个")
            md_lines.append(f"- 总学习时长: {self.learning_progress['total_learning_hours']}小时")
            md_lines.append(f"- 最后学习时间: {self.learning_progress['last_learning_session']}\n")
            
            md_lines.append("## 核心概念\n")
            for concept in self.concepts.values():
                md_lines.append(f"### {concept.concept_name}")
                md_lines.append(f"**类别**: {concept.category}")
                md_lines.append(f"**描述**: {concept.description}")
                md_lines.append("**核心原则**:")
                for principle in concept.key_principles[:3]:
                    md_lines.append(f"  - {principle}")
                md_lines.append("**现代AI应用**:")
                for app in concept.modern_ai_applications[:3]:
                    md_lines.append(f"  - {app}")
                md_lines.append(f"**置信度**: {concept.confidence_level:.2f}")
                md_lines.append(f"**最后更新**: {concept.last_updated}\n")
            
            md_lines.append("## 集成模式\n")
            for pattern in self.integration_patterns.values():
                md_lines.append(f"### {pattern.pattern_name}")
                md_lines.append(f"**钱学森概念**: {pattern.qian_concept}")
                md_lines.append(f"**AI框架**: {pattern.ai_framework}")
                md_lines.append(f"**集成方法**: {pattern.integration_method}")
                md_lines.append("**应用场景**:")
                for use_case in pattern.use_cases[:3]:
                    md_lines.append(f"  - {use_case}")
                md_lines.append("**成功指标**:")
                for metric, value in pattern.success_metrics.items():
                    md_lines.append(f"  - {metric}: {value:.2f}")
                md_lines.append("")
            
            return '\n'.join(md_lines)
        
        else:
            return f"不支持的格式: {format}"

# 使用示例
if __name__ == "__main__":
    # 创建知识库实例
    knowledge_base = QianXuesenKnowledgeBase()
    
    # 显示学习摘要
    summary = knowledge_base.get_concept_summary()
    print(f"已学习概念: {summary['total_concepts']}个")
    print(f"按类别分布: {summary['concepts_by_category']}")
    
    # 获取集成推荐
    recommendations = knowledge_base.get_integration_recommendations('LangChain')
    print(f"\nLangChain集成推荐 ({len(recommendations)}个):")
    for rec in recommendations[:3]:
        print(f"- {rec['pattern_name']} (难度: {rec['implementation_difficulty']})")
    
    # 导出知识
    export_md = knowledge_base.export_knowledge('markdown')
    print(f"\n知识导出完成，长度: {len(export_md)} 字符")