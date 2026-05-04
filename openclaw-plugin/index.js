/**
 * ATLAS Memory v10.0.0-phase3 — 自主演化知识系统（L0-L3 · 整理Agent · 域向量匹配 · L1 Obsidian写入）
 *
 * 架构（四层，商业级）：
 *   INJECT  — LRU缓存 + 跳过短/重复 + 时间衰减 + 访问计数 + 注入 memory_type
 *   CAPTURE — agent_end（含用户消息上下文 + 质量过滤≥7 + 冲突检测）
 *             + llm_output 每5轮中途捕获
 *   LEARN   — after_tool_call 拦截搜索工具 → Qdrant
 *   TOOLS   — 9工具 + atlas_merge（近重复合并）+ atlas_obsidian_sync
 *
 * 商业级升级：
 *   ★ omlx Qwen3.5-9B 替代 Ollama qwen2.5（4s vs 25s，质量更高）
 *   ★ 冲突检测（新记忆与旧记忆矛盾时自动 keep_new/keep_old/merge）
 *   ★ 质量评分（提取时评分1-10，只存≥7分）
 *   ★ memory_type 字段（preference/fact/skill/project/constraint/event）
 *   ★ 用户消息纳入 CAPTURE 上下文
 *   ★ 过期记忆自动清理（hit_count=0 + age>90天 + importance=low）
 *   ★ atlas_merge 工具（近重复智能合并）
 *
 * Obsidian Bridge（v9.4.0 新增）：
 *   ★ 单向主权：Qdrant AI记忆 → Atlas_Mirror（只读进化监控台）
 *   ★ 主题聚类导出：memory_type + 主标签分组，[type] topic.md 高辨识度命名
 *   ★ 图谱融合：聚类文件底部生成 [[wikilinks]]，接入 Obsidian 知识图谱
 *   ★ 每日进化日志：_evolution/YYYY-MM-DD.md 按天切分，记录 CAPTURE/MERGE/PRUNE/UPGRADE
 *   ★ Dataview 仪表盘：_index.md 含空数据降级提示
 *
 * v9.5.0 升级：
 *   ★ atlas_feedback — 记忆反馈回路（负评降权/删除，防止错误记忆加权）
 *   ★ atlas_distill  — 知识提炼（DeepSeek云端合成通则，omlx备用）
 *   ★ atlas_timeline — 主题时间线查询
 *   ★ 版本化         — 冲突替换时保留旧版本（status:superseded），不再物理删除
 *   ★ INJECT改进    — 自动过滤负评记忆，优先注入[distilled]通则，追踪注入ID
 *   ★ EVOLVE自动提炼 — 同标签≥5条时自动触发distill，生成通则进入下次检索
 */

import http from 'http';
import https from 'https';
import { createHash } from 'crypto';
import { writeFile, readFile, mkdir, appendFile, unlink } from 'fs/promises';
import { homedir } from 'os';
import { join } from 'path';

// ── 常量 ──────────────────────────────────────────────────────────────────────
const QDRANT               = 'http://127.0.0.1:6333';
const OLLAMA               = 'http://127.0.0.1:11434';
const OMLX                 = 'http://127.0.0.1:7749';
const OMLX_MODEL           = 'Qwen3.5-9B-OptiQ-4bit';
const COLLECTION           = 'atlas_memories';
const EMBED_MODEL          = 'nomic-embed-text';
const VECTOR_DIM           = 768;
const SCORE_MIN            = 0.65;
const SCORE_DEDUP          = 0.92;
const SCORE_CONFLICT_MIN   = 0.75;  // ★ 冲突检测下界
const SCORE_CONFLICT_MAX   = 0.91;  // ★ 冲突检测上界（DEDUP以上已去重）
const INJECT_LIMIT         = 5;
const MIN_CAPTURE_CHARS    = 200;
const TIMEOUT_MS           = 10_000;
const INJECT_TIMEOUT_MS    = 2_500;  // INJECT hook 专用：超时即降级，不阻塞响应
const EXTRACT_TIMEOUT_MS   = 12_000; // omlx 快得多，12s 足够
const FETCH_TIMEOUT_MS     = 15_000;
const EMBED_CACHE_SIZE     = 200;
const CAPTURE_TURN_INTERVAL = 5;
const CHUNK_SIZE           = 1500;
const CHUNK_OVERLAP        = 300;
const MAX_CHUNKS           = 5;
const DECAY_MAX_PENALTY    = 0.4;
const DECAY_PERIOD_DAYS    = 180;
const BACKUP_DIR           = join(homedir(), '.atlas-backups');
const IMPORTANCE_LEVELS    = ['low', 'medium', 'high', 'critical'];
const HIT_UPGRADE          = { low: 5, medium: 12, high: 25 };
const STALE_AGE_DAYS       = 90;    // ★ 过期记忆清理阈值
const MIN_QUALITY_SCORE    = 7;     // ★ 只存质量≥7的记忆
const SEARCH_TOOL_KEYWORDS = ['search', 'harvester', 'google', 'brave', 'bing', 'duckduckgo', 'serp'];

// ── DeepSeek（云端合成，用于 distill）────────────────────────────────────────
const DEEPSEEK_URL          = 'https://api.deepseek.com';
const DEEPSEEK_MODEL        = 'deepseek-chat';
const DEEPSEEK_TIMEOUT_MS   = 30_000;
const DEEPSEEK_API_KEY      = process.env.DEEPSEEK_API_KEY ?? '';

// ── 反馈回路 ──────────────────────────────────────────────────────────────────
const FEEDBACK_DECAY        = 0.25;   // 负反馈降幅（wrong/outdated）
const FEEDBACK_BOOST        = 0.05;   // 正反馈升幅（correct）
const FEEDBACK_FILTER_MIN   = 0.5;    // INJECT 过滤门槛（低于此值不注入）
const FEEDBACK_DELETE_FLOOR = 0.2;    // 低于此值直接删除

// ── 知识提炼 ──────────────────────────────────────────────────────────────────
const DISTILL_MIN_COUNT     = 5;      // 同标签最少记忆数才触发提炼
const DISTILL_TAG           = '[distilled]';

// ── Obsidian Bridge 常量 ───────────────────────────────────────────────────────
const OBSIDIAN_VAULT         = process.env.ATLAS_OBSIDIAN_VAULT ?? '';
const OBSIDIAN_MIRROR_DIR    = 'Atlas_Mirror';
const EVOLUTION_LOG_SUBDIR   = '_evolution';
const MIRROR_LINK_MAX        = 5;
const MIRROR_EXPORT_INTERVAL = 6 * 60 * 60 * 1000;
const IMPORTANCE_ORDER       = { critical: 4, high: 3, medium: 2, low: 1 };

// ── v10 知识库常量 ─────────────────────────────────────────────────────────────
const LEVEL_RAW          = 0;  // L0 原料
const LEVEL_KNOWLEDGE    = 1;  // L1 知识
const LEVEL_INSIGHT      = 2;  // L2 关联
const LEVEL_WISDOM       = 3;  // L3 智识

const ORGANIZE_INTERVAL_MS   = 60 * 60 * 1000;         // 1h
const DOMAIN_INTERVAL_MS     = 6 * 60 * 60 * 1000;     // 6h
const ASSOCIATE_INTERVAL_MS  = 6 * 60 * 60 * 1000;     // 6h
const SYNTHESIZE_INTERVAL_MS = 12 * 60 * 60 * 1000;    // 12h
const META_INTERVAL_MS       = 24 * 60 * 60 * 1000;    // 24h

const FRESHNESS_REFRESH      = 0.40;  // 低于此值重新验证
const FRESHNESS_INJECT_MIN   = 0.20;  // 低于此值不注入
const DOMAIN_MATCH_SCORE     = 0.80;  // 域精确匹配门槛
const DOMAIN_SUBDOMAIN_SCORE = 0.65;  // 子域匹配门槛
const CLUSTER_MIN_SIZE       = 3;     // 聚类最小记忆数
const CLUSTER_MIN_SCORE      = 0.70;
const ASSOC_MIN_SCORE        = 0.65;  // 关联搜索下界
const ASSOC_MAX_SCORE        = 0.85;  // 关联搜索上界（避开直接重复）
const DECAY_HALF_LIFE        = { fast: 7, medium: 30, slow: 180 }; // 单位：天
const MCP_PORT               = parseInt(process.env.ATLAS_MCP_PORT ?? '8765');
const GITHUB_REPO            = process.env.ATLAS_GITHUB_REPO ?? '';

// 域目录映射（vault 根目录下的域文件夹名）
const DOMAIN_DIRS = {
  '营销': '营销', '品牌项目': '品牌项目', '情感学': '情感学',
  '战略': '战略', 'TikTok运营': 'TikTok运营', '五金工具-电焊机': '五金工具-电焊机',
  '储能电池': '储能电池', 'OKX交易': 'OKX交易',
};
const LEVEL_DIRS = ['L0-原料', 'L1-知识', 'L2-关联', 'L3-智识'];

// 域描述（用于向量匹配，整理Agent用）
const DOMAIN_DESCRIPTIONS = {
  '营销':        '营销策略 广告文案 品牌传播 流量获取 内容营销 用户转化 市场推广 促销活动 消费者心理',
  '品牌项目':    '香氛品牌 产品开发 品牌策略 视觉设计 产品定位 包装设计 品牌故事 产品规划',
  '情感学':      '情感关系 吸引力 搭讪 社交技巧 约会 恋爱 人际沟通 男女关系 吸引异性',
  '战略':        '商业战略 竞争分析 市场定位 商业模式 长期规划 企业管理 决策框架 战略思维',
  'TikTok运营':  'TikTok短视频 内容创作 算法 运营数据 海外社媒 粉丝增长 账号管理 视频剪辑',
  '五金工具-电焊机': '五金工具 电焊机 工业设备 产品规格 焊接技术 工具选型 供应链 硬件产品',
  '储能电池':    '储能电池 新能源 电力系统 电池技术 光伏储能 锂电池 能源管理 充放电',
  'OKX交易':     'OKX 加密货币 比特币 以太坊 交易策略 数字资产 DeFi 区块链 行情分析',
};
const ORGANIZE_BATCH_MAX = 20; // 整理Agent每次处理上限

// ── 运行时状态 ─────────────────────────────────────────────────────────────────
const embedCache     = new Map();
let embedCacheHits   = 0;
let embedCacheMisses = 0;
const sessionTurns   = new Map();
let lastInjectKey    = '';
let lastInjectResult = undefined;
let lastBackupTime   = null;
let   lastInjectedIds        = [];             // ★ INJECT 注入的记忆 ID，供 feedback 定位
const distillWrittenHashes   = new Set();      // ★ distill 已写入的 hash，阻止 CAPTURE 二次捕获
const domainEmbeddingCache   = new Map();      // 域描述向量缓存（整理Agent）

// ── WriteQueue（并发安全，P1=CAPTURE/LEARN，P2=Agent）────────────────────────
class WriteQueue {
  constructor() { this._queue = []; this._running = false; }
  push(priority, fn) {
    return new Promise((resolve, reject) => {
      this._queue.push({ priority, fn, resolve, reject });
      this._queue.sort((a, b) => a.priority - b.priority);
      this._drain();
    });
  }
  async _drain() {
    if (this._running || !this._queue.length) return;
    this._running = true;
    while (this._queue.length) {
      const { fn, resolve, reject } = this._queue.shift();
      try { resolve(await fn()); } catch (e) { reject(e); }
    }
    this._running = false;
  }
}
const writeQueue = new WriteQueue();
const WRITE_PRIORITY = { CAPTURE: 1, LEARN: 1, AGENT: 2 };

// ── Agent 锁（防止同一 Agent 并发执行）───────────────────────────────────────
const agentLocks = new Map([
  ['organize', false], ['domain', false], ['associate', false],
  ['synthesize', false], ['meta', false], ['restructure', false],
]);

async function runAgent(name, fn) {
  if (agentLocks.get(name)) return;
  agentLocks.set(name, true);
  try { await fn(); } finally { agentLocks.set(name, false); }
}

// ── HTTP/HTTPS 工具 ───────────────────────────────────────────────────────────
function httpReq(url, method = 'GET', body = null, extraHeaders = {}, timeoutMs = TIMEOUT_MS) {
  return new Promise((resolve) => {
    const u   = new URL(url);
    const mod = u.protocol === 'https:' ? https : http;
    const req = mod.request({
      hostname: u.hostname,
      port:     Number(u.port) || (u.protocol === 'https:' ? 443 : 80),
      path:     u.pathname + u.search,
      method,
      headers:  { 'Content-Type': 'application/json', ...extraHeaders },
      rejectUnauthorized: false,
    }, (res) => {
      let raw = '';
      res.on('data', c => { raw += c; });
      res.on('end', () => {
        try   { resolve({ ok: res.statusCode < 300, status: res.statusCode, body: JSON.parse(raw) }); }
        catch { resolve({ ok: res.statusCode < 300, status: res.statusCode, body: raw }); }
      });
    });
    req.setTimeout(timeoutMs, () => { req.destroy(); resolve({ ok: false, error: 'timeout' }); });
    req.on('error', e => resolve({ ok: false, error: e.message }));
    if (body !== null) req.write(JSON.stringify(body));
    req.end();
  });
}

// ── URL 网页抓取 ──────────────────────────────────────────────────────────────
function fetchUrlText(url, redirectsLeft = 3) {
  return new Promise((resolve) => {
    try {
      const u   = new URL(url);
      const mod = u.protocol === 'https:' ? https : http;
      const req = mod.request({
        hostname: u.hostname,
        port:     Number(u.port) || (u.protocol === 'https:' ? 443 : 80),
        path:     u.pathname + u.search,
        method:   'GET',
        headers:  { 'User-Agent': 'Mozilla/5.0 (compatible; atlas-memory/9.3)', 'Accept': 'text/html,text/plain,*/*' },
        rejectUnauthorized: false,
      }, (res) => {
        if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location && redirectsLeft > 0) {
          req.destroy();
          const next = res.headers.location.startsWith('http') ? res.headers.location : new URL(res.headers.location, url).href;
          resolve(fetchUrlText(next, redirectsLeft - 1));
          return;
        }
        let raw = '';
        res.setEncoding('utf8');
        res.on('data', c => { if (raw.length < 200_000) raw += c; });
        res.on('end', () => resolve({ ok: res.statusCode < 400, text: raw, contentType: res.headers['content-type'] ?? '' }));
      });
      req.setTimeout(FETCH_TIMEOUT_MS, () => { req.destroy(); resolve({ ok: false, error: 'timeout', text: '' }); });
      req.on('error', e => resolve({ ok: false, error: e.message, text: '' }));
      req.end();
    } catch (e) {
      resolve({ ok: false, error: e.message, text: '' });
    }
  });
}

