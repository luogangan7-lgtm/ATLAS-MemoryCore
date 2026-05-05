#!/usr/bin/env python3
"""
课程转录稿 → L1 知识节点 v3
目标：完整度 ≥ 90%，超越手写思维导图
格式：#### 编号 [标题] + 核心内容 / 如何运用 / 关联知识 + 完整原文引用
支持：deepseek-v4-flash（默认）/ deepseek-v4-pro（高质量）
并行：--group 1 跑前半组，--group 2 跑后半组
"""
import os, sys, json, re, time, hashlib, urllib.request, zipfile
from pathlib import Path
from datetime import datetime, timezone

# ── 配置 ──────────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = "sk-048299902d784a418b1563ba720184fc"
DEEPSEEK_URL     = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL   = "deepseek-v4-flash"   # 改为 deepseek-v4-pro 获得更高质量

OLLAMA_URL       = "http://127.0.0.1:11434"
EMBED_MODEL      = "bge-m3"

QDRANT_URL       = "http://127.0.0.1:6333"
COLLECTION       = "atlas_memories"
VECTOR_DIM       = 1024

OBSIDIAN_VAULT   = "/Volumes/data/obsidian-vault"
BASE_DIR         = Path("/Volumes/XBSHgtyp/整理学习/01-情感学")
XMIND_DIR        = Path("/Volumes/XBSHgtyp/老电脑资料/临散学习整理")

# (course_dir_name, course_name, domain, xmind_file_or_None)
COURSES = [
    ("01-乌鸦救赎·关系缔造论",      "关系缔造论",  "情感学", "关系缔造论.xmind"),
    ("02-乌鸦救赎·预期式求爱聊天",   "预期式求爱",  "情感学", "关系缔造论.xmind"),
    ("09-乌鸦救赎·Play连招",         "Play连招",    "情感学", None),
    ("10-乌鸦救赎团队·破局",         "破局",        "情感学", None),
    ("11-故事沟通术",                "故事沟通术",  "情感学", None),
    ("12-散讲·实战案例",             "散讲合集",    "情感学", None),
]

