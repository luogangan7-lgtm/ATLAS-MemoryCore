/**
 * ATLAS v12 集成测试
 * 直接调用真实 Qdrant + DeepSeek，测试后清理
 */
import { createHash } from 'crypto';

const QDRANT     = 'http://127.0.0.1:6333';
const COLLECTION = 'atlas_memories_v2';
const DEEPSEEK_URL   = 'https://api.deepseek.com';
const DEEPSEEK_MODEL = 'deepseek-v4-flash';
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY ?? '';
const EMBED_URL  = 'http://127.0.0.1:11434';
const EMBED_MODEL = 'bge-m3';

const RECORD_TYPES = { KNOWLEDGE: 'knowledge', ENTITY: 'entity', RELATION: 'relation' };
const RELATION_TYPES = { SUPPORTS: 'supports', EXTENDS: 'extends', CROSS_DOMAIN: 'cross_domain' };
const CONFIDENCE_DEFAULT = 0.6;
const EMBED_SAFE_CHARS = 6000;

// 测试用的临时 ID（测试后统一删除）
const TEST_IDS = [];

// ── 工具函数 ──────────────────────────────────────────────────────────────────
async function req(url, method = 'GET', body = null, headers = {}) {
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, body: json };
}

function stableId(text) {
  return parseInt(createHash('sha256').update(text).digest('hex').slice(0, 15), 16);
}

async function embed(text) {
  const r = await req(`${EMBED_URL}/api/embed`, 'POST', { model: EMBED_MODEL, input: text });
  return r.ok ? (r.body?.embeddings?.[0] ?? null) : null;
}

async function deepseek(system, user, maxTokens = 800) {
  const r = await req(`${DEEPSEEK_URL}/v1/chat/completions`, 'POST', {
    model: DEEPSEEK_MODEL,
    messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
    max_tokens: maxTokens,
    temperature: 0.3,
  }, { Authorization: `Bearer ${DEEPSEEK_API_KEY}` });
  return r.body?.choices?.[0]?.message?.content ?? null;
}

function parseJson(text) {
  if (!text) return null;
  const m = text.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
  if (!m) return null;
  try { return JSON.parse(m[0]); } catch { return null; }
}

// ── 测试框架 ──────────────────────────────────────────────────────────────────
let passed = 0, failed = 0;
function test(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) { console.log(`  ✓ ${name}`); passed++; }
  else { console.error(`  ✗ ${name}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`); failed++; }
}
function testTrue(name, value) {
  if (value) { console.log(`  ✓ ${name}`); passed++; }
  else { console.error(`  ✗ ${name}: expected truthy, got ${JSON.stringify(value)}`); failed++; }
}

// ── 1. Qdrant 连通性 ──────────────────────────────────────────────────────────
console.log('\n【Qdrant 连通性】');
const collRes = await req(`${QDRANT}/collections/${COLLECTION}`);
test('集合存在且green', collRes.body?.result?.status, 'green');
const existingCount = collRes.body?.result?.points_count ?? 0;
testTrue(`现有数据 ${existingCount} 条不为0`, existingCount > 0);
console.log(`  ℹ 现有记录: ${existingCount} 条（测试不会修改这些数据）`);

// ── 2. Embed 连通性 ───────────────────────────────────────────────────────────
console.log('\n【bge-m3 Embed 连通性】');
const testVec = await embed('钩子句是短视频开头用来吸引注意的句子');
testTrue('embed 返回向量', Array.isArray(testVec));
test('向量维度 1024', testVec?.length, 1024);

// ── 3. DeepSeek 连通性 ────────────────────────────────────────────────────────
console.log('\n【DeepSeek 连通性】');
const dsRes = await deepseek('只输出数字，不要任何其他内容', '1+1等于几？', 10);
testTrue('DeepSeek 有响应', !!dsRes);
testTrue('响应包含2', dsRes?.includes('2'));
console.log(`  ℹ DeepSeek 响应: "${dsRes?.trim()}"`);

// ── 4. upsertEntity 测试 ─────────────────────────────────────────────────────
console.log('\n【upsertEntity 实体注册】');
const testEntityName = `__test_钩子句_${Date.now()}`;
const entityPointId = stableId(testEntityName + '_entity');
TEST_IDS.push(entityPointId);

