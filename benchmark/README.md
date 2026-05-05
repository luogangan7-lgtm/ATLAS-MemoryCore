# Benchmark

## retrieval_comparison.py

对三种检索策略做端到端评估，使用**真实的 Qdrant + bge-m3 嵌入**，手工标注 10 条记忆和 6 个查询的 ground truth。

### 运行

```bash
# 前置：Qdrant 和 Ollama 都在运行
python3 benchmark/retrieval_comparison.py
```

### 三种策略对比

| 策略 | 描述 |
|------|------|
| **keyword** | 字符级分词交集，无向量，O(n) 遍历 |
| **vector** | 朴素 Qdrant cosine 搜索，单次向量查询 |
| **atlas** | 向量搜索 + importance × exp(-λ·age) 时间衰减重排 |

### 实测输出（Apple Silicon，Qdrant 本地，bge-m3）

```
策略           mean P@3   mean R@3   median ms
keyword           0.556      1.000        0.1
vector            0.500      0.917       31.9
atlas             0.389      0.750       31.5
```

**诚实解读：**

- **keyword** 在这个测试集上 R@3 最高——因为中文 bigram 对短文本有很强的匹配能力。但它对语义相似（同义词、近义词）无效，不能泛化。
- **atlas（时间衰减重排）比朴素向量搜索更差**——原因是测试集中有两条 age=0 的记忆（m08、m09），时间衰减公式大幅提升了它们的分数，把真正相关的旧记忆挤出 top-3。这说明衰减权重（λ）需要针对查询意图调节，"想要最新"和"想要最相关"是不同的需求。

> 10 条记忆的测试集太小，上述结论不具统计显著性。

### 已知局限

- 测试集由人工构造，不来自真实用户数据
- 6 个查询无法覆盖边缘情况
- 关键词策略使用字符 n-gram 交集（而非分词），在中文上偏弱
- "精度提升"完全取决于 ground truth 的质量

## benchmark_v6_vs_v6.2.py（已弃用）

原版基准全部使用 `time.sleep()` 模拟延迟和硬编码结果，**数字不反映真实系统性能**，仅保留作历史参考。