function htmlToText(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/\s{2,}/g, ' ').trim();
}

function isSearchTool(toolName) {
  const lower = toolName.toLowerCase();
  return SEARCH_TOOL_KEYWORDS.some(k => lower.includes(k));
}

function searchResultToText(result, query) {
  if (!result) return '';
  if (typeof result === 'string') return result;
  if (Array.isArray(result?.content)) {
    return result.content.filter(b => b?.type === 'text').map(b => b.text ?? '').join('\n');
  }
  if (Array.isArray(result?.results)) {
    return result.results.map(r =>
      [r.title, r.url, r.snippet ?? r.description ?? r.body ?? ''].filter(Boolean).join(' — ')
    ).join('\n');
  }
  try { return JSON.stringify(result); } catch { return ''; }
}

// ── ① 嵌入（LRU 缓存，仍用 Ollama nomic-embed-text）────────────────────────
async function embed(text) {
  const key = createHash('sha256').update(text.slice(0, 300)).digest('hex').slice(0, 16);
  if (embedCache.has(key)) {
    embedCacheHits++;
    const v = embedCache.get(key);
    embedCache.delete(key);
    embedCache.set(key, v);
    return v;
  }
  embedCacheMisses++;
  const r = await httpReq(`${OLLAMA}/api/embeddings`, 'POST', {
    model: EMBED_MODEL, prompt: text.slice(0, 4000),
  });
  if (r.ok && Array.isArray(r.body?.embedding)) {
    if (embedCache.size >= EMBED_CACHE_SIZE) embedCache.delete(embedCache.keys().next().value);
    embedCache.set(key, r.body.embedding);
    return r.body.embedding;
  }
  return null;
}

// ── ★ omlx Qwen3.5-9B 推理（替代 Ollama 提取）───────────────────────────────
async function omlxGenerate(systemMsg, userMsg, maxTokens = 800, timeoutMs = EXTRACT_TIMEOUT_MS) {
  const r = await httpReq(
    `${OMLX}/v1/chat/completions`, 'POST',
    {
      model:       OMLX_MODEL,
      messages:    [
        { role: 'system', content: systemMsg },
        { role: 'user',   content: userMsg },
      ],
      temperature: 0.1,
      max_tokens:  maxTokens,
      stream:      false,
    },
    {},
    timeoutMs,
  );
  if (!r.ok) return null;
  return r.body?.choices?.[0]?.message?.content ?? null;
}
const AGENT_OMLX_TIMEOUT_MS = 90_000; // 后台Agent调用，允许更长等待

// ── ★ DeepSeek 云端推理（用于 distill 等复杂合成，token 有限制）─────────────
async function deepseekGenerate(systemMsg, userMsg, maxTokens = 400) {
  const key = DEEPSEEK_API_KEY || process.env.DEEPSEEK_API_KEY;
  if (!key) return null;
  const r = await httpReq(
    `${DEEPSEEK_URL}/v1/chat/completions`, 'POST',
    {
      model:       DEEPSEEK_MODEL,
      messages:    [
        { role: 'system', content: systemMsg },
        { role: 'user',   content: userMsg   },
      ],
      temperature: 0.3,
      max_tokens:  maxTokens,
      stream:      false,
    },
    { Authorization: `Bearer ${key}` },
    DEEPSEEK_TIMEOUT_MS,
  );
  if (!r.ok) return null;
  return r.body?.choices?.[0]?.message?.content ?? null;
}

// ── JSON 解析工具 ─────────────────────────────────────────────────────────────
function parseFactsJson(text) {
  if (!text) return [];
  const clean = text.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
  for (let i = 0; i < clean.length; i++) {
    if (clean[i] !== '[') continue;
    try {
      const parsed = JSON.parse(clean.slice(i));
      if (Array.isArray(parsed)) {
        return parsed.filter(f => typeof f?.content === 'string' && f.content.trim().length > 10);
      }
    } catch { /* try next */ }
  }
  return [];
}

function parseJsonObject(text) {
  if (!text) return null;
  const clean = text.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
  for (let i = 0; i < clean.length; i++) {
    if (clean[i] !== '{') continue;
    try {
      const parsed = JSON.parse(clean.slice(i));
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
    } catch { /* try next */ }
  }
  return null;
}

// ── ★ 事实提取（omlx + 质量过滤 + memory_type + 用户上下文）─────────────────
async function extractFacts(assistantText, userContext = '') {
  if (!assistantText || assistantText.length < MIN_CAPTURE_CHARS) return [];
  const sys = '你是记忆提取专家。严格只输出有效JSON数组，不要任何解释或额外文字。';
  const contextLine = userContext
    ? `\n用户提问/上下文（辅助理解）：\n${userContext.slice(0, 400)}\n`
    : '';
  const user =
    `从以下对话中提取 0-5 条值得长期记忆的重要事实。${contextLine}
只提取跨会话有价值的内容（用户偏好、技术决策、项目约束、重要能力、关键结论）。
不提取：临时任务、本次对话特有内容、泛泛而谈的信息。
对每条打质量分(1-10)，只有≥${MIN_QUALITY_SCORE}分才值得保存。

格式（JSON数组）：
[{"content":"事实内容（简洁准确，20-200字）","category":"work|personal|project|system|learning","importance":"low|medium|high|critical","tags":["标签"],"quality":8,"memory_type":"preference|fact|skill|project|constraint|event"}]
无重要内容返回[]

助手回复：
${assistantText.slice(0, 3000)}

JSON数组：`;
  const out = await omlxGenerate(sys, user, 1000);
  if (!out) return [];
  const facts = parseFactsJson(out);
  return facts.filter(f => (f.quality ?? 10) >= MIN_QUALITY_SCORE);
}

// ── ★ 网页知识提取（omlx）────────────────────────────────────────────────────
async function extractWebFacts(text, query) {
  if (!text || text.length < 80) return [];
  const sys = '你是知识提取助手。严格只输出有效JSON数组，不要任何解释。';
  const user =
    `从以下网络内容中提取有价值的知识。
搜索查询: ${(query ?? '').slice(0, 100)}

只提取客观、持久有效的知识（技术事实、操作方法、重要定义、最佳实践）。
不提取：广告、导航、时效性内容。最多3条，质量<7的不提取。

格式：[{"content":"知识点","category":"learning","importance":"low|medium|high","tags":["主题"],"quality":7,"memory_type":"fact|skill|constraint"}]
无价值内容返回[]

内容：
${text.slice(0, 3000)}

JSON数组：`;
  const out = await omlxGenerate(sys, user, 600);
  if (!out) return [];
  const facts = parseFactsJson(out);
  return facts.filter(f => (f.quality ?? 10) >= MIN_QUALITY_SCORE);
}

// ── ★ 冲突检测与解决 ─────────────────────────────────────────────────────────
async function detectConflict(newContent, candidates) {
  if (!candidates.length) return null;
  const sys = '你是记忆冲突检测助手。严格只输出JSON对象，不要解释。';
  const list = candidates.map((c, i) => `${i + 1}. ${c.payload?.content ?? ''}`).join('\n');
  const user =
    `判断新记忆是否与旧记忆存在语义矛盾（而非仅仅是补充或相关）：

新记忆：${newContent}

旧记忆：
${list}

输出JSON：{"has_conflict":true/false,"conflict_index":0,"action":"keep_new|keep_old|merge","merged_content":""}
说明：conflict_index从1开始（0=无冲突）。has_conflict=false时其他字段忽略。
merge时merged_content填写合并后的完整内容。`;
  const out = await omlxGenerate(sys, user, 250);
  if (!out) return null;
  return parseJsonObject(out);
}

// ── 时间衰减评分 ──────────────────────────────────────────────────────────────
function applyTimeDecay(hits) {
  const now = Date.now();
  return hits
    .map(h => {
      const created = h.payload?.created_at ? new Date(h.payload.created_at).getTime() : now;
      const ageDays = Math.max(0, (now - created) / 86_400_000);
      const penalty = Math.min(DECAY_MAX_PENALTY, (ageDays / DECAY_PERIOD_DAYS) * (DECAY_MAX_PENALTY / 2));
      return { ...h, effectiveScore: h.score * (1 - penalty) };
    })
    .sort((a, b) => b.effectiveScore - a.effectiveScore);
}

// ── v10 衰减速率推断 ──────────────────────────────────────────────────────────
function inferDecayRate(domain, tags = []) {
  const fastDomains = ['OKX交易'];
  const fastKeywords = ['价格', '行情', '市场', '汇率', 'price', 'market', '报价'];
  if (fastDomains.includes(domain)) return 'fast';
  if (tags.some(t => fastKeywords.some(k => t.includes(k)))) return 'fast';

  const slowDomains = ['战略', '情感学'];
  const slowKeywords = ['原则', '规律', '方法论', '底层逻辑', '核心', '战略', '框架', '模型'];
  if (slowDomains.includes(domain)) return 'slow';
  if (tags.some(t => slowKeywords.some(k => t.includes(k)))) return 'slow';

  return 'medium';
}

// ── 访问计数 + 自动升级 importance ────────────────────────────────────────────
async function trackAccess(hits) {
  for (const h of hits) {
    const hitCount  = (h.payload?.hit_count ?? 0) + 1;
    const imp       = h.payload?.importance ?? 'medium';
    const impIdx    = IMPORTANCE_LEVELS.indexOf(imp);
    const threshold = HIT_UPGRADE[imp];
    const newImp    = (threshold && hitCount >= threshold && impIdx < IMPORTANCE_LEVELS.length - 1)
      ? IMPORTANCE_LEVELS[impIdx + 1] : imp;
    const update    = { hit_count: hitCount, last_accessed_at: new Date().toISOString() };
    if (newImp !== imp) {
      update.importance = newImp;
      appendEvolutionLog('UPGRADE', `"${(h.payload?.content ?? '').slice(0, 50)}" ${imp}→${newImp}（访问${hitCount}次）`).catch(() => {});
    }
    await httpReq(
      `${QDRANT}/collections/${COLLECTION}/points/payload`, 'POST',
      { payload: update, points: [h.id] },
    );
  }
}

// ── 文本分块 ──────────────────────────────────────────────────────────────────
function chunkText(text, size = CHUNK_SIZE, overlap = CHUNK_OVERLAP) {
  if (text.length <= size) return [text];
  const chunks = [];
  let i = 0;
  while (i < text.length) {
    chunks.push(text.slice(i, i + size));
    if (i + size >= text.length) break;
    i += size - overlap;
  }
  return chunks;
}

// ── ★ 从 messages 提取对话上下文（含用户消息）───────────────────────────────
function extractConversationContext(messages) {
  if (!Array.isArray(messages)) return { assistantText: '', userContext: '' };
  const recent = messages.slice(-12);
  const getText = (msg) => {
    const c = msg.content;
    if (typeof c === 'string') return c;
    if (Array.isArray(c)) return c.filter(b => b?.type === 'text').map(b => b.text ?? '').join(' ');
    return '';
  };
  const userTexts      = recent.filter(m => m?.role === 'user').map(getText).filter(t => t.trim());
  const assistantTexts = recent.filter(m => m?.role === 'assistant').map(getText).filter(t => t.trim());
  return {
    assistantText: assistantTexts.slice(-2).join('\n\n').trim(),
    userContext:   userTexts.slice(-3).join('\n').trim(),
  };
}

// ── Qdrant 操作 ───────────────────────────────────────────────────────────────
async function ensureCollection() {
  const check = await httpReq(`${QDRANT}/collections/${COLLECTION}`);
  if (check.ok) return true;
  const create = await httpReq(`${QDRANT}/collections/${COLLECTION}`, 'PUT', {
    vectors:           { size: VECTOR_DIM, distance: 'Cosine' },
    on_disk_payload:   true,
    optimizers_config: { memmap_threshold: 20000 },
  });
  return create.ok;
}

function stableId(text) {
  return parseInt(createHash('sha256').update(text).digest('hex').slice(0, 15), 16);
}

async function upsert(vector, payload) {
  const id = stableId(payload.content + (payload.created_at ?? ''));
  const r  = await httpReq(`${QDRANT}/collections/${COLLECTION}/points?wait=true`, 'PUT', {
    points: [{ id, vector, payload }],
  });
  return { ok: r.ok, id, error: r.error };
}

