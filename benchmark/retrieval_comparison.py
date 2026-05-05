#!/usr/bin/env python3
"""
语义记忆检索对比基准

比较三种检索策略在真实 Qdrant 实例上的表现：
  1. 关键词匹配（baseline：无向量，纯文本 grep）
  2. 朴素向量搜索（vanilla Qdrant cosine search）
  3. 时间衰减重排（向量搜索 + freshness × importance 重排）

要求：
  - Qdrant 运行在 localhost:6333
  - Ollama + bge-m3 运行在 localhost:11434
  - pip install qdrant-client requests numpy

运行：
  python3 benchmark/retrieval_comparison.py

结果写入 benchmark/results_<timestamp>.json
"""

import json
import time
import math
import statistics
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import Optional
import uuid

# ── 配置 ──────────────────────────────────────────────────────────────────────
QDRANT_URL   = "http://localhost:6333"
OLLAMA_URL   = "http://localhost:11434"
EMBED_MODEL  = "bge-m3"
VECTOR_DIM   = 1024
COLLECTION   = "bench_atlas_retrieval"

# ── 测试数据集（手工标注，确保 ground truth 可信）──────────────────────────────
# 每条记忆有明确的主题标签，查询→期望召回的记忆 ID 已知
MEMORIES = [
    # id (int), short_id (str), topic, content, age_days, importance
    (1, "m01", "情感", "主动建立关系的核心是创造对方对你的预期，而非等待对方主动。预期式求爱的底层逻辑：让对方始终有下一步期待。", 1, 0.9),
    (2, "m02", "情感", "关系缔造论：关系的本质是资源置换，双方提供对方需要的价值才能维持连接。没有价值的关系会自然消亡。", 3, 0.85),
    (3, "m03", "情感", "Play连招：通过游戏化互动拉近距离，核心是让对方进入你的框架而非追随对方的框架。", 7, 0.8),
    (4, "m04", "情感", "故事沟通术：用故事代替道理，用情感代替逻辑。隧道视觉让人只愿看到自己认可的故事。", 2, 0.75),
    (5, "m05", "技术", "bge-m3 是多语言多粒度嵌入模型，1024维，支持中英文混合文本，适合语义检索场景。", 5, 0.7),
    (6, "m06", "技术", "Qdrant 向量数据库支持 payload 过滤、时间范围查询和 cosine/dot-product 距离。推荐用 cosine。", 10, 0.65),
    (7, "m07", "技术", "时间衰减公式：score = vector_score × exp(-λt)，λ 控制遗忘速率，通常取 0.01~0.1。", 4, 0.8),
    (8, "m08", "项目", "ATLAS 知识库系统目标：将课程转录稿提炼为 L1 结构化知识节点，写入 Qdrant + Obsidian Vault。", 0, 0.95),
    (9, "m09", "项目", "course_to_l1_pipeline.py 支持 --group 参数并行运行，组1处理前三门课程，组2处理后三门。", 0, 0.9),
    (10, "m10", "其他", "艾宾浩斯遗忘曲线：记忆在第1天、第3天、第7天、第14天、第30天复习效果最佳。", 30, 0.6),
]

# 查询集：每个查询有期望检索到的记忆 short_id 列表（ground truth）
QUERIES = [
    {
        "text": "如何建立预期吸引对方",
        "relevant": ["m01", "m02"],
        "topic": "情感-预期",
    },
    {
        "text": "故事与沟通的关系",
        "relevant": ["m04"],
        "topic": "情感-沟通",
    },
    {
        "text": "向量数据库怎么做时间衰减",
        "relevant": ["m06", "m07"],
        "topic": "技术-检索",
    },
    {
        "text": "知识库 pipeline 并行运行",
        "relevant": ["m08", "m09"],
        "topic": "项目",
    },
    {
        "text": "bge-m3 嵌入模型",
        "relevant": ["m05"],
        "topic": "技术-嵌入",
    },
    {
        "text": "记忆遗忘和复习时机",
        "relevant": ["m10", "m07"],
        "topic": "记忆科学",
    },
]

# short_id → int id 的映射（用于检索结果转换）
_ID_MAP = {m[1]: m[0] for m in MEMORIES}
_REVERSE_ID_MAP = {m[0]: m[1] for m in MEMORIES}