# ── 工具函数 ──────────────────────────────────────────────────────────────────
def http_post(url, body, headers=None, timeout=300):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def http_put(url, body, timeout=30):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def read_file(path: Path) -> str | None:
    for enc in ("utf-8", "gbk", "gb2312", "utf-8-sig"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None

def stable_id(text: str) -> str:
    h = hashlib.md5(text.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

# ── XMind 解析 ────────────────────────────────────────────────────────────────
_xmind_cache: dict[str, dict[str, str]] = {}

def load_xmind(xmind_file: str) -> dict[str, str]:
    """解析 xmind 文件，返回 {顶层节点标题: 完整大纲文本}"""
    if xmind_file in _xmind_cache:
        return _xmind_cache[xmind_file]

    xmind_path = XMIND_DIR / xmind_file
    sections: dict[str, str] = {}

    if not xmind_path.exists():
        return sections

    try:
        with zipfile.ZipFile(xmind_path, 'r') as z:
            with z.open('content.json') as f:
                data = json.load(f)
    except Exception:
        return sections

    def node_to_lines(node, depth=0):
        lines = []
        title = node.get('title', '').strip()
        if title:
            lines.append('  ' * depth + ('- ' if depth > 0 else '') + title)
        for child in node.get('children', {}).get('attached', []):
            lines.extend(node_to_lines(child, depth + 1))
        return lines

    for sheet in data:
        root = sheet.get('rootTopic', {})
        for section in root.get('children', {}).get('attached', []):
            sec_title = section.get('title', '').strip()
            lines = node_to_lines(section)
            sections[sec_title] = '\n'.join(lines)

    _xmind_cache[xmind_file] = sections
    return sections

CN_NUM = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
          '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
          '十一': '11', '十二': '12', '十三': '13', '十四': '14',
          '十五': '15', '十六': '16', '十七': '17', '十八': '18'}

def _norm_num(s: str) -> str:
    return CN_NUM.get(s, s)

def find_xmind_section(sections: dict[str, str], filename: str) -> tuple[str, str] | tuple[None, None]:
    fname = Path(filename).stem
    fname_nums = re.findall(r'[一二三四五六七八九十]+|(?<!\d)\d+(?!\d)', fname)
    fname_normed = [_norm_num(n) for n in fname_nums]

    for key, val in sections.items():
        key_nums = re.findall(r'[一二三四五六七八九十]+|(?<!\d)\d+(?!\d)', key)
        key_normed = [_norm_num(n) for n in key_nums]

        if fname_normed and key_normed and fname_normed[0] == key_normed[0]:
            return key, val

        core = re.sub(r'^[第]?[一二三四五六七八九十\d]+[讲章课节][:：\s]*', '', key).strip()
        if core and len(core) > 2 and core in fname:
            return key, val

    return None, None

# ── Prompt 构建 ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是一位深度学习专家，擅长将课程内容转化为结构清晰、便于理解、可直接学以致用的知识文档。

【工作思路】
读懂转录稿后，对每段内容问自己这些问题：
- 讲了什么核心观点？有几个知识点？它们是什么关系（并列/递进/因果/举例）？
- 每个知识点的背后逻辑是什么？为什么这么说？
- 学习者需要理解什么、记住什么？
- 这个知识点在实际中怎么运用？在哪些场景下用？
- 这个知识点和其他哪些概念有关联（课程内部或更广泛的知识体系）？
- 有哪些案例、故事、话术在支撑这些观点？

【文档格式】
#### X.X [知识点标题]

**核心内容**
[1-3段书面语段落，阐释：是什么 + 为什么 + 深层逻辑 + 如何理解。至少2段，每段3-5句。]

**如何运用**
[实际场景中如何使用这个知识？什么情况下用？怎么操作？]

**关联知识**
[与哪些相关概念有内在联系？（课程内部关联 + 通用知识体系）]

> [紧接着放支撑该知识点的完整原文，不摘要不缩短]

---
层次说明：顶层(1. 2. 3.)、第二层(1.1 1.2)、第三层(1.1.1)、第四层(1.1.1.1)
所有层级均使用 `####` 标记，层级通过编号数字体现

【正文段落标准】
- 书面语，去除口头禅（"啊"、"呢"、"对吧"、"就是说"）
- 每个知识点至少写2-3段，每段3-5句话
- 要分析和解释，不只是转述

【引用块标准】
- 完整复制原文，严禁摘要或缩短
- 只删去连续4次以上完全相同的语气词
- 引用块可以很长，这是正常的

【完整度规则】
1. 整理任务，不是摘要任务，所有有价值的知识点都必须保留
2. 没有字数限制，宁可多写也不遗漏
3. 禁止使用"省略"、"如上"、"详见原文"
4. 直接输出文档内容，不要有任何前言"""


def build_prompt_with_xmind(course_name: str, title: str, xmind_section: str, transcript: str) -> str:
    min_chars = max(12000, int(len(transcript) * 0.25))
    return f"""课程：{course_name} ·{title}

【思维导图骨架（顶层知识点参考）】
{xmind_section}

【转录稿全文】
{transcript}

---
整理要求：
以思维导图骨架为顶层（1. 2. 3.），向下至少展开三层。每个知识节点完整结构：

#### X.X [知识点标题]

**核心内容**
[书面语段落...]

**如何运用**
[实际场景...]

**关联知识**
[关联...]

> [完整原文，不摘要不缩短]

---
- 转录稿中有骨架未涵盖的知识点，整理在相关节点下或最后单独列出
- 总输出不少于 {min_chars:,} 字
- 最终交付一份让人能看懂、能学习、能运用、知道如何关联其他知识的完整文档"""


def build_prompt_no_xmind(course_name: str, title: str, transcript: str) -> str:
    min_chars = max(12000, int(len(transcript) * 0.25))
    return f"""课程：{course_name} ·{title}

【转录稿全文】
{transcript}

---
整理要求：
按照讲师实际讲解的逻辑，识别所有知识点，自行构建层次结构（1. → 1.1 → 1.1.1）。
每个知识节点完整结构：

#### X.X [知识点标题]

**核心内容**
[书面语段落，分析解释，不只是转述...]

**如何运用**
[实际场景...]

**关联知识**
[关联...]

> [完整原文，不摘要不缩短]

---
- 总输出不少于 {min_chars:,} 字
- 最终交付一份让人能看懂、能学习、能运用的完整文档"""


# ── DeepSeek 调用 ──────────────────────────────────────────────────────────────
def deepseek(user_prompt: str, max_tokens: int = 65536) -> str | None:
    resp = http_post(
        DEEPSEEK_URL,
        {
            "model":       DEEPSEEK_MODEL,
            "messages":    [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            "max_tokens":  max_tokens,
            "temperature": 0.1,
        },
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        timeout=600,
    )
    if "error" in resp and "choices" not in resp:
        print(f"    [API错误] {resp['error']}")
        return None
    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not content:
        return None
    # 去除模型自我介绍的前言（找第一个 #### 标题）
    first = content.find('\n####')
    if 0 < first < 400:
        content = content[first:].lstrip()
    return content


# ── Ollama 嵌入 ───────────────────────────────────────────────────────────────
def embed(text: str) -> list[float] | None:
    resp = http_post(
        f"{OLLAMA_URL}/api/embeddings",
        {"model": EMBED_MODEL, "prompt": text[:6000]},
        timeout=60,
    )
    v = resp.get("embedding")
    return v if isinstance(v, list) and len(v) == VECTOR_DIM else None


# ── Qdrant ────────────────────────────────────────────────────────────────────
def ensure_collection():
    check = http_post(f"{QDRANT_URL}/collections/{COLLECTION}/points/count", {}, timeout=10)
    if "error" in check:
        http_put(
            f"{QDRANT_URL}/collections/{COLLECTION}",
            {"vectors": {"size": VECTOR_DIM, "distance": "Cosine"},
             "optimizers_config": {"default_segment_number": 2}},
        )
        print("  [Qdrant] 集合已重建")

def upsert_l1(point_id: str, vector: list[float], payload: dict) -> bool:
    resp = http_put(
        f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
        {"points": [{"id": point_id, "vector": vector, "payload": payload}]},
        timeout=30,
    )
    return resp.get("status") == "ok"


# ── Obsidian Vault 写入 ───────────────────────────────────────────────────────
def write_vault(domain: str, course: str, title: str, content: str,
                completeness: float) -> str | None:
    if not OBSIDIAN_VAULT:
        return None
    domain_dir = Path(OBSIDIAN_VAULT) / "L1" / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r'[/\\:*?"<>|]', '-', f"{course}·{title}").strip('-')[:80]
    filepath = domain_dir / f"{slug}.md"

    frontmatter = (
        "---\n"
        "level: L1\n"
        "content_type: principle\n"
        f"domain: {domain}\n"
        f"topic: {course}·{title}\n"
        f"course: {course}\n"
        f"created: {datetime.now(timezone.utc).isoformat()}\n"
        f'tags: ["{course}", "{domain}", "课程笔记"]\n'
        f"completeness_score: {completeness:.2f}\n"
        "---\n\n"
    )
    filepath.write_text(frontmatter + content, encoding="utf-8")
    return str(filepath.relative_to(OBSIDIAN_VAULT))


# ── 完整度估算 ────────────────────────────────────────────────────────────────
def calc_completeness(content: str, transcript_len: int) -> float:
    if transcript_len == 0:
        return 0.5
    ratio = len(content) / transcript_len
    if ratio >= 0.5:
        return 1.0
    elif ratio >= 0.35:
        return 0.90
    elif ratio >= 0.25:
        return 0.80
    elif ratio >= 0.15:
        return 0.70
    else:
        return max(0.3, ratio * 2)


# ── 单文件处理 ────────────────────────────────────────────────────────────────
def process_transcript(course_dir: Path, course_name: str, domain: str,
                        txt_path: Path, output_dir: Path,
                        xmind_sections: dict[str, str]) -> bool:
    title = txt_path.stem
    clean_title = re.sub(r'^\d+[、.．]\s*', '', title).strip()

    out_file = output_dir / f"{re.sub(r'[/\\:*?\"<>|]', '-', clean_title)[:80]}.md"
    if out_file.exists():
        print(f"    [跳过-已存在] {clean_title}")
        return True

    transcript = read_file(txt_path)
    if not transcript:
        print(f"    [跳过-编码失败] {txt_path.name}")
        return False

    transcript = transcript.strip()
    if len(transcript) < 200:
        print(f"    [跳过-内容太短] {txt_path.name}")
        return False

    xmind_key, xmind_section = find_xmind_section(xmind_sections, txt_path.name)

    if xmind_section:
        prompt = build_prompt_with_xmind(course_name, clean_title, xmind_section, transcript)
        print(f"    提炼中（+xmind:{xmind_key[:20]}）... ({len(transcript):,} 字)")
    else:
        prompt = build_prompt_no_xmind(course_name, clean_title, transcript)
        print(f"    提炼中（无xmind）... ({len(transcript):,} 字)")

    # 推理模型需要额外 token 余量（约 10000 reasoning overhead）
    target_tokens = min(131072, max(40000, int(len(transcript) * 0.5 / 1.5)) + 12000)
    content = deepseek(prompt, max_tokens=target_tokens)
    if not content:
        print(f"    [失败] DeepSeek 无返回")
        return False

    out_file.write_text(content, encoding="utf-8")

    completeness = calc_completeness(content, len(transcript))
    vault_path = write_vault(domain, course_name, clean_title, content, completeness)

    embed_text = f"{course_name} {clean_title}\n{content[:4000]}"
    vector = embed(embed_text)
    if not vector:
        print(f"    [警告] 嵌入失败，跳过 Qdrant 写入")
    else:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "level":              1,
            "status":             "active",
            "content":            content[:3000],
            "topic":              f"{course_name}·{clean_title}",
            "domain":             domain,
            "course":             course_name,
            "content_type":       "principle",
            "summary":            content[:500],
            "tags":               [course_name, domain, "课程笔记"],
            "completeness_score": completeness,
            "faithfulness_score": 1.0,
            "obsidian_path":      vault_path or "",
            "created_at":         now,
            "last_verified":      now,
            "freshness_score":    1.0,
            "source":             "course-transcript-v3",
            "transcript_chars":   len(transcript),
            "output_chars":       len(content),
        }
        ok = upsert_l1(stable_id(f"{course_name}{clean_title}{now[:10]}"), vector, payload)
        if not ok:
            print(f"    [警告] Qdrant 写入失败")

    ratio = len(content) / len(transcript) * 100
    print(f"    ✓ 完整度 {completeness*100:.0f}%  输出 {len(content):,} 字 / 转录稿 {len(transcript):,} 字（{ratio:.0f}%）")
    return True


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    # --group 1 跑前三个课程，--group 2 跑后三个课程，不传则全跑
    group = None
    if "--group" in sys.argv:
        idx = sys.argv.index("--group")
        try:
            group = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            pass

    if group == 1:
        courses = COURSES[:3]
        label = "组1 (01,02,09)"
    elif group == 2:
        courses = COURSES[3:]
        label = "组2 (10,11,12)"
    else:
        courses = COURSES
        label = "全部"

    print("=" * 60)
    print(f"课程知识提炼 v3  [{label}]")
    print(f"模型: {DEEPSEEK_MODEL}  PID: {os.getpid()}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    ensure_collection()

    total_ok, total_fail = 0, 0

    for course_dir_name, course_name, domain, xmind_file in courses:
        course_dir = BASE_DIR / course_dir_name
        if not course_dir.exists():
            print(f"\n[跳过] 目录不存在: {course_dir}")
            continue

        xmind_sections = load_xmind(xmind_file) if xmind_file else {}
        if xmind_sections:
            print(f"\n  已加载 xmind: {xmind_file}（{len(xmind_sections)} 个章节）")

        txt_files = sorted(course_dir.rglob("*.txt"))
        txt_files = [f for f in txt_files
                     if "核心知识整理" not in str(f) and not f.name.startswith("._")]

        if not txt_files:
            print(f"\n[跳过] 无转录稿: {course_name}")
            continue

        output_dir = course_dir / "核心知识整理"
        output_dir.mkdir(exist_ok=True)

        for wrong_dir in [course_dir / "转录稿" / "核心知识整理"]:
            if wrong_dir.exists():
                import shutil; shutil.rmtree(wrong_dir)

        print(f"\n{'='*60}")
        print(f"课程：【{course_name}】  共 {len(txt_files)} 个转录稿")
        if xmind_sections:
            print(f"      xmind 章节: {list(xmind_sections.keys())}")
        print(f"{'='*60}")

        for i, txt_path in enumerate(txt_files, 1):
            print(f"\n  [{i}/{len(txt_files)}] {txt_path.name}")
            ok = process_transcript(course_dir, course_name, domain,
                                    txt_path, output_dir, xmind_sections)
            if ok:
                total_ok += 1
            else:
                total_fail += 1
            time.sleep(2)

    resp = http_post(f"{QDRANT_URL}/collections/{COLLECTION}/points/count", {})
    total_nodes = resp.get("result", {}).get("count", "?")

    print(f"\n{'='*60}")
    print(f"[{label}] 完成！成功: {total_ok}，失败: {total_fail}")
    print(f"Qdrant L1 节点总数: {total_nodes}")
    print(f"Vault: {OBSIDIAN_VAULT}/L1/")

if __name__ == "__main__":
    main()