async function qdrantSearch(vector, { limit = 5, category, minScore = SCORE_MIN } = {}) {
  const body = { vector, limit, with_payload: true, score_threshold: minScore };
  // ★ 永远过滤 superseded 版本
  const mustNot = [{ key: 'status', match: { value: 'superseded' } }];
  if (category && category !== 'any') {
    body.filter = { must: [{ key: 'category', match: { value: category } }], must_not: mustNot };
  } else {
    body.filter = { must_not: mustNot };
  }
  const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/search`, 'POST', body);
  if (!r.ok) return [];
  // ★ 过滤负反馈记忆 + 低鲜度记忆
  return (r.body?.result ?? []).filter(h =>
    (h.payload?.feedback_score  ?? 1.0) >= FEEDBACK_FILTER_MIN &&
    (h.payload?.freshness_score ?? 1.0) >= FRESHNESS_INJECT_MIN
  );
}

async function qdrantDelete(ids) {
  if (!ids.length) return { ok: true, deleted: 0 };
  const r = await httpReq(
    `${QDRANT}/collections/${COLLECTION}/points/delete?wait=true`, 'POST', { points: ids },
  );
  return { ok: r.ok, deleted: ids.length };
}

async function qdrantPatchPayload(id, patch) {
  return httpReq(
    `${QDRANT}/collections/${COLLECTION}/points/payload`, 'POST',
    { payload: patch, points: [id] },
  );
}

function fmtHits(hits) {
  return hits.map(h => ({
    id:               h.id,               // ★ 供 atlas_feedback 定位使用
    content:          h.payload?.content,
    category:         h.payload?.category,
    importance:       h.payload?.importance,
    memory_type:      h.payload?.memory_type ?? 'fact',
    tags:             h.payload?.tags ?? [],
    source:           h.payload?.source ?? 'unknown',
    created_at:       h.payload?.created_at,
    hit_count:        h.payload?.hit_count ?? 0,
    last_accessed_at: h.payload?.last_accessed_at,
    score:            Math.round((h.effectiveScore ?? h.score) * 1000) / 1000,
  }));
}

function formatInjectContext(hits) {
  if (!hits.length) return '';
  // ★ 通则([distilled])优先排在最前面
  const sorted = [...hits].sort((a, b) => {
    const aD = (a.payload?.tags ?? []).includes(DISTILL_TAG) ? 1 : 0;
    const bD = (b.payload?.tags ?? []).includes(DISTILL_TAG) ? 1 : 0;
    return bD - aD;
  });
  const lines = sorted.map(h => {
    const imp  = h.payload?.importance ?? 'medium';
    const type = h.payload?.memory_type ? `[${h.payload.memory_type}]` : '';
    const dist = (h.payload?.tags ?? []).includes(DISTILL_TAG) ? '[通则]' : '';
    const text = h.payload?.content ?? '';
    return `• [${imp}]${type}${dist} ${text}`;
  });
  return `<atlas_memory>\n以下是与当前对话相关的历史记忆（ATLAS Memory 自动检索）：\n${lines.join('\n')}\n</atlas_memory>`;
}

// ── ★ 知识提炼内部存储 ────────────────────────────────────────────────────────
async function _storeDistilled(tag, content, basis) {
  const vector = await embed(content);
  if (!vector) return null;
  await ensureCollection();
  const now  = new Date().toISOString();
  const tags = [tag, DISTILL_TAG];
  const payload = {
    content,
    category:           'work',
    importance:         'high',
    tags,
    memory_type:        'skill',
    created_at:         now,
    source:             'distill',
    session_key:        'system',
    hit_count:          0,
    last_accessed_at:   null,
    status:             'active',
    feedback_score:     1.0,
    distill_basis:      basis,
    level:              LEVEL_WISDOM,
    domain:             null,
    topic:              tag,
    freshness_score:    1.0,
    decay_rate:         inferDecayRate(null, tags),
    last_verified:      now,
    source_ids:         [],
    associated_ids:     [],
    derived_to_id:      null,
    obsidian_path:      null,
    acquisition_source: 'distill',
  };
  const h = createHash('sha256').update(content.slice(0, 200)).digest('hex').slice(0, 16);
  distillWrittenHashes.add(h);
  const r = await upsert(vector, payload);
  return r.ok ? { ok: true, id: r.id, content, basis } : null;
}

// ── ★ 知识提炼主流程（DeepSeek 优先，omlx 备用）─────────────────────────────
async function distillTagMemories(tag, logger, force = false) {
  // 1. 拉取该标签下的非superseded、非distilled记忆
  let offset = null;
  const tagPoints = [];
  do {
    const body = {
      limit: 50, with_payload: true, with_vector: false,
      filter: {
        must: [{ key: 'tags', match: { value: tag } }],
        must_not: [
          { key: 'status', match: { value: 'superseded' } },
          { key: 'tags',   match: { value: DISTILL_TAG  } },
        ],
      },
    };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    tagPoints.push(...(r.body?.result?.points ?? []));
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null && tagPoints.length < 100);

  if (tagPoints.length < DISTILL_MIN_COUNT) {
    return { ok: false, skipped: true, reason: `"${tag}" 下只有 ${tagPoints.length} 条记忆，需要 ≥${DISTILL_MIN_COUNT} 条` };
  }

  // 2. 检查是否已有通则（force=true 时跳过检查）
  if (!force) {
    const checkR = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', {
      limit: 5, with_payload: false, with_vector: false,
      filter: {
        must: [
          { key: 'tags', match: { value: tag        } },
          { key: 'tags', match: { value: DISTILL_TAG } },
        ],
        must_not: [{ key: 'status', match: { value: 'superseded' } }],
      },
    });
    if (checkR.ok && (checkR.body?.result?.points ?? []).length > 0) {
      return { ok: false, skipped: true, reason: `"${tag}" 已有通则，使用 force:true 强制重新提炼` };
    }
  }

  // 3. 构建提炼提示（token 控制：最多 10 条，截断至 1800 字符）
  const topMems = tagPoints
    .sort((a, b) => (b.payload?.hit_count ?? 0) - (a.payload?.hit_count ?? 0))
    .slice(0, 10)
    .map((p, i) => `${i + 1}. [${p.payload?.importance ?? 'medium'}] ${(p.payload?.content ?? '').slice(0, 150)}`)
    .join('\n');

  const sys  = '你是知识提炼专家。从多条经验中提炼出一条简洁、可直接应用的"通则"。只输出通则内容，不超过150字，不要编号和解释。';
  const user = `标签：${tag}\n\n原始经验：\n${topMems.slice(0, 1800)}\n\n提炼通则：`;

  // 4. 调用 DeepSeek（优先）或 omlx（备用）
  let principle = null;
  if (DEEPSEEK_API_KEY) {
    principle = await deepseekGenerate(sys, user, 300);
  }
  if (!principle?.trim()) {
    logger?.warn?.('[atlas-memory] distill: DeepSeek 不可用，回退 omlx');
    principle = await omlxGenerate(sys, user, 200);
  }
  if (!principle?.trim()) return null;

  return await _storeDistilled(tag, principle.trim(), tagPoints.length);
}

// ── ★ 带冲突检测的存储 ────────────────────────────────────────────────────────
async function storeWithConflict({ content, category = 'work', importance = 'medium', tags = [], memory_type = 'fact', source = 'manual', sessionKey, doConflictCheck = false }) {
  const vector = await embed(content);
  if (!vector) return { ok: false, error: 'Ollama embed 不可用' };

  // 精确去重
  const exactDup = await qdrantSearch(vector, { limit: 1, minScore: SCORE_DEDUP });
  if (exactDup.length) return { ok: true, deduplicated: true, similar: exactDup[0].payload?.content?.slice(0, 80) };

  let supersededId = null;  // ★ 版本化：记录被替换的旧版本 ID
  // ★ 冲突检测（仅 medium 以上重要性，避免对低价值内容浪费 omlx）
  if (doConflictCheck && IMPORTANCE_LEVELS.indexOf(importance) >= 1) {
    const candidates = await qdrantSearch(vector, { limit: 3, minScore: SCORE_CONFLICT_MIN });
    const conflicts  = candidates.filter(c => c.score < SCORE_DEDUP);
    if (conflicts.length > 0) {
      const res = await detectConflict(content, conflicts);
      if (res?.has_conflict) {
        const cidx = (res.conflict_index ?? 1) - 1;
        const conflictId = conflicts[Math.max(0, Math.min(cidx, conflicts.length - 1))]?.id;
        if (res.action === 'keep_old') {
          return { ok: true, skipped: true, reason: 'conflict_keep_old' };
        } else if (res.action === 'keep_new' && conflictId) {
          supersededId = conflictId;  // ★ 版本化：不删除，标记为 superseded
          await qdrantPatchPayload(conflictId, { status: 'superseded', superseded_at: new Date().toISOString() });
        } else if (res.action === 'merge' && res.merged_content?.trim() && conflictId) {
          supersededId = conflictId;  // ★ 版本化：合并时也保留旧版本
          await qdrantPatchPayload(conflictId, { status: 'superseded', superseded_at: new Date().toISOString() });
          content = res.merged_content.trim();
        }
      }
    }
  }

  await ensureCollection();
  const now     = new Date().toISOString();
  const tagList = Array.isArray(tags) ? tags : [];
  const payload = {
    content:            content.trim(),
    category,
    importance,
    tags:               tagList,
    memory_type,
    created_at:         now,
    source,
    session_key:        sessionKey ?? 'unknown',
    hit_count:          0,
    last_accessed_at:   null,
    status:             'active',
    feedback_score:     1.0,
    level:              LEVEL_KNOWLEDGE,
    domain:             null,
    topic:              tagList[0] ?? category ?? 'general',
    freshness_score:    1.0,
    decay_rate:         inferDecayRate(null, tagList),
    last_verified:      now,
    source_ids:         [],
    associated_ids:     [],
    derived_to_id:      null,
    obsidian_path:      null,
    acquisition_source: source,
  };
  const result = await upsert(vector, payload);
  if (result.ok && supersededId) {
    await qdrantPatchPayload(supersededId, { superseded_by: result.id }).catch(() => {});
  }
  return result.ok ? { ok: true, id: result.id } : { ok: false, error: result.error || 'Qdrant 写入失败' };
}

// ★ 向后兼容的 storeMemory（手动工具调用，启用冲突检测）
async function storeMemory(params) {
  return storeWithConflict({ ...params, doConflictCheck: true });
}

// ── ⑥ 批量存储（并行 embed → 逐条 intakeToL0，统一 L0 入口）──────────────────
async function batchStoreMemories(facts, source, sessionKey, doConflictCheck = false) {
  if (!facts.length) return { stored: 0, deduplicated: 0, skipped: 0 };
  await ensureCollection();

  // 并行 embed（保持性能）
  const embedded = await Promise.all(
    facts.map(async f => {
      const vector = await embed(f.content);
      return vector ? { f, vector } : null;
    })
  );
  const valid = embedded.filter(Boolean);
  let stored = 0, deduplicated = 0, skipped = 0;

  for (const { f, vector } of valid) {
    // 跳过 distill 刚写入的内容（防 CAPTURE 二次捕获）
    const ch = createHash('sha256').update(f.content.trim().slice(0, 200)).digest('hex').slice(0, 16);
    if (distillWrittenHashes.has(ch)) { deduplicated++; continue; }
    // 精确去重
    const dup = await qdrantSearch(vector, { limit: 1, minScore: SCORE_DEDUP });
    if (dup.length) { deduplicated++; continue; }

    // 冲突检测（medium+ 重要性）
    let content      = f.content.trim();
    const importance = f.importance ?? 'medium';
    let supersededId = null;
    if (doConflictCheck && IMPORTANCE_LEVELS.indexOf(importance) >= 1) {
      const candidates = await qdrantSearch(vector, { limit: 3, minScore: SCORE_CONFLICT_MIN });
      const conflicts  = candidates.filter(c => c.score < SCORE_DEDUP);
      if (conflicts.length > 0) {
        const res = await detectConflict(content, conflicts);
        if (res?.has_conflict) {
          const cidx       = (res.conflict_index ?? 1) - 1;
          const conflictId = conflicts[Math.max(0, Math.min(cidx, conflicts.length - 1))]?.id;
          if (res.action === 'keep_old') { skipped++; continue; }
          if ((res.action === 'keep_new' || res.action === 'merge') && conflictId) {
            supersededId = conflictId;
            await qdrantPatchPayload(conflictId, { status: 'superseded', superseded_at: new Date().toISOString() });
          }
          if (res.action === 'merge' && res.merged_content?.trim()) content = res.merged_content.trim();
        }
      }
    }

    // ★ v10 统一入口：Obsidian L0 + Qdrant（含 level/domain/freshness_score/decay_rate）
    const result = await intakeToL0({
      content,
      domain:      null,            // Phase 4 域检测Agent 自动填充
      topic:       f.tags?.[0] ?? f.category ?? 'general',
      source,
      tags:        Array.isArray(f.tags) ? f.tags : [],
      category:    f.category   ?? 'work',
      importance,
      memory_type: f.memory_type ?? 'fact',
      sessionKey,
    });

    if (result?.ok) {
      stored++;
      if (supersededId && result.id) {
        await qdrantPatchPayload(supersededId, { superseded_by: result.id }).catch(() => {});
      }
    }
  }

  if (stored > 0) {
    appendEvolutionLog('CAPTURE', `+${stored} 条记忆（${source}，去重${deduplicated}，冲突跳过${skipped}）`).catch(() => {});
  }
  return { stored, deduplicated, skipped };
}

// ── 后台进化：去重 + ★ 过期清理 ──────────────────────────────────────────────
async function runEvolution(logger) {
  logger?.info?.('[atlas-memory] 开始记忆进化（去重 + 过期清理）...');
  let offset = null;
  const allIds = [];
  do {
    const body = { limit: 250, with_payload: false, with_vector: false };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    allIds.push(...(r.body?.result?.points ?? []).map(p => p.id));
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null);

  if (allIds.length < 2) {
    logger?.info?.(`[atlas-memory] 进化完成：总数 ${allIds.length}，无需处理`);
    return { total: allIds.length, removed: 0, pruned: 0 };
  }

  const pointsWithVecs = [];
  for (let i = 0; i < allIds.length; i += 50) {
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points`, 'POST', {
      ids: allIds.slice(i, i + 50), with_vector: true, with_payload: true,
    });
    if (r.ok) pointsWithVecs.push(...(r.body?.result ?? []));
  }

  const toDelete = new Set();
  const now      = Date.now();

  // ★ 过期清理：hit_count=0 + age>90天 + importance='low'（跳过历史版本）
  for (const pt of pointsWithVecs) {
    if (pt.payload?.status === 'superseded') continue;  // ★ 版本历史永不过期清理
    const hitCount  = pt.payload?.hit_count ?? 0;
    const imp       = pt.payload?.importance ?? 'medium';
    const created   = pt.payload?.created_at ? new Date(pt.payload.created_at).getTime() : now;
    const ageDays   = (now - created) / 86_400_000;
    if (hitCount === 0 && imp === 'low' && ageDays > STALE_AGE_DAYS) {
      toDelete.add(pt.id);
    }
  }

  // 相似度去重（跳过历史版本）
  for (const pt of pointsWithVecs) {
    if (toDelete.has(pt.id) || !pt.vector) continue;
    if (pt.payload?.status === 'superseded') continue;  // ★ 不对历史版本做去重
    const similar = await qdrantSearch(pt.vector, { limit: 5, minScore: SCORE_DEDUP });
    for (const hit of similar) {
      if (hit.id === pt.id || toDelete.has(hit.id)) continue;
      const ptImp  = IMPORTANCE_LEVELS.indexOf(pt.payload?.importance  ?? 'medium');
      const hitImp = IMPORTANCE_LEVELS.indexOf(hit.payload?.importance ?? 'medium');
      toDelete.add(hitImp > ptImp ? pt.id : hit.id);
    }
  }

  if (toDelete.size > 0) {
    await qdrantDelete([...toDelete]);
    appendEvolutionLog('PRUNE', `清理 ${toDelete.size} 条记忆（过期/重复），剩余 ${allIds.length - toDelete.size} 条`).catch(() => {});
  }
  // ★ 自动提炼：统计标签分布，对积累 ≥ DISTILL_MIN_COUNT 条的标签自动生成通则
  const tagCount = new Map();
  for (const pt of pointsWithVecs) {
    if (pt.payload?.status === 'superseded') continue;
    if ((pt.payload?.tags ?? []).includes(DISTILL_TAG)) continue;
    for (const tag of (pt.payload?.tags ?? [])) {
      if (tag !== DISTILL_TAG) tagCount.set(tag, (tagCount.get(tag) ?? 0) + 1);
    }
  }
  const distillCandidates = [];
  for (const [tag, count] of tagCount) {
    if (count >= DISTILL_MIN_COUNT) {
      const hasDistilled = pointsWithVecs.some(pt =>
        !pt.payload?.status?.includes('superseded') &&
        (pt.payload?.tags ?? []).includes(DISTILL_TAG) &&
        (pt.payload?.tags ?? []).includes(tag)
      );
      if (!hasDistilled) distillCandidates.push({ tag, count });
    }
  }
  let distilled = 0;
  for (const { tag } of distillCandidates.sort((a, b) => b.count - a.count).slice(0, 3)) {
    const r = await distillTagMemories(tag, logger).catch(() => null);
    if (r?.ok) {
      distilled++;
      appendEvolutionLog('DISTILL', `自动提炼"${tag}"：${r.basis}条 → 通则（id:${r.id?.slice(0, 8)}）`).catch(() => {});
    }
  }
  logger?.info?.(`[atlas-memory] 进化完成：总数 ${allIds.length}，删除 ${toDelete.size} 条，自动提炼 ${distilled} 条通则`);
  return { total: allIds.length, removed: toDelete.size, distilled };
}