# ── HTTP 工具 ──────────────────────────────────────────────────────────────────
def http_json(url: str, method: str = "GET", body=None, timeout=30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ── 嵌入 ──────────────────────────────────────────────────────────────────────
_embed_cache: dict[str, list[float]] = {}

def embed(text: str) -> list[float]:
    if text in _embed_cache:
        return _embed_cache[text]
    resp = http_json(f"{OLLAMA_URL}/api/embeddings", "POST",
                     {"model": EMBED_MODEL, "prompt": text[:4000]}, timeout=60)
    vec = resp["embedding"]
    _embed_cache[text] = vec
    return vec


# ── Qdrant 操作 ────────────────────────────────────────────────────────────────
def setup_collection():
    try:
        http_json(f"{QDRANT_URL}/collections/{COLLECTION}", "DELETE", {})
    except Exception:
        pass
    http_json(f"{QDRANT_URL}/collections/{COLLECTION}", "PUT", {
        "vectors": {"size": VECTOR_DIM, "distance": "Cosine"}
    })


def insert_memories():
    now = datetime.now(timezone.utc)
    points = []
    for int_id, short_id, topic, content, age_days, importance in MEMORIES:
        vec = embed(content)
        created_at = (now - timedelta(days=age_days)).isoformat()
        points.append({
            "id": int_id,          # Qdrant requires int or UUID
            "vector": vec,
            "payload": {
                "mid": short_id,
                "topic": topic,
                "content": content,
                "age_days": age_days,
                "importance": importance,
                "created_at": created_at,
            }
        })
    http_json(f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true", "PUT",
              {"points": points})


# ── 三种检索策略 ──────────────────────────────────────────────────────────────
def retrieve_keyword(query: str, k: int = 3) -> list[str]:
    """朴素关键词匹配：字符级 bigram 交集，无向量，O(n) 遍历"""
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1))
    q_bi = bigrams(query)
    scores = []
    for int_id, short_id, topic, content, age_days, importance in MEMORIES:
        c_bi = bigrams(content)
        score = len(q_bi & c_bi) / max(len(q_bi), 1)
        scores.append((short_id, score))
    scores.sort(key=lambda x: -x[1])
    return [sid for sid, s in scores[:k] if s > 0]


def retrieve_vector(query: str, k: int = 3) -> tuple[list[str], float]:
    """朴素向量搜索：vanilla Qdrant cosine，返回 short_id 列表"""
    t0 = time.perf_counter()
    vec = embed(query)
    resp = http_json(f"{QDRANT_URL}/collections/{COLLECTION}/points/search", "POST", {
        "vector": vec,
        "limit": k,
        "with_payload": True,
    })
    latency = (time.perf_counter() - t0) * 1000  # ms
    ids = [_REVERSE_ID_MAP.get(hit["id"], str(hit["id"])) for hit in resp.get("result", [])]
    return ids, latency


def retrieve_atlas(query: str, k: int = 3, lambda_decay: float = 0.05) -> tuple[list[str], float]:
    """时间衰减重排：向量搜索 top-k*3 后，用 importance × exp(-λ×age) 重排"""
    t0 = time.perf_counter()
    vec = embed(query)
    resp = http_json(f"{QDRANT_URL}/collections/{COLLECTION}/points/search", "POST", {
        "vector": vec,
        "limit": min(len(MEMORIES), k * 3),
        "with_payload": True,
    })
    hits = resp.get("result", [])
    reranked = []
    for hit in hits:
        vscore = hit["score"]
        payload = hit["payload"]
        age_days = payload.get("age_days", 0)
        importance = payload.get("importance", 0.5)
        decay = math.exp(-lambda_decay * age_days)
        final_score = vscore * 0.6 + importance * 0.25 * decay + decay * 0.15
        short_id = _REVERSE_ID_MAP.get(hit["id"], str(hit["id"]))
        reranked.append((short_id, final_score))
    reranked.sort(key=lambda x: -x[1])
    latency = (time.perf_counter() - t0) * 1000
    ids = [sid for sid, _ in reranked[:k]]
    return ids, latency


