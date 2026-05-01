/**
 * ATLAS Memory v9.4.0 — Commercial-Grade Semantic Memory + Obsidian Bridge
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
 */

import http from 'http';
import https from 'https';
import { createHash } from 'crypto';
import { writeFile, readFile, mkdir, appendFile } from 'fs/promises';
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

// ── Obsidian Bridge 常量 ───────────────────────────────────────────────────────
const OBSIDIAN_VAULT         = process.env.ATLAS_OBSIDIAN_VAULT ?? '';
const OBSIDIAN_MIRROR_DIR    = 'Atlas_Mirror';
const EVOLUTION_LOG_SUBDIR   = '_evolution';
const MIRROR_LINK_MAX        = 5;
const MIRROR_EXPORT_INTERVAL = 6 * 60 * 60 * 1000;
const IMPORTANCE_ORDER       = { critical: 4, high: 3, medium: 2, low: 1 };

// ── 运行时状态 ─────────────────────────────────────────────────────────────────
const embedCache     = new Map();
let embedCacheHits   = 0;
let embedCacheMisses = 0;
const sessionTurns   = new Map();
let lastInjectKey    = '';
let lastInjectResult = undefined;
let lastBackupTime   = null;

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
async function omlxGenerate(systemMsg, userMsg, maxTokens = 800) {
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
    EXTRACT_TIMEOUT_MS,
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
  if (category && category !== 'any') {
    body.filter = { must: [{ key: 'category', match: { value: category } }] };
  }
  const r = await httpReq(`${QDRANT}/collections/${COLLECTION}/points/search`, 'POST', body);
  return r.ok ? (r.body?.result ?? []) : [];
}

async function qdrantDelete(ids) {
  if (!ids.length) return { ok: true, deleted: 0 };
  const r = await httpReq(
    `${QDRANT}/collections/${COLLECTION}/points/delete?wait=true`, 'POST', { points: ids },
  );
  return { ok: r.ok, deleted: ids.length };
}

function fmtHits(hits) {
  return hits.map(h => ({
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
  const lines = hits.map(h => {
    const imp  = h.payload?.importance ?? 'medium';
    const type = h.payload?.memory_type ? `[${h.payload.memory_type}]` : '';
    const text = h.payload?.content ?? '';
    return `• [${imp}]${type} ${text}`;
  });
  return `<atlas_memory>\n以下是与当前对话相关的历史记忆（ATLAS Memory 自动检索）：\n${lines.join('\n')}\n</atlas_memory>`;
}

// ── ★ 带冲突检测的存储 ────────────────────────────────────────────────────────
async function storeWithConflict({ content, category = 'work', importance = 'medium', tags = [], memory_type = 'fact', source = 'manual', sessionKey, doConflictCheck = false }) {
  const vector = await embed(content);
  if (!vector) return { ok: false, error: 'Ollama embed 不可用' };

  // 精确去重
  const exactDup = await qdrantSearch(vector, { limit: 1, minScore: SCORE_DEDUP });
  if (exactDup.length) return { ok: true, deduplicated: true, similar: exactDup[0].payload?.content?.slice(0, 80) };

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
          await qdrantDelete([conflictId]);
        } else if (res.action === 'merge' && res.merged_content?.trim() && conflictId) {
          await qdrantDelete([conflictId]);
          content = res.merged_content.trim();
        }
      }
    }
  }

  await ensureCollection();
  const now     = new Date().toISOString();
  const payload = {
    content:          content.trim(),
    category,
    importance,
    tags:             Array.isArray(tags) ? tags : [],
    memory_type,
    created_at:       now,
    source,
    session_key:      sessionKey ?? 'unknown',
    hit_count:        0,
    last_accessed_at: null,
  };
  const result = await upsert(vector, payload);
  return result.ok ? { ok: true, id: result.id } : { ok: false, error: result.error || 'Qdrant 写入失败' };
}

// ★ 向后兼容的 storeMemory（手动工具调用，启用冲突检测）
async function storeMemory(params) {
  return storeWithConflict({ ...params, doConflictCheck: true });
}