// ── ⑦ 备份 ───────────────────────────────────────────────────────────────────
async function backupCollection(logger, customPath) {
  let offset = null;
  const points = [];
  do {
    const body = { limit: 250, with_payload: true, with_vector: true };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    points.push(...(r.body?.result?.points ?? []));
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null);
  if (!points.length) return { ok: true, points: 0, file: null };
  const date     = new Date().toISOString().slice(0, 10);
  const filePath = customPath ?? join(BACKUP_DIR, `atlas-backup-${date}.json`);
  await mkdir(BACKUP_DIR, { recursive: true });
  await writeFile(filePath, JSON.stringify({ version: '9.3.0', collection: COLLECTION, created_at: new Date().toISOString(), points }, null, 2), 'utf8');
  lastBackupTime = new Date().toISOString();
  logger?.info?.(`[atlas-memory] 备份：${points.length} 条记忆 → ${filePath}`);
  return { ok: true, points: points.length, file: filePath };
}

// ── Obsidian Bridge：主题聚类导出 ─────────────────────────────────────────────
async function runMirrorExport(logger) {
  if (!OBSIDIAN_VAULT) return { ok: false, reason: 'ATLAS_OBSIDIAN_VAULT 未配置' };

  // 1. 拉取全量 points（不需要向量，只要 payload）
  let offset = null;
  const allPoints = [];
  do {
    const body = { limit: 250, with_payload: true, with_vector: false };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    allPoints.push(...(r.body?.result?.points ?? []));
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null);

  if (!allPoints.length) return { ok: true, written: 0, total: 0, clusters: 0 };

  // 2. 按 memory_type + 主标签 聚类（主标签 = tags[0] 或 category 作为兜底）
  const clusters = new Map(); // "{memory_type}|{tag}" → points[]
  for (const pt of allPoints) {
    const memType    = pt.payload?.memory_type ?? 'fact';
    const primaryTag = pt.payload?.tags?.[0] ?? pt.payload?.category ?? 'general';
    const key        = `${memType}|${primaryTag}`;
    if (!clusters.has(key)) clusters.set(key, []);
    clusters.get(key).push(pt);
  }

  // 3. 预算文件名映射（供 wikilinks 引用）
  const clusterFilename = (key) => {
    const [memType, tag] = key.split('|');
    return `[${memType}] ${tag}`;
  };

  // 4. 构建标签重叠关系（用于 wikilinks：同一 point 带多个 tag → 相关聚类互联）
  const tagToKeys = new Map();
  for (const [key, points] of clusters) {
    for (const pt of points) {
      for (const t of (pt.payload?.tags ?? [])) {
        if (!tagToKeys.has(t)) tagToKeys.set(t, new Set());
        tagToKeys.get(t).add(key);
      }
    }
  }

  // 5. 全量覆写每个聚类文件
  const memoriesDir = join(OBSIDIAN_VAULT, OBSIDIAN_MIRROR_DIR, 'memories');
  await mkdir(memoriesDir, { recursive: true });

  let written = 0;
  for (const [key, points] of clusters) {
    const [memType, tag] = key.split('|');

    // 按重要性 DESC → hit_count DESC 排序
    points.sort((a, b) => {
      const ia = IMPORTANCE_ORDER[a.payload?.importance] ?? 2;
      const ib = IMPORTANCE_ORDER[b.payload?.importance] ?? 2;
      if (ib !== ia) return ib - ia;
      return (b.payload?.hit_count ?? 0) - (a.payload?.hit_count ?? 0);
    });

    // 相关聚类：共享 tag 的其他聚类（去重，限 MIRROR_LINK_MAX 个）
    const relatedKeys = new Set();
    for (const pt of points) {
      for (const t of (pt.payload?.tags ?? [])) {
        for (const rk of (tagToKeys.get(t) ?? [])) {
          if (rk !== key) relatedKeys.add(rk);
        }
      }
    }
    const relatedLinks = [...relatedKeys]
      .slice(0, MIRROR_LINK_MAX)
      .map(rk => `[[${clusterFilename(rk)}]]`)
      .join('  ');

    // 统计摘要
    const total    = points.length;
    const avgHits  = total ? Math.round(points.reduce((s, p) => s + (p.payload?.hit_count ?? 0), 0) / total) : 0;
    const impCounts = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const pt of points) impCounts[pt.payload?.importance ?? 'medium']++;
    const now = new Date().toISOString();

    // 记忆列表（每条一节）
    const memoriesBody = points.map((pt, i) => {
      const imp   = pt.payload?.importance ?? 'medium';
      const hits  = pt.payload?.hit_count ?? 0;
      const date  = (pt.payload?.created_at ?? '').slice(0, 10);
      const src   = pt.payload?.source ?? '';
      const mtype = pt.payload?.memory_type ?? memType;
      const tags  = (pt.payload?.tags ?? []).map(t => `\`${t}\``).join(' ');
      return `### ${i + 1}. ${(pt.payload?.content ?? '').slice(0, 60)}${(pt.payload?.content ?? '').length > 60 ? '…' : ''}\n\n${pt.payload?.content ?? ''}\n\n*重要性: **${imp}** · 访问: ${hits}次 · 类型: ${mtype} · 来源: ${src} · ${date}*${tags ? `\n标签: ${tags}` : ''}\n`;
    }).join('\n---\n\n');

    const relatedSection = relatedLinks
      ? `\n## 关联主题\n\n${relatedLinks}\n`
      : '';

    const fileContent =
`---
memory_type: ${memType}
primary_tag: "${tag}"
total_memories: ${total}
avg_hit_count: ${avgHits}
critical_count: ${impCounts.critical}
high_count: ${impCounts.high}
medium_count: ${impCounts.medium}
low_count: ${impCounts.low}
last_updated: "${now}"
---

# [${memType}] ${tag}

> 共 **${total}** 条记忆 · 平均访问 **${avgHits}** 次 · 最后更新 ${now.slice(0, 16).replace('T', ' ')}

| 重要性 | 数量 |
|--------|------|
| 🔴 critical | ${impCounts.critical} |
| 🟠 high | ${impCounts.high} |
| 🟡 medium | ${impCounts.medium} |
| ⚪ low | ${impCounts.low} |

## 记忆内容

${memoriesBody}
${relatedSection}`;

    await writeFile(join(memoriesDir, `${clusterFilename(key)}.md`), fileContent, 'utf8');
    written++;
  }

  logger?.info?.(`[atlas-memory] Mirror 导出：${written} 个主题文件（${allPoints.length} 条记忆）→ ${memoriesDir}`);
  return { ok: true, written, total: allPoints.length, clusters: clusters.size, dir: memoriesDir };
}

// ── Obsidian Bridge：Dataview 仪表盘 ──────────────────────────────────────────
async function writeIndexDashboard() {
  if (!OBSIDIAN_VAULT) return;
  const mirrorDir = join(OBSIDIAN_VAULT, OBSIDIAN_MIRROR_DIR);
  await mkdir(mirrorDir, { recursive: true });

  const qdrantRes   = await httpReq(`${QDRANT}/collections/${COLLECTION}`);
  const totalPoints = qdrantRes.body?.result?.points_count ?? 0;
  const now         = new Date().toISOString();

  const content =
`---
type: atlas-dashboard
last_updated: "${now}"
---

# ATLAS Memory 监控台

> 向量库共 **${totalPoints}** 条记忆 · 最后刷新 ${now.slice(0, 16).replace('T', ' ')}
> 运行 \`atlas_obsidian_sync\` 重建聚类文件

---

## 高价值记忆 Top 10（按访问次数）

\`\`\`dataviewjs
const pages = dv.pages('"${OBSIDIAN_MIRROR_DIR}/memories"');
if (pages.length === 0) {
  dv.paragraph("⏳ 暂无数据，等待首次进化。请运行 \`atlas_obsidian_sync\` 工具。");
} else {
  dv.table(
    ["主题文件", "类型", "记忆数", "平均访问", "高价值数"],
    pages.sort(p => -(p.avg_hit_count ?? 0))
      .slice(0, 10)
      .map(p => [
        p.file.link,
        p.memory_type ?? "-",
        p.total_memories ?? 0,
        p.avg_hit_count ?? 0,
        (p.high_count ?? 0) + (p.critical_count ?? 0)
      ])
  );
}
\`\`\`

---

## 各主题记忆分布

\`\`\`dataviewjs
const pages = dv.pages('"${OBSIDIAN_MIRROR_DIR}/memories"');
if (pages.length === 0) {
  dv.paragraph("⏳ 暂无数据，等待首次进化。");
} else {
  dv.table(
    ["主题文件", "类型", "记忆总数", "🔴 critical", "🟠 high", "🟡 medium", "⚪ low"],
    pages.sort(p => -(p.total_memories ?? 0))
      .map(p => [
        p.file.link,
        p.memory_type ?? "-",
        p.total_memories ?? 0,
        p.critical_count ?? 0,
        p.high_count ?? 0,
        p.medium_count ?? 0,
        p.low_count ?? 0
      ])
  );
}
\`\`\`

---

## 近 7 天进化日志

\`\`\`dataviewjs
const logs = dv.pages('"${OBSIDIAN_MIRROR_DIR}/${EVOLUTION_LOG_SUBDIR}"')
  .sort(p => p.file.name, 'desc')
  .slice(0, 7);
if (logs.length === 0) {
  dv.paragraph("⏳ 尚无进化记录。记忆进化（CAPTURE / MERGE / PRUNE / UPGRADE）后自动生成。");
} else {
  dv.list(logs.map(p => p.file.link + " — " + p.file.name));
}
\`\`\`

---

*由 ATLAS Memory v9.4.0 · Obsidian Bridge 自动生成*
`;

  await writeFile(join(mirrorDir, '_index.md'), content, 'utf8');
}

// ── Obsidian Bridge：每日进化日志 ─────────────────────────────────────────────
async function appendEvolutionLog(type, message) {
  if (!OBSIDIAN_VAULT) return;
  const today   = new Date().toISOString().slice(0, 10);
  const logDir  = join(OBSIDIAN_VAULT, OBSIDIAN_MIRROR_DIR, EVOLUTION_LOG_SUBDIR);
  const logFile = join(logDir, `${today}.md`);
  const time    = new Date().toTimeString().slice(0, 5);
  try {
    await mkdir(logDir, { recursive: true });
    // 新文件：写入日志头
    let needsHeader = false;
    try { await readFile(logFile, 'utf8'); } catch { needsHeader = true; }
    if (needsHeader) {
      await writeFile(logFile,
        `---\ndate: ${today}\ntype: evolution-log\n---\n\n# 进化日志 ${today}\n\n`, 'utf8');
    }
    await appendFile(logFile, `- \`${time}\` **[${type}]** ${message}\n`, 'utf8');
  } catch { /* 静默：日志写失败不影响主流程 */ }
}

// ── v10 Schema 迁移（启动时运行，向后兼容旧记录）─────────────────────────────
async function migrateSchema(logger) {
  let offset = null;
  let patched = 0;
  const now = new Date().toISOString();
  do {
    const body = { limit: 250, with_payload: true, with_vector: false };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    const points = r.body?.result?.points ?? [];
    for (const pt of points) {
      const p = pt.payload ?? {};
      if (p.level !== undefined && p.freshness_score !== undefined) continue;
      const patch = {};
      if (p.level            === undefined) patch.level            = LEVEL_KNOWLEDGE;
      if (p.domain           === undefined) patch.domain           = null;
      if (p.topic            === undefined) patch.topic            = p.tags?.[0] ?? p.category ?? 'general';
      if (p.freshness_score  === undefined) patch.freshness_score  = 1.0;
      if (p.decay_rate       === undefined) patch.decay_rate       = 'medium';
      if (p.last_verified    === undefined) patch.last_verified    = now;
      if (p.source_ids       === undefined) patch.source_ids       = [];
      if (p.associated_ids   === undefined) patch.associated_ids   = [];
      if (p.derived_to_id    === undefined) patch.derived_to_id    = null;
      if (p.obsidian_path    === undefined) patch.obsidian_path    = null;
      if (p.acquisition_source === undefined) patch.acquisition_source = p.source ?? 'auto-capture';
      await qdrantPatchPayload(pt.id, patch);
      patched++;
    }
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null);
  if (patched > 0) logger?.info?.(`[atlas-memory] v10 schema 迁移：${patched} 条记录已更新`);
  return { patched };
}

// ── 启动时还原动态域（防重启丢失）────────────────────────────────────────────
async function restoreDynamicDomains(logger) {
  // Scroll all points, collect distinct non-null domain values not in static DOMAIN_DIRS
  const seen = new Set();
  let offset = null;
  do {
    const body = { limit: 250, with_payload: true, with_vector: false,
      filter: { must_not: [{ is_null: { key: 'domain' } }] } };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    for (const pt of r.body?.result?.points ?? []) {
      const d = pt.payload?.domain;
      if (d && !DOMAIN_DIRS[d]) seen.add(d);
    }
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null);

  if (!seen.size) return;

  for (const domainName of seen) {
    DOMAIN_DIRS[domainName] = domainName;
    // Read description from _维度图谱.md if it exists
    let desc = domainName;
    if (OBSIDIAN_VAULT) {
      const mapPath = join(OBSIDIAN_VAULT, domainName, '_维度图谱.md');
      const raw = await readFile(mapPath, 'utf8').catch(() => null);
      if (raw) {
        const m = raw.match(/^description:\s*(.+)$/m);
        if (m) desc = m[1].trim();
      }
    }
    DOMAIN_DESCRIPTIONS[domainName] = desc;
    // Pre-warm embedding cache
    const vec = await embed(desc);
    if (vec) domainEmbeddingCache.set(domainName, vec);
    logger?.info?.(`[atlas-memory] 还原动态域: "${domainName}"`);
  }
}