# ── 评估指标 ──────────────────────────────────────────────────────────────────
def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    hits = sum(1 for r in retrieved[:k] if r in relevant)
    return hits / k if k > 0 else 0.0


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for r in retrieved[:k] if r in relevant)
    return hits / len(relevant)


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    K = 3
    print("=" * 64)
    print("ATLAS 语义检索对比基准")
    print(f"测试集：{len(MEMORIES)} 条记忆 / {len(QUERIES)} 个查询 / top-{K}")
    print("=" * 64)

    # 准备数据
    print("\n[1/3] 初始化 Qdrant collection 并插入测试记忆...")
    setup_collection()
    insert_memories()
    print(f"      已插入 {len(MEMORIES)} 条记忆")

    # 预热嵌入缓存（嵌入查询文本）
    print("\n[2/3] 预热嵌入缓存...")
    for q in QUERIES:
        embed(q["text"])

    # 运行评估
    print("\n[3/3] 运行检索评估...\n")
    results = {
        "keyword":  {"p@k": [], "r@k": [], "latency_ms": []},
        "vector":   {"p@k": [], "r@k": [], "latency_ms": []},
        "atlas":    {"p@k": [], "r@k": [], "latency_ms": []},
    }

    print(f"{'查询':<20} {'策略':<10} {'P@3':>6} {'R@3':>6} {'ms':>7}  {'命中'}")
    print("-" * 70)

    for q in QUERIES:
        text = q["text"]
        relevant = q["relevant"]

        # 关键词
        t0 = time.perf_counter()
        kw_ids = retrieve_keyword(text, K)
        kw_ms = (time.perf_counter() - t0) * 1000
        kw_p = precision_at_k(kw_ids, relevant, K)
        kw_r = recall_at_k(kw_ids, relevant, K)
        results["keyword"]["p@k"].append(kw_p)
        results["keyword"]["r@k"].append(kw_r)
        results["keyword"]["latency_ms"].append(kw_ms)
        print(f"{text[:18]:<20} {'keyword':<10} {kw_p:>6.2f} {kw_r:>6.2f} {kw_ms:>7.1f}  {kw_ids}")

        # 朴素向量
        vec_ids, vec_ms = retrieve_vector(text, K)
        vec_p = precision_at_k(vec_ids, relevant, K)
        vec_r = recall_at_k(vec_ids, relevant, K)
        results["vector"]["p@k"].append(vec_p)
        results["vector"]["r@k"].append(vec_r)
        results["vector"]["latency_ms"].append(vec_ms)
        print(f"{'':20} {'vector':<10} {vec_p:>6.2f} {vec_r:>6.2f} {vec_ms:>7.1f}  {vec_ids}")

        # 时间衰减重排
        atl_ids, atl_ms = retrieve_atlas(text, K)
        atl_p = precision_at_k(atl_ids, relevant, K)
        atl_r = recall_at_k(atl_ids, relevant, K)
        results["atlas"]["p@k"].append(atl_p)
        results["atlas"]["r@k"].append(atl_r)
        results["atlas"]["latency_ms"].append(atl_ms)
        print(f"{'':20} {'atlas':<10} {atl_p:>6.2f} {atl_r:>6.2f} {atl_ms:>7.1f}  {atl_ids}")
        print()

    # 汇总
    print("=" * 64)
    print(f"{'策略':<12} {'mean P@3':>10} {'mean R@3':>10} {'median ms':>12}")
    print("-" * 64)
    for name, r in results.items():
        mp = statistics.mean(r["p@k"])
        mr = statistics.mean(r["r@k"])
        ml = statistics.median(r["latency_ms"])
        print(f"{name:<12} {mp:>10.3f} {mr:>10.3f} {ml:>12.1f}")
    print("=" * 64)

    # 写结果文件
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/tmp/ATLAS-MemoryCore/benchmark/results_{ts}.json"
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {"embed_model": EMBED_MODEL, "vector_dim": VECTOR_DIM, "k": K,
                   "n_memories": len(MEMORIES), "n_queries": len(QUERIES)},
        "queries": QUERIES,
        "per_query": {q["text"]: {} for q in QUERIES},
        "summary": {name: {
            "mean_precision_at_k": statistics.mean(r["p@k"]),
            "mean_recall_at_k": statistics.mean(r["r@k"]),
            "median_latency_ms": statistics.median(r["latency_ms"]),
        } for name, r in results.items()},
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入: {out_path}")

    # 清理
    try:
        http_json(f"{QDRANT_URL}/collections/{COLLECTION}", "DELETE", {})
        print("已清理测试 collection")
    except Exception:
        pass


if __name__ == "__main__":
    main()