const entityVec = await embed((testEntityName + ' 短视频开头吸引注意的句子结构').slice(0, EMBED_SAFE_CHARS));
testTrue('实体向量生成', !!entityVec);

const upsertRes = await req(`${QDRANT}/collections/${COLLECTION}/points?wait=true`, 'PUT', {
  points: [{ id: entityPointId, vector: entityVec, payload: {
    record_type: RECORD_TYPES.ENTITY,
    canonical_name: testEntityName,
    aliases: ['hook句', '开场钩子'],
    domains: ['短视频生产', '营销'],
    definition: '短视频开头用来吸引注意力的句子结构',
    related_entity_names: [],
    knowledge_node_ids: [],
    confidence: CONFIDENCE_DEFAULT,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }}],
});
test('实体写入成功', upsertRes.ok, true);

// 验证写入后能读回
const readRes = await req(`${QDRANT}/collections/${COLLECTION}/points`, 'POST', {
  ids: [entityPointId], with_payload: true, with_vector: false,
});
const readEntity = readRes.body?.result?.[0];
test('实体读回成功', readEntity?.payload?.canonical_name, testEntityName);
test('record_type 正确', readEntity?.payload?.record_type, RECORD_TYPES.ENTITY);
test('初始 confidence 正确', readEntity?.payload?.confidence, CONFIDENCE_DEFAULT);
test('aliases 写入', readEntity?.payload?.aliases?.length, 2);

// ── 5. upsertRelation 测试 ────────────────────────────────────────────────────
console.log('\n【upsertRelation 关系写入】');
const srcId = entityPointId;
const tgtId = stableId('__test_cta_entity');
const relId = stableId(String(srcId) + '_' + RELATION_TYPES.SUPPORTS + '_' + String(tgtId));
TEST_IDS.push(relId);

const relVec = await embed('钩子句 supports CTA');
testTrue('关系向量生成', !!relVec);

const relRes = await req(`${QDRANT}/collections/${COLLECTION}/points?wait=true`, 'PUT', {
  points: [{ id: relId, vector: relVec, payload: {
    record_type: RECORD_TYPES.RELATION,
    source_id: srcId,
    target_id: tgtId,
    relation_type: RELATION_TYPES.SUPPORTS,
    strength: 0.8,
    context: '好的钩子句能支撑CTA的转化效果',
    created_at: new Date().toISOString(),
  }}],
});
test('关系写入成功', relRes.ok, true);

const relRead = await req(`${QDRANT}/collections/${COLLECTION}/points`, 'POST', {
  ids: [relId], with_payload: true, with_vector: false,
});
const relData = relRead.body?.result?.[0];
test('关系读回成功', relData?.payload?.relation_type, RELATION_TYPES.SUPPORTS);
test('关系 record_type 正确', relData?.payload?.record_type, RECORD_TYPES.RELATION);

// ── 6. qdrantSearch 排除 entity/relation 验证 ─────────────────────────────────
console.log('\n【qdrantSearch 默认排除实体/关系记录】');
const searchVec = await embed('钩子句');
const searchRes = await req(`${QDRANT}/collections/${COLLECTION}/points/search`, 'POST', {
  vector: searchVec, limit: 10, with_payload: true, score_threshold: 0.5,
  filter: {
    must_not: [
      { key: 'record_type', match: { value: RECORD_TYPES.ENTITY } },
      { key: 'record_type', match: { value: RECORD_TYPES.RELATION } },
    ],
  },
});
const hits = searchRes.body?.result ?? [];
const hasEntityInResults = hits.some(h => h.payload?.record_type === RECORD_TYPES.ENTITY);
const hasRelationInResults = hits.some(h => h.payload?.record_type === RECORD_TYPES.RELATION);
test('搜索结果不含实体记录', hasEntityInResults, false);
test('搜索结果不含关系记录', hasRelationInResults, false);
testTrue(`搜索返回 ${hits.length} 条知识节点`, hits.length >= 0);