// ── ⑥ 批量存储（并行 embed + 单次 batch upsert）──────────────────────────────
async function batchStoreMemories(facts, source, sessionKey, doConflictCheck = false) {
  if (!facts.length) return { stored: 0, deduplicated: 0, skipped: 0 };
  await ensureCollection();

  const embedded = await Promise.all(
    facts.map(async f => {
      const vector = await embed(f.content);
      return vector ? { f, vector } : null;
    })
  );
  const valid = embedded.filter(Boolean);
  const points  = [];
  let deduplicated = 0;
  let skipped      = 0;

  for (const { f, vector } of valid) {
    // 精确去重
    const dup = await qdrantSearch(vector, { limit: 1, minScore: SCORE_DEDUP });
    if (dup.length) { deduplicated++; continue; }

    // ★ 冲突检测（medium+ 重要性且启用时）
    let content     = f.content.trim();
    const importance = f.importance ?? 'work';
    if (doConflictCheck && IMPORTANCE_LEVELS.indexOf(importance) >= 1) {
      const candidates = await qdrantSearch(vector, { limit: 3, minScore: SCORE_CONFLICT_MIN });
      const conflicts  = candidates.filter(c => c.score < SCORE_DEDUP);
      if (conflicts.length > 0) {
        const res = await detectConflict(content, conflicts);
        if (res?.has_conflict) {
          const cidx       = (res.conflict_index ?? 1) - 1;
          const conflictId = conflicts[Math.max(0, Math.min(cidx, conflicts.length - 1))]?.id;
          if (res.action === 'keep_old') { skipped++; continue; }
          if (res.action === 'keep_new' && conflictId) await qdrantDelete([conflictId]);
          if (res.action === 'merge' && res.merged_content?.trim() && conflictId) {
            await qdrantDelete([conflictId]);
            content = res.merged_content.trim();
          }
        }
      }
    }

    const now = new Date().toISOString();
    const id  = stableId(content + now);
    points.push({
      id, vector,
      payload: {
        content,
        category:         f.category    ?? 'work',
        importance:       f.importance  ?? 'medium',
        tags:             Array.isArray(f.tags) ? f.tags : [],
        memory_type:      f.memory_type ?? 'fact',
        created_at:       now,
        source,
        session_key:      sessionKey ?? 'unknown',
        hit_count:        0,
        last_accessed_at: null,
      },
    });
  }

  if (points.length > 0) {
    await httpReq(`${QDRANT}/collections/${COLLECTION}/points?wait=true`, 'PUT', { points });
    appendEvolutionLog('CAPTURE', `+${points.length} 条记忆（${source}，去重${deduplicated}，冲突跳过${skipped}）`).catch(() => {});
  }
  return { stored: points.length, deduplicated, skipped };
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

  // ★ 过期清理：hit_count=0 + age>90天 + importance='low'
  for (const pt of pointsWithVecs) {
    const hitCount  = pt.payload?.hit_count ?? 0;
    const imp       = pt.payload?.importance ?? 'medium';
    const created   = pt.payload?.created_at ? new Date(pt.payload.created_at).getTime() : now;
    const ageDays   = (now - created) / 86_400_000;
    if (hitCount === 0 && imp === 'low' && ageDays > STALE_AGE_DAYS) {
      toDelete.add(pt.id);
    }
  }

  // 相似度去重
  for (const pt of pointsWithVecs) {
    if (toDelete.has(pt.id) || !pt.vector) continue;
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
  logger?.info?.(`[atlas-memory] 进化完成：总数 ${allIds.length}，删除 ${toDelete.size} 条（包含过期清理）`);
  return { total: allIds.length, removed: toDelete.size };
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

// ── 工具结果格式 ──────────────────────────────────────────────────────────────
function jsonResult(payload) {
  return { content: [{ type: 'text', text: JSON.stringify(payload, null, 2) }] };
}

// ── 插件注册 ──────────────────────────────────────────────────────────────────
export const name        = 'atlas-memory';
export const description = 'ATLAS Memory v9.4.0 — 商业级语义记忆 + Obsidian Bridge（进化监控台 · 主题聚类 · 图谱融合 · 每日进化日志）';

export function register(api) {
  const logger = api.logger;

  ensureCollection().catch(() => {});
  setInterval(() => runEvolution(logger).catch(() => {}), 24 * 60 * 60 * 1000);
  setInterval(() => backupCollection(logger).catch(() => {}), 7 * 24 * 60 * 60 * 1000);

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
        const hits    = await qdrantSearch(vector, { limit: maxResults });
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
        version: '9.4.0',
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
          conflict_detect: `开启（agent_end+atlas_store，medium+重要性触发）`,
          quality_filter:  `≥${MIN_QUALITY_SCORE}/10`,
          memory_types:    'preference|fact|skill|project|constraint|event',
          time_decay:      `${DECAY_PERIOD_DAYS}天半衰期，最大惩罚${DECAY_MAX_PENALTY * 100}%`,
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
}