// ── v10 L0 原料统一摄入 ───────────────────────────────────────────────────────
async function intakeToL0({ content, domain, topic, source = 'manual', tags = [], category = 'work', importance = 'medium', memory_type = 'fact', sessionKey }) {
  return writeQueue.push(WRITE_PRIORITY.CAPTURE, async () => {
    const domainDir = DOMAIN_DIRS[domain] ?? null;
    const level0Dir = OBSIDIAN_VAULT
      ? (domainDir ? join(OBSIDIAN_VAULT, domainDir, 'L0-原料') : join(OBSIDIAN_VAULT, '_未分类'))
      : null;
    const slug     = (topic ?? 'untitled').replace(/[/\\:*?"<>|]/g, '-').slice(0, 40);
    const date     = new Date().toISOString().slice(0, 10);
    const filename = `${slug}-${date}.md`;
    let   obsidianPath = null;

    if (level0Dir) {
      await mkdir(level0Dir, { recursive: true });
      const md = [
        '---',
        `level: L0`,
        `domain: ${domain ?? '未分类'}`,
        `topic: ${topic ?? ''}`,
        `source: ${source}`,
        `importance: ${importance}`,
        `memory_type: ${memory_type}`,
        `created: ${new Date().toISOString()}`,
        `tags: [${tags.map(t => `"${t}"`).join(', ')}]`,
        '---',
        '',
        content,
        '',
      ].join('\n');
      await writeFile(join(level0Dir, filename), md, 'utf8');
      obsidianPath = domainDir ? `${domainDir}/L0-原料/${filename}` : `_未分类/${filename}`;
    }

    const vector = await embed(content);
    if (!vector) return { ok: false, error: 'embed failed' };
    await ensureCollection();
    const now = new Date().toISOString();
    const decay_rate = inferDecayRate(domain, tags);
    const payload = {
      content:            content.trim(),
      category,
      importance,
      tags:               Array.isArray(tags) ? tags : [],
      memory_type,
      created_at:         now,
      source,
      session_key:        sessionKey ?? 'manual',
      hit_count:          0,
      last_accessed_at:   null,
      status:             'active',
      feedback_score:     1.0,
      level:              LEVEL_RAW,
      domain:             domain ?? null,
      topic:              topic ?? tags[0] ?? category,
      freshness_score:    1.0,
      decay_rate,
      last_verified:      now,
      source_ids:         [],
      associated_ids:     [],
      derived_to_id:      null,
      obsidian_path:      obsidianPath,
      acquisition_source: source,
    };
    return upsert(vector, payload);
  });
}

// ── Phase 3：整理Agent（L0→L1）────────────────────────────────────────────────

function cosine(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  return dot / (Math.sqrt(na) * Math.sqrt(nb) || 1);
}

async function getDomainEmbeddings() {
  const total = Object.keys(DOMAIN_DESCRIPTIONS).length;
  if (domainEmbeddingCache.size >= total) return domainEmbeddingCache;
  for (const [domain, desc] of Object.entries(DOMAIN_DESCRIPTIONS)) {
    if (domainEmbeddingCache.has(domain)) continue;
    const vec = await embed(desc);
    if (vec) domainEmbeddingCache.set(domain, vec);
  }
  return domainEmbeddingCache;
}

async function matchDomainForVector(vector) {
  const cache = await getDomainEmbeddings();
  let best = null, bestScore = 0;
  for (const [domain, domVec] of cache) {
    const score = cosine(vector, domVec);
    if (score > bestScore) { bestScore = score; best = domain; }
  }
  if (bestScore >= DOMAIN_MATCH_SCORE)    return { domain: best, score: bestScore };
  if (bestScore >= DOMAIN_SUBDOMAIN_SCORE) return { domain: best, score: bestScore, weak: true };
  return { domain: null, score: bestScore };
}

async function extractL1Content(content, domain) {
  const sys = '你是知识整理专家。严格只输出有效JSON对象，不要任何解释或markdown代码块。';
  const user =
    `将以下原始知识整理为结构化L1知识节点。
域：${domain ?? '通用'}
原始内容：${content.slice(0, 2000)}

输出JSON（字段不可省略）：
{
  "title": "简洁主题标题（10字以内）",
  "summary": "3-5句话的知识摘要（保留核心观点，不要废话）",
  "key_points": ["核心知识点1", "核心知识点2", "核心知识点3"],
  "applicable_scenarios": "这些知识适用的实际场景（1-2句）",
  "tags": ["标签1", "标签2", "标签3"]
}`;
  const out = await omlxGenerate(sys, user, 700, AGENT_OMLX_TIMEOUT_MS);
  if (!out) return null;
  return parseJsonObject(out);
}

async function writeL1Obsidian(domain, topic, l1Data, sourceL0Path) {
  if (!OBSIDIAN_VAULT) return null;
  const domainDir = DOMAIN_DIRS[domain] ?? '_未分类';
  const l1Dir     = domain ? join(OBSIDIAN_VAULT, domainDir, 'L1-知识') : join(OBSIDIAN_VAULT, '_未分类');
  await mkdir(l1Dir, { recursive: true });
  const slug     = topic.replace(/[/\\:*?"<>|]/g, '-').slice(0, 50);
  const filename = `${slug}.md`;
  const lines = [
    '---',
    `level: L1`,
    `domain: ${domain ?? '未分类'}`,
    `topic: ${topic}`,
    `source_l0: ${sourceL0Path ?? ''}`,
    `created: ${new Date().toISOString()}`,
    `tags: [${(l1Data.tags ?? []).map(t => `"${t}"`).join(', ')}]`,
    '---',
    '',
    `# ${l1Data.title ?? topic}`,
    '',
    '## 知识摘要',
    l1Data.summary ?? '',
    '',
    '## 核心知识点',
    ...(l1Data.key_points ?? []).map(p => `- ${p}`),
    '',
    '## 适用场景',
    l1Data.applicable_scenarios ?? '',
    '',
  ];
  await writeFile(join(l1Dir, filename), lines.join('\n'), 'utf8');
  return domain ? `${domainDir}/L1-知识/${filename}` : `_未分类/${filename}`;
}

async function runOrganizeAgent(logger) {
  // 1. 拉取 level=0 的记录（含向量）
  let offset = null;
  const l0Points = [];
  do {
    const body = {
      limit: 50, with_payload: true, with_vector: true,
      filter: { must: [{ key: 'level', match: { value: LEVEL_RAW } }] },
    };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    l0Points.push(...(r.body?.result?.points ?? []));
    offset = r.body?.result?.next_page_offset ?? null;
    if (l0Points.length >= ORGANIZE_BATCH_MAX) break;
  } while (offset != null);

  if (!l0Points.length) {
    logger?.debug?.('[atlas-memory] 整理Agent: 无L0待处理记录');
    return { processed: 0, promoted: 0, skipped: 0 };
  }

  logger?.info?.(`[atlas-memory] 整理Agent: 处理 ${l0Points.length} 条L0记录`);
  let promoted = 0, skipped = 0;

  for (const pt of l0Points) {
    const content = pt.payload?.content;
    if (!content?.trim() || !pt.vector) { skipped++; continue; }

    // 2. 域匹配
    const match  = await matchDomainForVector(pt.vector);
    const domain = match.domain;

    // 3. omlx 提取 L1 结构化内容
    const l1Data = await extractL1Content(content, domain).catch(() => null);
    if (!l1Data?.title || !l1Data?.summary) { skipped++; continue; }

    const topic = l1Data.title;
    const tags  = [...new Set([...(l1Data.tags ?? []), ...(pt.payload?.tags ?? [])])];

    // 4. 写 Obsidian L1 文件
    const obsidianPath = await writeL1Obsidian(domain, topic, l1Data, pt.payload?.obsidian_path)
      .catch(() => null);

    // 5. 更新 Qdrant：level→1，domain，topic，obsidian_path
    const now = new Date().toISOString();
    await writeQueue.push(WRITE_PRIORITY.AGENT, async () => {
      await qdrantPatchPayload(pt.id, {
        level:          LEVEL_KNOWLEDGE,
        domain,
        topic,
        tags,
        obsidian_path:  obsidianPath,
        last_verified:  now,
        freshness_score: 1.0,
        decay_rate:     inferDecayRate(domain, tags),
      });
    });

    promoted++;
    appendEvolutionLog('ORGANIZE', `L0→L1: "${topic}" → [${domain ?? '未分类'}] (匹配度${match.score.toFixed(2)})`).catch(() => {});
  }

  logger?.info?.(`[atlas-memory] 整理Agent: 晋升${promoted}条, 跳过${skipped}条`);
  return { processed: l0Points.length, promoted, skipped };
}

// ── Phase 4：域检测Agent ──────────────────────────────────────────────────────

function centroid(vectors) {
  if (!vectors.length) return null;
  const dim = vectors[0].length;
  const sum = new Array(dim).fill(0);
  for (const v of vectors) for (let i = 0; i < dim; i++) sum[i] += v[i];
  const len = vectors.length;
  return sum.map(x => x / len);
}

function clusterNodes(nodes, minSim = CLUSTER_MIN_SCORE, minSize = CLUSTER_MIN_SIZE) {
  // Greedy threshold clustering: first unclustered node becomes seed
  const clusters = [];
  const assigned = new Set();

  for (let i = 0; i < nodes.length; i++) {
    if (assigned.has(i)) continue;
    const cluster = [i];
    assigned.add(i);
    for (let j = i + 1; j < nodes.length; j++) {
      if (assigned.has(j)) continue;
      if (cosine(nodes[i].vector, nodes[j].vector) >= minSim) {
        cluster.push(j);
        assigned.add(j);
      }
    }
    if (cluster.length >= minSize) clusters.push(cluster.map(idx => nodes[idx]));
  }
  return clusters;
}

async function inferNewDomain(samples) {
  const excerpts = samples.slice(0, 5).map((s, i) => `${i + 1}. ${s.payload?.content?.slice(0, 120) ?? ''}`).join('\n');
  const sys = '你是知识分类专家。严格输出JSON，不要解释，不要markdown代码块。';
  const user =
    `以下是同一知识簇中的记忆样本：\n${excerpts}\n\n` +
    `请推断这个知识簇属于什么业务域，输出：\n` +
    `{"domain_name":"不超过6个汉字的域名","description":"一句话描述（15-30字）",` +
    `"dimensions":["维度1","维度2","维度3"],"keywords":["关键词1","关键词2","关键词3","关键词4","关键词5"]}`;

  const raw = await deepseekGenerate(sys, user, 400);
  if (!raw) return null;
  try {
    const cleaned = raw.replace(/```[a-z]*\n?/gi, '').replace(/```/g, '').trim();
    const parsed = JSON.parse(cleaned);
    if (!parsed.domain_name || !parsed.description) return null;
    parsed.dimensions = Array.isArray(parsed.dimensions) ? parsed.dimensions.slice(0, 5) : [];
    parsed.keywords   = Array.isArray(parsed.keywords)   ? parsed.keywords.slice(0, 8)   : [];
    return parsed;
  } catch {
    return null;
  }
}

async function createDomainStructure(domainName, domainInfo) {
  if (!OBSIDIAN_VAULT) return null;
  const domainDir = join(OBSIDIAN_VAULT, domainName);
  for (const level of LEVEL_DIRS) {
    await mkdir(join(domainDir, level), { recursive: true });
    // ensure .gitkeep
    const kp = join(domainDir, level, '.gitkeep');
    try { await writeFile(kp, '', 'utf8'); } catch {}
  }

  // Write dimension map
  const dims  = (domainInfo.dimensions ?? []).map(d => `- ${d}`).join('\n');
  const kws   = (domainInfo.keywords ?? []).map(k => `#${k}`).join(' ');
  const now   = new Date().toISOString();
  const mapMd = [
    '---',
    `domain: ${domainName}`,
    `description: ${domainInfo.description ?? ''}`,
    `created: ${now}`,
    `auto_detected: true`,
    '---',
    '',
    `# ${domainName} · 维度图谱`,
    '',
    `> ${domainInfo.description ?? ''}`,
    '',
    '## 核心维度',
    dims,
    '',
    '## 关键词',
    kws,
    '',
    '## 层级结构',
    '- [[L0-原料]] — 原始信息、未加工片段',
    '- [[L1-知识]] — 经过整理的知识点',
    '- [[L2-关联]] — 跨域关联洞见',
    '- [[L3-智识]] — 提炼的高阶原则',
  ].join('\n');

  await writeFile(join(domainDir, '_维度图谱.md'), mapMd, 'utf8');
  return `${domainName}/_维度图谱.md`;
}

async function runDomainDetectAgent(logger) {
  // 1. Scroll all domain=null active records with vectors
  const unassigned = [];
  let offset = null;
  do {
    const body = {
      limit: 500,
      with_payload: true,
      with_vector: true,
      filter: { must: [{ is_null: { key: 'domain' } }, { must_not: [{ match: { key: 'status', value: 'superseded' } }] }] },
    };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    const pts = r.body?.result?.points ?? [];
    unassigned.push(...pts);
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null);

  if (unassigned.length < CLUSTER_MIN_SIZE) {
    logger?.info?.(`[atlas-memory] 域检测Agent: 未分类记录${unassigned.length}条，未达聚类最低${CLUSTER_MIN_SIZE}条，跳过`);
    return { checked: unassigned.length, clusters_found: 0, new_domains: 0, assigned: 0 };
  }

  logger?.info?.(`[atlas-memory] 域检测Agent: 扫描${unassigned.length}条未分类记录`);

  // 2. Cluster
  const clusters = clusterNodes(unassigned);
  logger?.info?.(`[atlas-memory] 域检测Agent: 聚类${clusters.length}个`);

  let newDomains = 0;
  let assigned = 0;

  for (const cluster of clusters) {
    const vectors = cluster.map(n => n.vector);
    const c = centroid(vectors);

    // 3. Compare centroid against existing domains
    const match = await matchDomainForVector(c);

    let targetDomain;
    if (match.domain && match.score >= DOMAIN_MATCH_SCORE) {
      // Assign to existing domain
      targetDomain = match.domain;
    } else {
      // 4. Infer new domain via DeepSeek
      const domainInfo = await inferNewDomain(cluster);
      if (!domainInfo) continue;

      const newName = domainInfo.domain_name;
      if (DOMAIN_DIRS[newName]) {
        // Race condition: domain was just created; just assign
        targetDomain = newName;
      } else {
        // Create directory + map
        await createDomainStructure(newName, domainInfo);

        // 5. Update runtime caches
        DOMAIN_DIRS[newName] = newName;
        DOMAIN_DESCRIPTIONS[newName] = domainInfo.description;
        const vec = await embed(domainInfo.description);
        if (vec) domainEmbeddingCache.set(newName, vec);

        targetDomain = newName;
        newDomains++;

        appendEvolutionLog('DOMAIN_NEW',
          `新域: "${newName}" — ${domainInfo.description} (从${cluster.length}条记录聚类发现)`
        ).catch(() => {});
        logger?.info?.(`[atlas-memory] 域检测Agent: 新域 "${newName}"`);
      }
    }

    // 6. Patch all nodes in cluster → target domain (batch via raw HTTP)
    const now = new Date().toISOString();
    await writeQueue.push(WRITE_PRIORITY.AGENT, async () => {
      const ids = cluster.map(n => n.id);
      await httpReq(
        `${QDRANT}/collections/${COLLECTION}/points/payload`, 'POST',
        { payload: { domain: targetDomain, last_verified: now }, points: ids },
      );
    });

    // Also move Obsidian file if obsidian_path exists and is in _未分类
    for (const node of cluster) {
      const op = node.payload?.obsidian_path;
      if (op && op.startsWith('_未分类/') && OBSIDIAN_VAULT) {
        const src = join(OBSIDIAN_VAULT, op);
        const filename = op.split('/').pop();
        const destDir = join(OBSIDIAN_VAULT, targetDomain, 'L0-原料');
        await mkdir(destDir, { recursive: true });
        const dest = join(destDir, filename);
        try {
          const content = await readFile(src, 'utf8').catch(() => null);
          if (content) {
            // Update domain field in frontmatter
            const updated = content.replace(/^domain: 未分类$/m, `domain: ${targetDomain}`);
            await writeFile(dest, updated, 'utf8');
            await unlink(src).catch(() => {});
            const newPath = `${targetDomain}/L0-原料/${filename}`;
            await writeQueue.push(WRITE_PRIORITY.AGENT, () =>
              qdrantPatchPayload(node.id, { obsidian_path: newPath })
            );
          }
        } catch {}
      }
    }

    assigned += cluster.length;
    appendEvolutionLog('DOMAIN_ASSIGN',
      `域归属: "${targetDomain}" ← ${cluster.length}条 (相似度${match.score?.toFixed(2) ?? 'new'})`
    ).catch(() => {});
  }

  logger?.info?.(`[atlas-memory] 域检测Agent: 新域${newDomains}个, 归属${assigned}条`);
  return { checked: unassigned.length, clusters_found: clusters.length, new_domains: newDomains, assigned };
}

// ── Phase 5：关联Agent ────────────────────────────────────────────────────────

let lastAssociateRun = 0; // unix ms，用于只取上轮以来新增的L1

async function generateCrossInsight(nodeA, nodeB) {
  const ca = nodeA.payload?.content?.slice(0, 200) ?? '';
  const cb = nodeB.payload?.content?.slice(0, 200) ?? '';
  const da = nodeA.payload?.domain ?? '未分类';
  const db = nodeB.payload?.domain ?? '未分类';
  const sys = '你是跨域知识关联专家。严格输出一段100-150字的中文洞察，不要解释，不要标题，不要JSON。';
  const user =
    `域A（${da}）知识：${ca}\n\n域B（${db}）知识：${cb}\n\n` +
    `请写出这两条知识的跨域关联洞察：它们共同揭示了什么规律？如何相互印证或补充？对实际决策有何启示？`;
  return omlxGenerate(sys, user, 300, AGENT_OMLX_TIMEOUT_MS);
}

async function writeL2Obsidian(domain, topic, insight, srcAPath, srcBPath, domainB) {
  if (!OBSIDIAN_VAULT) return null;
  const domainDir = DOMAIN_DIRS[domain] ?? domain;
  const dir = join(OBSIDIAN_VAULT, domainDir, 'L2-关联');
  await mkdir(dir, { recursive: true });
  const slug = topic.replace(/[/\\:*?"<>|]/g, '-').slice(0, 40);
  const date = new Date().toISOString().slice(0, 10);
  const filename = `${slug}-${date}.md`;
  const linkA = srcAPath ? `[[${srcAPath.replace(/\.md$/, '')}]]` : '';
  const linkB = srcBPath ? `[[${srcBPath.replace(/\.md$/, '')}]]` : '';
  const md = [
    '---',
    `level: L2`,
    `domain: ${domain}`,
    `linked_domain: ${domainB}`,
    `topic: ${topic}`,
    `created: ${new Date().toISOString()}`,
    '---',
    '',
    `# ${topic}`,
    '',
    insight,
    '',
    '## 来源',
    `- ${linkA || srcAPath || '(未知)'}`,
    `- ${linkB || srcBPath || '(未知)'}`,
  ].join('\n');
  await writeFile(join(dir, filename), md, 'utf8');
  return `${domainDir}/L2-关联/${filename}`;
}

async function appendWikilink(obsidianPath, linkTarget) {
  if (!OBSIDIAN_VAULT || !obsidianPath) return;
  const fullPath = join(OBSIDIAN_VAULT, obsidianPath);
  const link = `\n\n## 关联洞见\n- [[${linkTarget.replace(/\.md$/, '')}]]\n`;
  await appendFile(fullPath, link, 'utf8').catch(() => {});
}

async function runAssociateAgent(logger) {
  const since = lastAssociateRun;
  lastAssociateRun = Date.now();

  // 1. Fetch L1 nodes added since last run (or all L1 if first run)
  const l1Nodes = [];
  let offset = null;
  const filter = since > 0
    ? { must: [
        { match: { key: 'level', value: LEVEL_KNOWLEDGE } },
        { match: { key: 'status', value: 'active' } },
        { range: { key: 'created_at', gte: new Date(since).toISOString() } },
      ] }
    : { must: [
        { match: { key: 'level', value: LEVEL_KNOWLEDGE } },
        { match: { key: 'status', value: 'active' } },
      ] };

  do {
    const body = { limit: 200, with_payload: true, with_vector: true, filter };
    if (offset != null) body.offset = offset;
    const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
    if (!r.ok) break;
    l1Nodes.push(...(r.body?.result?.points ?? []));
    offset = r.body?.result?.next_page_offset ?? null;
  } while (offset != null);

  if (!l1Nodes.length) {
    logger?.info?.('[atlas-memory] 关联Agent: 无新L1节点，跳过');
    return { checked: 0, created: 0 };
  }

  logger?.info?.(`[atlas-memory] 关联Agent: 检查${l1Nodes.length}个L1节点`);
  let created = 0;

  for (const node of l1Nodes) {
    const nodeDomain = node.payload?.domain ?? null;

    // 2. Cross-domain similarity search
    const hits = await qdrantSearch(node.vector, {
      limit: 10,
      minScore: ASSOC_MIN_SCORE,
      filter: {
        must: [
          { match: { key: 'level', value: LEVEL_KNOWLEDGE } },
          { match: { key: 'status', value: 'active' } },
        ],
        // Exclude same node
        must_not: [{ has_id: [node.id] }],
      },
    });

    // Filter: different domain + score in (ASSOC_MIN_SCORE, ASSOC_MAX_SCORE]
    const candidates = hits.filter(h => {
      const hd = h.payload?.domain ?? null;
      return h.score <= ASSOC_MAX_SCORE && hd !== nodeDomain;
    });

    for (const partner of candidates.slice(0, 2)) { // max 2 associations per node
      const partnerDomain = partner.payload?.domain ?? null;

      // 3. Generate cross-domain insight via omlx
      const insight = await generateCrossInsight(node, partner);
      if (!insight || insight.length < 30) continue;

      const topicA = node.payload?.topic ?? node.payload?.tags?.[0] ?? '知识';
      const topicB = partner.payload?.topic ?? partner.payload?.tags?.[0] ?? '知识';
      const insightTopic = `${topicA}×${topicB}`;

      // 4. Write L2 Obsidian files for BOTH domains
      const pathA = node.payload?.obsidian_path ?? null;
      const pathB = partner.payload?.obsidian_path ?? null;

      const domainADir = nodeDomain ?? '未分类';
      const domainBDir = partnerDomain ?? '未分类';

      const l2PathA = await writeL2Obsidian(domainADir, insightTopic, insight, pathA, pathB, domainBDir);
      const l2PathB = partnerDomain && partnerDomain !== nodeDomain
        ? await writeL2Obsidian(domainBDir, insightTopic, insight, pathB, pathA, domainADir)
        : null;

      // 5. Append wikilinks to L1 source files
      if (l2PathA) {
        await appendWikilink(pathA, l2PathA);
        await appendWikilink(pathB, l2PathA);
      }

      // 6. Upsert L2 node in Qdrant
      const vector = await embed(insight);
      if (vector) {
        await writeQueue.push(WRITE_PRIORITY.AGENT, async () => {
          const now = new Date().toISOString();
          const decay_rate = 'medium';
          await upsert(vector, {
            content:            insight,
            category:           'work',
            importance:         'high',
            tags:               [domainADir, domainBDir, 'cross-domain'],
            memory_type:        'insight',
            created_at:         now,
            source:             'associate-agent',
            session_key:        'agent',
            hit_count:          0,
            last_accessed_at:   null,
            status:             'active',
            feedback_score:     1.0,
            level:              LEVEL_INSIGHT,
            domain:             domainADir,
            topic:              insightTopic,
            freshness_score:    1.0,
            decay_rate,
            last_verified:      now,
            source_ids:         [],
            associated_ids:     [node.id, partner.id],
            derived_to_id:      null,
            obsidian_path:      l2PathA,
            acquisition_source: 'associate-agent',
          });
        });
        created++;
        appendEvolutionLog('ASSOCIATE',
          `L2洞见: "${insightTopic}" [${domainADir}×${domainBDir}]`
        ).catch(() => {});
      }
    }
  }

  logger?.info?.(`[atlas-memory] 关联Agent: 新建${created}个L2洞见`);
  return { checked: l1Nodes.length, created };
}

// ── 工具结果格式 ──────────────────────────────────────────────────────────────
function jsonResult(payload) {
  return { content: [{ type: 'text', text: JSON.stringify(payload, null, 2) }] };
}

// ── 插件注册 ──────────────────────────────────────────────────────────────────
export const name        = 'atlas-memory';
export const description = 'ATLAS Memory v10.0.0-phase5 — 自主演化知识系统（L0-L3四层 · 整理/域检测/关联Agent · 跨域L1碰撞 · L2洞见 · wikilinks · atlas_organize · atlas_domain_detect · atlas_associate）';

export function register(api) {
  const logger = api.logger;

  ensureCollection()
    .then(() => migrateSchema(logger))
    .then(() => restoreDynamicDomains(logger))
    .catch(() => {});
  setInterval(() => runEvolution(logger).catch(() => {}), 24 * 60 * 60 * 1000);
  setInterval(() => backupCollection(logger).catch(() => {}), 7 * 24 * 60 * 60 * 1000);
  // Phase 3：整理Agent（1h 周期 + 启动后 10s 首次触发）
  setInterval(() => runAgent('organize', () => runOrganizeAgent(logger)).catch(() => {}), ORGANIZE_INTERVAL_MS);
  setTimeout(() => runAgent('organize', () => runOrganizeAgent(logger)).catch(() => {}), 10_000);
  // Phase 4：域检测Agent（6h 周期 + 启动后 30s 首次触发）
  setInterval(() => runAgent('domain', () => runDomainDetectAgent(logger)).catch(() => {}), DOMAIN_INTERVAL_MS);
  setTimeout(() => runAgent('domain', () => runDomainDetectAgent(logger)).catch(() => {}), 30_000);
  // Phase 5：关联Agent（6h 周期 + 启动后 60s 首次触发，在域检测之后）
  setInterval(() => runAgent('associate', () => runAssociateAgent(logger)).catch(() => {}), ASSOCIATE_INTERVAL_MS);
  setTimeout(() => runAgent('associate', () => runAssociateAgent(logger)).catch(() => {}), 60_000);

  // Obsidian Bridge：每 6 小时自动刷新监控台
  if (OBSIDIAN_VAULT) {
    logger?.info?.(`[atlas-memory] Obsidian Bridge 启动，vault: ${OBSIDIAN_VAULT}`);
    setInterval(async () => {
      await runMirrorExport(logger).catch(() => {});
      await writeIndexDashboard().catch(() => {});
    }, MIRROR_EXPORT_INTERVAL);
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // INJECT
  // ══════════════════════════════════════════════════════════════════════════════
  api.on('before_prompt_build', async (event, _ctx) => {
    const query = (event.prompt ?? '').trim();
    if (query.length < 15) return;
    const key = query.slice(0, 200);
    if (key === lastInjectKey) return lastInjectResult;
    try {
      // 硬超时：INJECT_TIMEOUT_MS 内未完成即降级，不阻塞响应
      const work = (async () => {
        const vector = await embed(query);
        if (!vector) return undefined;
        const hits = await qdrantSearch(vector, { limit: INJECT_LIMIT });
        if (!hits.length) return undefined;
        const decayed = applyTimeDecay(hits);
        lastInjectedIds = decayed.map(h => h.id);  // ★ 追踪注入 ID，供 feedback 定位
        trackAccess(decayed).catch(() => {});
        return { prependContext: formatInjectContext(decayed) };
      })();
      const deadline = new Promise(res => setTimeout(() => res(undefined), INJECT_TIMEOUT_MS));
      const result   = await Promise.race([work, deadline]);
      lastInjectKey    = key;
      lastInjectResult = result;
      return result;
    } catch { /* 静默降级 */ }
  }, { priority: 50 });

  // ══════════════════════════════════════════════════════════════════════════════
  // CAPTURE — ★ 含用户上下文 + 质量过滤 + 冲突检测
  // ══════════════════════════════════════════════════════════════════════════════
  api.on('agent_end', (event, ctx) => {
    if (!event.success) return;
    (async () => {
      try {
        const { assistantText, userContext } = extractConversationContext(event.messages);
        if (assistantText.length < MIN_CAPTURE_CHARS) return;
        const facts = await extractFacts(assistantText, userContext);
        const valid = facts.filter(f => f.content?.trim());
        if (valid.length) {
          const r = await batchStoreMemories(valid, 'auto-capture', ctx.sessionKey, true); // ★ 冲突检测开启
          if (r.stored > 0) logger?.debug?.(`[atlas-memory] agent_end: +${r.stored} 条，去重${r.deduplicated}，冲突跳过${r.skipped}`);
        }
      } catch (e) {
        logger?.debug?.(`[atlas-memory] capture error: ${e.message}`);
      }
    })();
  });

  // ══════════════════════════════════════════════════════════════════════════════
  // CAPTURE — 中途捕获（每 N 轮）
  // ══════════════════════════════════════════════════════════════════════════════
  api.on('llm_output', (event, ctx) => {
    const sid   = event.sessionId ?? ctx.sessionId ?? 'unknown';
    const count = (sessionTurns.get(sid) ?? 0) + 1;
    sessionTurns.set(sid, count);
    if (count % CAPTURE_TURN_INTERVAL !== 0) return;
    const text = (event.assistantTexts ?? []).join('\n\n').trim();
    if (text.length < MIN_CAPTURE_CHARS) return;
    (async () => {
      try {
        const facts = await extractFacts(text);
        const valid = facts.filter(f => f.content?.trim());
        if (valid.length) {
          const r = await batchStoreMemories(valid, 'mid-capture', ctx.sessionKey, false);
          if (r.stored > 0) logger?.debug?.(`[atlas-memory] mid-capture: +${r.stored} 条（第${count}轮）`);
        }
      } catch (e) {
        logger?.debug?.(`[atlas-memory] mid-capture error: ${e.message}`);
      }
    })();
  });

  api.on('session_end', (_event, ctx) => {
    if (ctx.sessionId) sessionTurns.delete(ctx.sessionId);
  });

  // ══════════════════════════════════════════════════════════════════════════════
  // LEARN — 搜索工具自动学习
  // ══════════════════════════════════════════════════════════════════════════════
  api.on('after_tool_call', (event, ctx) => {
    if (event.error || !isSearchTool(event.toolName)) return;
    (async () => {
      try {
        const query = event.params?.query ?? event.params?.q ?? event.params?.keyword ?? event.toolName;
        const text  = searchResultToText(event.result, query);
        if (text.length < 80) return;
        const facts = await extractWebFacts(text, String(query));
        const valid = facts.filter(f => f.content?.trim());
        if (valid.length) {
          const r = await batchStoreMemories(valid, `web-learn:${event.toolName}`, ctx.sessionKey, false);
          if (r.stored > 0) logger?.info?.(`[atlas-memory] web-learn: ${event.toolName} → +${r.stored} 条知识`);
        }
      } catch (e) {
        logger?.debug?.(`[atlas-memory] web-learn error (${event.toolName}): ${e.message}`);
      }
    })();
  });

  // ══════════════════════════════════════════════════════════════════════════════
  // SUPPLEMENT
  // ══════════════════════════════════════════════════════════════════════════════
  api.registerMemoryCorpusSupplement({
    async search({ query, maxResults = 5 }) {
      try {
        const vector  = await embed(query);
        if (!vector) return [];
        const hits    = await qdrantSearch(vector, { limit: maxResults, minScore: 0.50 });
        const decayed = applyTimeDecay(hits);
        return decayed.map(h => ({
          corpus:     'atlas',
          path:       `atlas:${h.id}`,
          title:      h.payload?.tags?.[0] ?? h.payload?.category ?? 'memory',
          kind:       'atlas-memory',
          score:      h.effectiveScore ?? h.score,
          snippet:    (h.payload?.content ?? '').slice(0, 300),
          source:     'atlas-memory',
          sourceType: 'vector-db',
          updatedAt:  h.payload?.created_at,
        }));
      } catch { return []; }
    },
    async get() { return null; },
  });

  // ══════════════════════════════════════════════════════════════════════════════
  // TOOLS
  // ══════════════════════════════════════════════════════════════════════════════

  // atlas_store
  api.registerTool(() => ({
    name: 'atlas_store',
    description:
      '将重要信息存入语义记忆库。自动进行冲突检测（与已有记忆矛盾时智能合并/替换），' +
      '相似度≥0.92时去重跳过。支持 memory_type 分类。',
    parameters: {
      type: 'object', required: ['content'],
      properties: {
        content:     { type: 'string',  description: '要存储的内容（20-500字）' },
        category:    { type: 'string',  enum: ['personal', 'work', 'project', 'system', 'learning'], default: 'work' },
        importance:  { type: 'string',  enum: ['low', 'medium', 'high', 'critical'], default: 'medium' },
        memory_type: { type: 'string',  enum: ['preference', 'fact', 'skill', 'project', 'constraint', 'event'], default: 'fact' },
        tags:        { type: 'array',   items: { type: 'string' }, default: [] },
      },
    },
    execute: async (_callId, params) => {
      const { content, category = 'work', importance = 'medium', memory_type = 'fact', tags = [] } = params ?? {};
      if (!content?.trim()) return jsonResult({ error: 'content 不能为空' });
      const result = await storeMemory({ content, category, importance, memory_type, tags, source: 'manual' });
      if (!result.ok) return jsonResult({ error: result.error });
      if (result.deduplicated) return jsonResult({ ok: true, deduplicated: true, similar: result.similar });
      if (result.skipped) return jsonResult({ ok: true, skipped: true, reason: result.reason });
      return jsonResult({ ok: true, id: result.id, category, importance, memory_type });
    },
  }));

  // atlas_recall
  api.registerTool(() => ({
    name: 'atlas_recall',
    description: '从语义记忆库检索相关知识（向量搜索 + 时间衰减排序 + 访问计数）。',
    parameters: {
      type: 'object', required: ['query'],
      properties: {
        query:       { type: 'string',  description: '搜索查询（自然语言）' },
        limit:       { type: 'integer', default: 5, minimum: 1, maximum: 20 },
        category:    { type: 'string',  enum: ['personal', 'work', 'project', 'system', 'learning', 'any'], default: 'any' },
        min_score:   { type: 'number',  default: 0.65, minimum: 0.1, maximum: 1.0 },
      },
    },
    execute: async (_callId, params) => {
      const { query, limit = 5, category = 'any', min_score = SCORE_MIN } = params ?? {};
      if (!query?.trim()) return jsonResult({ error: 'query 不能为空', results: [], count: 0 });
      const vector  = await embed(query);
      if (!vector) return jsonResult({ error: 'Ollama embed 不可用', results: [], count: 0 });
      const hits    = await qdrantSearch(vector, { limit, category, minScore: min_score });
      const decayed = applyTimeDecay(hits);
      trackAccess(decayed).catch(() => {});
      return jsonResult({ query, count: decayed.length, results: fmtHits(decayed) });
    },
  }));

  // atlas_delete
  api.registerTool(() => ({
    name: 'atlas_delete',
    description: '按语义相似度删除记忆（建议先用 atlas_recall 确认）。',
    parameters: {
      type: 'object', required: ['query'],
      properties: {
        query:     { type: 'string', description: '要删除内容的描述' },
        min_score: { type: 'number', default: 0.85 },
      },
    },
    execute: async (_callId, params) => {
      const { query, min_score = 0.85 } = params ?? {};
      if (!query?.trim()) return jsonResult({ error: 'query 不能为空' });
      const vector = await embed(query);
      if (!vector) return jsonResult({ error: 'embed 失败' });
      const hits = await qdrantSearch(vector, { limit: 10, minScore: min_score });
      if (!hits.length) return jsonResult({ deleted: 0, message: '未找到匹配记忆' });
      const ids = hits.map(h => h.id);
      const r   = await qdrantDelete(ids);
      return jsonResult(r.ok ? { deleted: r.deleted, ids } : { error: 'Qdrant 删除失败' });
    },
  }));

  // atlas_stats
  api.registerTool(() => ({
    name: 'atlas_stats',
    description: '查看 ATLAS 记忆库完整状态：记忆数、模型、缓存命中率、备份时间。',
    parameters: { type: 'object', properties: {} },
    execute: async () => {
      const [qdrantRes, ollamaRes, omlxRes] = await Promise.all([
        httpReq(`${QDRANT}/collections/${COLLECTION}`),
        httpReq(`${OLLAMA}/api/tags`),
        httpReq(`${OMLX}/v1/models`),
      ]);
      const ollamaModels = ollamaRes.ok ? (ollamaRes.body?.models ?? []).map(m => m.name) : [];
      const omlxModels   = omlxRes.ok  ? (omlxRes.body?.data   ?? []).map(m => m.id)    : [];
      const total        = embedCacheHits + embedCacheMisses;
      return jsonResult({
        version: '9.5.0',
        qdrant: {
          ok:         qdrantRes.ok,
          collection: COLLECTION,
          points:     qdrantRes.body?.result?.points_count ?? 0,
        },
        models: {
          embed:   { service: 'Ollama', model: EMBED_MODEL, ok: ollamaRes.ok, available: ollamaModels },
          extract: { service: 'omlx',   model: OMLX_MODEL,  ok: omlxRes.ok,  available: omlxModels },
        },
        embed_cache: {
          size: embedCache.size, capacity: EMBED_CACHE_SIZE,
          hits: embedCacheHits, misses: embedCacheMisses,
          hit_rate: total ? `${Math.round(embedCacheHits / total * 100)}%` : 'n/a',
        },
        quality_threshold: MIN_QUALITY_SCORE,
        stale_pruning:     `hit_count=0 + age>${STALE_AGE_DAYS}天 + importance=low`,
        backup:            { dir: BACKUP_DIR, last_backup: lastBackupTime ?? '未备份' },
        active_sessions:   sessionTurns.size,
        features: {
          extract_model:   `omlx ${OMLX_MODEL}（4s/次，thinking关闭）`,
          distill_model:   `deepseek-chat（云端，omlx备用）`,
          conflict_detect: `开启（agent_end+atlas_store，medium+重要性触发）`,
          quality_filter:  `≥${MIN_QUALITY_SCORE}/10`,
          memory_types:    'preference|fact|skill|project|constraint|event|[distilled]',
          time_decay:      `${DECAY_PERIOD_DAYS}天半衰期，最大惩罚${DECAY_MAX_PENALTY * 100}%`,
          feedback:        `正反馈+${FEEDBACK_BOOST}，负反馈-${FEEDBACK_DECAY}，删除门槛${FEEDBACK_DELETE_FLOOR}`,
          versioning:      '冲突替换保留历史（status:superseded），不物理删除',
          auto_distill:    `EVOLVE 24h 扫描，同标签≥${DISTILL_MIN_COUNT}条自动提炼通则`,
        },
        obsidian_bridge: {
          enabled:     Boolean(OBSIDIAN_VAULT),
          vault:       OBSIDIAN_VAULT || '未配置（设置 ATLAS_OBSIDIAN_VAULT 环境变量）',
          mirror_dir:  OBSIDIAN_VAULT ? join(OBSIDIAN_VAULT, OBSIDIAN_MIRROR_DIR) : null,
          export_interval: `每 ${MIRROR_EXPORT_INTERVAL / 3600000}h 自动刷新`,
          features:    '主题聚类导出 · 每日进化日志 · Dataview 仪表盘 · 图谱 wikilinks',
        },
      });
    },
  }));

  // atlas_evolve
  api.registerTool(() => ({
    name: 'atlas_evolve',
    description: '手动触发记忆进化：相似度去重（≥0.92）+ 过期记忆清理（无访问+90天+低重要性）。',
    parameters: { type: 'object', properties: {} },
    execute: async () => {
      try {
        const result = await runEvolution(logger);
        return jsonResult({ ok: true, ...result });
      } catch (e) {
        return jsonResult({ error: e.message });
      }
    },
  }));

  // atlas_organize（Phase 3）
  api.registerTool(() => ({
    name: 'atlas_organize',
    description: '手动触发整理Agent：将L0原料晋升为L1知识，自动域归类，写入Obsidian L1文件。每次最多处理20条。',
    parameters: { type: 'object', properties: {} },
    execute: async () => {
      try {
        if (agentLocks.get('organize')) return jsonResult({ ok: false, reason: '整理Agent正在运行，请稍后重试' });
        const result = await new Promise((resolve, reject) => {
          runAgent('organize', () => runOrganizeAgent(logger)).then(resolve).catch(reject);
        });
        return jsonResult({ ok: true, ...(result ?? {}) });
      } catch (e) {
        return jsonResult({ error: e.message });
      }
    },
  }));

  // atlas_domain_detect（Phase 4）
  api.registerTool(() => ({
    name: 'atlas_domain_detect',
    description: '手动触发域检测Agent：对domain=null的未分类记录做向量聚类，自动推断新域名（DeepSeek），创建Obsidian目录+维度图谱，更新Qdrant域字段。',
    parameters: { type: 'object', properties: {} },
    execute: async () => {
      try {
        if (agentLocks.get('domain')) return jsonResult({ ok: false, reason: '域检测Agent正在运行，请稍后重试' });
        const result = await new Promise((resolve, reject) => {
          runAgent('domain', () => runDomainDetectAgent(logger)).then(resolve).catch(reject);
        });
        return jsonResult({ ok: true, ...(result ?? {}) });
      } catch (e) {
        return jsonResult({ error: e.message });
      }
    },
  }));

  // atlas_associate（Phase 5）
  api.registerTool(() => ({
    name: 'atlas_associate',
    description: '手动触发关联Agent：扫描新增L1节点，跨域碰撞生成L2洞见，写入两个域的L2-关联/目录，追加wikilinks到L1源文件。',
    parameters: { type: 'object', properties: {} },
    execute: async () => {
      try {
        if (agentLocks.get('associate')) return jsonResult({ ok: false, reason: '关联Agent正在运行，请稍后重试' });
        const result = await new Promise((resolve, reject) => {
          runAgent('associate', () => runAssociateAgent(logger)).then(resolve).catch(reject);
        });
        return jsonResult({ ok: true, ...(result ?? {}) });
      } catch (e) {
        return jsonResult({ error: e.message });
      }
    },
  }));

  // atlas_web_learn（分块学习）
  api.registerTool(() => ({
    name: 'atlas_web_learn',
    description: '从 URL 或文本中学习并提取知识存入记忆库。长文章自动分块（≤5块×1500字）。',
    parameters: {
      type: 'object', required: [],
      properties: {
        url:       { type: 'string',  description: '网页 URL（http/https）' },
        text:      { type: 'string',  description: '直接提供的文本内容（与 url 二选一）' },
        query:     { type: 'string',  description: '主题方向描述（可选）' },
        max_facts: { type: 'integer', default: 5, minimum: 1, maximum: 10 },
      },
    },
    execute: async (_callId, params) => {
      const { url, text: rawText, query = '', max_facts = 5 } = params ?? {};
      let content = '';
      if (url) {
        const fetched = await fetchUrlText(url);
        if (!fetched.ok) return jsonResult({ error: `抓取失败: ${fetched.error ?? '未知'}`, url });
        content = fetched.contentType?.includes('html') ? htmlToText(fetched.text) : fetched.text;
        if (content.length < 100) return jsonResult({ error: '页面内容过短', url });
      } else if (rawText) {
        content = rawText;
      } else {
        return jsonResult({ error: '请提供 url 或 text 参数' });
      }

      const chunks   = chunkText(content).slice(0, MAX_CHUNKS);
      const allFacts = [];
      const sys      = '你是知识提取助手。严格只输出有效JSON数组，不要解释。';
      for (let i = 0; i < chunks.length; i++) {
        const chunkQuery = query || url || `内容 ${i + 1}/${chunks.length}`;
        const user =
          `从以下网页内容提取最多 ${max_facts} 条有价值的知识（质量<7不提取）。
主题：${chunkQuery.slice(0, 100)}
格式：[{"content":"...","category":"learning|work|project|system","importance":"low|medium|high|critical","tags":[],"quality":7,"memory_type":"fact|skill|constraint"}]

内容（${i + 1}/${chunks.length}）：
${chunks[i]}

JSON数组：`;
        const out = await omlxGenerate(sys, user, 1000);
        if (out) {
          const facts = parseFactsJson(out);
          allFacts.push(...facts.filter(f => (f.quality ?? 10) >= MIN_QUALITY_SCORE));
        }
      }

      if (!allFacts.length) return jsonResult({ ok: true, stored: 0, message: '未提取到高质量知识', chunks: chunks.length });

      const hostname = url ? (() => { try { return new URL(url).hostname; } catch { return ''; } })() : '';
      const facts    = allFacts.map(f => ({ ...f, tags: [...(f.tags ?? []), ...(hostname ? [hostname] : [])] }));
      const r        = await batchStoreMemories(facts, url ? `web-learn:${url}` : 'web-learn:manual', undefined, false);
      return jsonResult({ ok: true, url: url ?? null, chunks: chunks.length, extracted: allFacts.length, stored: r.stored, deduplicated: r.deduplicated });
    },
  }));

  // ★ atlas_merge — 近重复智能合并
  api.registerTool(() => ({
    name: 'atlas_merge',
    description:
      '扫描记忆库中相似度在 0.75-0.92 的近重复条目，用 Qwen3.5 合并成更丰富的单条记忆。' +
      '提升记忆质量，减少冗余碎片。',
    parameters: {
      type: 'object', properties: {
        query:      { type: 'string',  description: '指定合并主题范围（可选，默认全库）' },
        min_score:  { type: 'number',  default: 0.78, minimum: 0.70, maximum: 0.91 },
        max_merges: { type: 'integer', default: 10,   minimum: 1,    maximum: 50  },
      },
    },
    execute: async (_callId, params) => {
      const { query, min_score = 0.78, max_merges = 10 } = params ?? {};

      // 获取候选点
      let candidates = [];
      if (query) {
        const vector = await embed(query);
        if (!vector) return jsonResult({ error: 'embed 失败' });
        candidates = await qdrantSearch(vector, { limit: 100, minScore: 0.65 });
      } else {
        let offset = null;
        do {
          const body = { limit: 250, with_payload: true, with_vector: true };
          if (offset != null) body.offset = offset;
          const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
          if (!r.ok) break;
          candidates.push(...(r.body?.result?.points ?? []).map(p => ({ ...p, score: 1.0 })));
          offset = r.body?.result?.next_page_offset ?? null;
        } while (offset != null);
      }

      const processed = new Set();
      const mergeOps  = [];

      for (const pt of candidates) {
        if (processed.has(pt.id) || !pt.vector) continue;
        const similar   = await qdrantSearch(pt.vector, { limit: 5, minScore: min_score });
        const toMerge   = similar.filter(s => s.id !== pt.id && s.score < SCORE_DEDUP && !processed.has(s.id));
        if (!toMerge.length) continue;

        const all     = [pt, ...toMerge];
        const sys     = '你是记忆合并专家。将多条相关记忆合并为一条更完整的记忆。严格只输出JSON对象。';
        const content = all.map((m, i) => `${i + 1}. ${m.payload?.content ?? ''}`).join('\n');
        const user    =
          `将以下相关记忆合并为一条更丰富、更完整的记忆：
${content}

输出JSON：{"content":"合并后的完整内容（保留所有关键信息）","category":"...","importance":"...","tags":["..."]}`;
        const out = await omlxGenerate(sys, user, 400);
        if (!out) continue;
        const merged = parseJsonObject(out);
        if (!merged?.content) continue;

        all.forEach(m => processed.add(m.id));
        mergeOps.push({ ids: all.map(m => m.id), merged });
        if (mergeOps.length >= max_merges) break;
      }

      // 执行合并
      let mergedCount  = 0;
      let idsRemoved   = 0;
      for (const op of mergeOps) {
        await qdrantDelete(op.ids);
        idsRemoved += op.ids.length;
        const vec = await embed(op.merged.content);
        if (!vec) continue;
        const now = new Date().toISOString();
        await httpReq(`${QDRANT}/collections/${COLLECTION}/points?wait=true`, 'PUT', {
          points: [{
            id:      stableId(op.merged.content + now),
            vector:  vec,
            payload: {
              ...op.merged,
              tags:             Array.isArray(op.merged.tags) ? op.merged.tags : [],
              memory_type:      op.merged.memory_type ?? 'fact',
              created_at:       now,
              source:           'atlas_merge',
              hit_count:        0,
              last_accessed_at: null,
            },
          }],
        });
        mergedCount++;
      }

      if (mergedCount > 0) {
        appendEvolutionLog('MERGE', `合并 ${mergedCount} 组 → 清理 ${idsRemoved} 条，净减少 ${idsRemoved - mergedCount} 条`).catch(() => {});
      }
      return jsonResult({ ok: true, merged_groups: mergedCount, ids_removed: idsRemoved, net_reduction: idsRemoved - mergedCount });
    },
  }));

  // atlas_export
  api.registerTool(() => ({
    name: 'atlas_export',
    description: '将记忆库导出为 JSON 文件（含向量），用于备份或迁移。默认保存至 ~/.atlas-backups/。',
    parameters: { type: 'object', properties: { path: { type: 'string', description: '自定义导出路径（可选）' } } },
    execute: async (_callId, params) => {
      try { return jsonResult(await backupCollection(logger, params?.path)); }
      catch (e) { return jsonResult({ error: e.message }); }
    },
  }));

  // atlas_import
  api.registerTool(() => ({
    name: 'atlas_import',
    description: '从 JSON 备份文件恢复记忆库（atlas_export 格式，合并模式导入）。',
    parameters: { type: 'object', required: ['path'], properties: { path: { type: 'string' } } },
    execute: async (_callId, params) => {
      const { path: filePath } = params ?? {};
      if (!filePath) return jsonResult({ error: '请提供 path 参数' });
      try {
        const raw  = await readFile(filePath, 'utf8');
        const data = JSON.parse(raw);
        const pts  = data.points ?? [];
        if (!pts.length) return jsonResult({ ok: true, imported: 0, total: 0 });
        await ensureCollection();
        let imported = 0;
        for (let i = 0; i < pts.length; i += 100) {
          const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points?wait=true`, 'PUT', { points: pts.slice(i, i + 100) });
          if (r.ok) imported += Math.min(100, pts.length - i);
        }
        return jsonResult({ ok: true, imported, total: pts.length, file: filePath });
      } catch (e) {
        return jsonResult({ error: e.message });
      }
    },
  }));

  // ★ atlas_obsidian_sync — Obsidian Bridge 手动同步
  api.registerTool(() => ({
    name: 'atlas_obsidian_sync',
    description:
      '手动触发 Obsidian Bridge 全量同步：①按 memory_type+主标签重建聚类文件（全量覆写）；' +
      '②刷新 _index.md 仪表盘；③写入本次同步进化日志。' +
      '需配置环境变量 ATLAS_OBSIDIAN_VAULT=/path/to/vault。',
    parameters: {
      type: 'object',
      properties: {
        export_only: { type: 'boolean', description: '只重建聚类文件，不刷新仪表盘', default: false },
      },
    },
    execute: async (_callId, params) => {
      if (!OBSIDIAN_VAULT) {
        return jsonResult({
          error: 'ATLAS_OBSIDIAN_VAULT 环境变量未配置',
          hint:  '在 OpenClaw 配置或系统环境中设置 ATLAS_OBSIDIAN_VAULT=/path/to/your/obsidian/vault',
        });
      }
      const { export_only = false } = params ?? {};
      try {
        const exportResult = await runMirrorExport(logger);
        if (!export_only) await writeIndexDashboard();
        await appendEvolutionLog(
          'SYNC',
          `手动同步完成：${exportResult.clusters} 个主题聚类（${exportResult.total} 条记忆）→ ${exportResult.dir}`,
        );
        return jsonResult({
          ok:           true,
          vault:        OBSIDIAN_VAULT,
          mirror_dir:   exportResult.dir,
          clusters:     exportResult.clusters,
          total:        exportResult.total,
          files_written: exportResult.written,
          dashboard:    !export_only,
        });
      } catch (e) {
        return jsonResult({ error: e.message });
      }
    },
  }));

  // ★ atlas_feedback — 记忆反馈回路
  api.registerTool(() => ({
    name: 'atlas_feedback',
    description:
      '对刚才引用的记忆进行反馈评价。' +
      'correct=提升权重，wrong/outdated=降低权重（累计低于阈值自动删除）。' +
      '用户说"不对/你记错了/过时了"时主动调用。',
    parameters: {
      type: 'object', required: ['verdict'],
      properties: {
        query:   { type: 'string',  description: '记忆内容的关键词（用于语义定位，与 id 二选一）' },
        id:      { type: 'string',  description: '记忆 ID（从 atlas_recall 结果获取，优先使用）' },
        verdict: { type: 'string',  enum: ['correct', 'wrong', 'outdated'], description: '评价结果' },
        reason:  { type: 'string',  description: '评价原因（可选）' },
      },
    },
    execute: async (_callId, params) => {
      const { query, id, verdict, reason = '' } = params ?? {};
      if (!verdict) return jsonResult({ error: 'verdict 不能为空' });

      let targetId      = id ?? null;
      let targetContent = '';

      // 未提供 id：语义搜索，优先从最近注入的记忆中匹配
      if (!targetId && query) {
        const vector = await embed(query);
        if (vector) {
          const hits = await qdrantSearch(vector, { limit: 5, minScore: 0.6 });
          const recentHit = hits.find(h => lastInjectedIds.includes(h.id)) ?? hits[0];
          if (recentHit) { targetId = recentHit.id; targetContent = recentHit.payload?.content?.slice(0, 80) ?? ''; }
        }
      }
      if (!targetId) return jsonResult({ error: '未找到目标记忆，请提供 id 或更精确的 query' });

      // 获取当前 feedback_score
      const getR = await httpReq(`${QDRANT}/collections/${COLLECTION}/points`, 'POST', {
        ids: [targetId], with_payload: true, with_vector: false,
      });
      if (!getR.ok || !getR.body?.result?.[0]) return jsonResult({ error: '记忆不存在或已删除' });

      const current      = getR.body.result[0];
      const currentScore = current.payload?.feedback_score ?? 1.0;
      targetContent      = targetContent || current.payload?.content?.slice(0, 80) || '';

      const delta    = verdict === 'correct' ? FEEDBACK_BOOST : -FEEDBACK_DECAY;
      const newScore = Math.max(0, Math.min(1, currentScore + delta));

      if (newScore <= FEEDBACK_DELETE_FLOOR) {
        await qdrantDelete([targetId]);
        appendEvolutionLog('FEEDBACK', `删除（负评累积）"${targetContent}" ${reason ? `[${reason}]` : ''}`).catch(() => {});
        return jsonResult({
          ok: true, action: 'deleted',
          reason: `feedback_score ${currentScore.toFixed(2)}→${newScore.toFixed(2)} ≤ ${FEEDBACK_DELETE_FLOOR}`,
          memory: targetContent,
        });
      }

      await qdrantPatchPayload(targetId, { feedback_score: newScore });
      appendEvolutionLog('FEEDBACK', `${verdict === 'correct' ? '✓' : '✗'} "${targetContent}" score:${currentScore.toFixed(2)}→${newScore.toFixed(2)} ${reason ? `[${reason}]` : ''}`).catch(() => {});
      return jsonResult({
        ok: true, action: 'updated', verdict,
        feedback_score: { before: currentScore, after: newScore },
        memory: targetContent,
      });
    },
  }));

  // ★ atlas_distill — 知识提炼（DeepSeek 云端合成通则）
  api.registerTool(() => ({
    name: 'atlas_distill',
    description:
      '对指定标签下的多条记忆进行知识提炼，使用 DeepSeek 合成一条高质量"通则"（不足 5 条则报错）。' +
      '通则会优先注入到下次对话上下文中。',
    parameters: {
      type: 'object', required: ['tag'],
      properties: {
        tag:   { type: 'string',  description: '要提炼的标签名' },
        force: { type: 'boolean', default: false, description: '强制重新提炼（覆盖已有通则）' },
      },
    },
    execute: async (_callId, params) => {
      const { tag, force = false } = params ?? {};
      if (!tag?.trim()) return jsonResult({ error: 'tag 不能为空' });
      const result = await distillTagMemories(tag.trim(), logger, force);
      if (!result) return jsonResult({ error: 'distill 失败（DeepSeek 和 omlx 均不可用）' });
      if (result.skipped) return jsonResult({ ok: true, skipped: true, reason: result.reason });
      appendEvolutionLog('DISTILL', `手动提炼"${tag}"：${result.basis}条 → 通则 (id:${result.id?.slice(0, 8)})`).catch(() => {});
      return jsonResult({ ok: true, tag, ...result });
    },
  }));

  // ★ atlas_timeline — 主题时间线
  api.registerTool(() => ({
    name: 'atlas_timeline',
    description: '按时间线查看某标签下所有记忆的演进（创建时间排序）。用于追踪话题知识演进史。',
    parameters: {
      type: 'object', required: ['tag'],
      properties: {
        tag:   { type: 'string',  description: '标签名' },
        limit: { type: 'integer', default: 20, minimum: 1, maximum: 100 },
        order: { type: 'string',  enum: ['asc', 'desc'], default: 'desc', description: 'desc=最新在前' },
      },
    },
    execute: async (_callId, params) => {
      const { tag, limit = 20, order = 'desc' } = params ?? {};
      if (!tag?.trim()) return jsonResult({ error: 'tag 不能为空' });

      let offset = null;
      const allPoints = [];
      do {
        const body = {
          limit: 100, with_payload: true, with_vector: false,
          filter: {
            must:     [{ key: 'tags', match: { value: tag.trim() } }],
            must_not: [{ key: 'status', match: { value: 'superseded' } }],
          },
        };
        if (offset != null) body.offset = offset;
        const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/scroll`, 'POST', body);
        if (!r.ok) break;
        allPoints.push(...(r.body?.result?.points ?? []));
        offset = r.body?.result?.next_page_offset ?? null;
      } while (offset != null && allPoints.length < 500);

      if (!allPoints.length) return jsonResult({ tag, count: 0, timeline: [] });

      const sorted = allPoints
        .sort((a, b) => {
          const ta = new Date(a.payload?.created_at ?? 0).getTime();
          const tb = new Date(b.payload?.created_at ?? 0).getTime();
          return order === 'desc' ? tb - ta : ta - tb;
        })
        .slice(0, limit);

      return jsonResult({
        tag,
        total:    allPoints.length,
        showing:  sorted.length,
        timeline: sorted.map(h => ({
          id:           h.id,
          date:         (h.payload?.created_at ?? '').slice(0, 10),
          content:      h.payload?.content,
          importance:   h.payload?.importance,
          memory_type:  h.payload?.memory_type,
          hit_count:    h.payload?.hit_count ?? 0,
          feedback_score: h.payload?.feedback_score ?? 1.0,
          is_distilled: (h.payload?.tags ?? []).includes(DISTILL_TAG),
        })),
      });
    },
  }));
}