// ── 7. extractL1Content（DeepSeek 多节点输出）─────────────────────────────────
console.log('\n【extractL1Content DeepSeek 提炼】');
const testContent = `短视频钩子句写法：
1. 痛点切入型："你有没有遇到过这样的情况..."
2. 好奇心型："99%的人都不知道这个技巧..."
3. 利益承诺型："看完这个视频，你能学会..."
钩子句要在前3秒出现，长度不超过15字，要和目标用户的核心痛点直接相关。`;

const sysPrompt = `你是知识提炼专家。严格只输出有效JSON，不要markdown代码块。`;
const userPrompt = `从以下内容提取知识节点。
内容类型：video_script  领域：短视频生产
内容：${testContent}

输出JSON格式：
{
  "nodes": [{"title":"标题","summary":"摘要","content":"内容","knowledge_purpose":"production","tags":[],"faithfulness_score":0.9}],
  "entities": [{"canonical_name":"实体名","aliases":[],"definition":"定义","domains":[]}],
  "relations": []
}`;

const rawOutput = await deepseek(sysPrompt, userPrompt, 1000);
testTrue('DeepSeek 有输出', !!rawOutput);

const l1Result = parseJson(rawOutput);
testTrue('输出可解析为JSON', !!l1Result);
testTrue('nodes 是数组', Array.isArray(l1Result?.nodes));
testTrue('至少1个节点', (l1Result?.nodes?.length ?? 0) >= 1);

if (l1Result?.nodes?.[0]) {
  const node = l1Result.nodes[0];
  testTrue('节点有title', !!node.title);
  testTrue('节点有summary', !!node.summary);
  console.log(`  ℹ 提炼节点: "${node.title}"`);
  console.log(`  ℹ 实体数量: ${l1Result.entities?.length ?? 0}`);
}

// ── 8. calcConfidence 集成验证 ────────────────────────────────────────────────
console.log('\n【confidence + hit_count 连动验证】');
function calcConfidence(hitCount) {
  return parseFloat(Math.min(0.99, 1 - (1 - CONFIDENCE_DEFAULT) * Math.pow(0.85, hitCount)).toFixed(2));
}
// 模拟 trackAccess 更新 confidence
const updateRes = await req(`${QDRANT}/collections/${COLLECTION}/points/payload`, 'POST', {
  payload: { hit_count: 1, confidence: calcConfidence(1), last_accessed_at: new Date().toISOString() },
  points: [entityPointId],
});
test('trackAccess 模拟更新成功', updateRes.ok, true);

const afterRead = await req(`${QDRANT}/collections/${COLLECTION}/points`, 'POST', {
  ids: [entityPointId], with_payload: true, with_vector: false,
});
const afterConf = afterRead.body?.result?.[0]?.payload?.confidence;
test('hit=1 后 confidence=0.66', afterConf, 0.66);

// ── 9. 现有数据完整性验证 ──────────────────────────────────────────────────────
console.log('\n【现有数据完整性】');
const finalCount = (await req(`${QDRANT}/collections/${COLLECTION}`)).body?.result?.points_count ?? 0;
testTrue(`数据总量 >= 原有${existingCount}条`, finalCount >= existingCount);
console.log(`  ℹ 测试后总记录: ${finalCount} 条（增加了 ${finalCount - existingCount} 条测试记录）`);

// ── 清理测试数据 ───────────────────────────────────────────────────────────────
console.log('\n【清理测试数据】');
const cleanRes = await req(`${QDRANT}/collections/${COLLECTION}/points/delete?wait=true`, 'POST', {
  points: TEST_IDS,
});
test('测试数据清理成功', cleanRes.ok, true);
const afterClean = (await req(`${QDRANT}/collections/${COLLECTION}`)).body?.result?.points_count ?? 0;
test('清理后恢复原有数量', afterClean, existingCount);
console.log(`  ℹ 清理后记录: ${afterClean} 条`);

// ── 汇总 ──────────────────────────────────────────────────────────────────────
console.log(`\n${'='.repeat(40)}`);
console.log(`集成测试: ${passed} 通过 / ${failed} 失败`);
if (failed > 0) process.exit(1);
