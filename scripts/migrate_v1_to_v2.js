#!/usr/bin/env node
/**
 * migrate_v1_to_v2.js
 * 迁移 atlas_memories → atlas_memories_v2
 * 不修改源集合，只读取后写入新集合
 */

const QDRANT      = 'http://localhost:6333';
const SOURCE_COLL = 'atlas_memories';
const TARGET_COLL = 'atlas_memories_v2';
const VECTOR_DIM  = 1024;

const TTL_MAP = {
  trading:       5 * 60,
  news:          3 * 24 * 3600,
  social:        7 * 24 * 3600,
  chat:          7 * 24 * 3600,
  platform_rule: 90 * 24 * 3600,
  course:        null,
  process:       null,
  unknown:       30 * 24 * 3600,
};

function inferSourceType(pt) {
  const { domain = '', tags = [], content = '', source = '' } = pt.payload ?? {};
  const text = (content + ' ' + tags.join(' ')).toLowerCase();

  if (domain === 'OKX交易') return 'trading';
  if (['战略', '情感学', '故事沟通术', 'Play连招', '关系缔造论',
       '预期式求爱', '破局', '散讲合集', '营销', '品牌项目',
       'TikTok运营', '五金工具-电焊机', '储能电池'].includes(domain)) return 'course';

  if (source.includes('web-learn')) return 'news';
  if (source.includes('distill'))   return 'course';

  if (content.includes('> ') && content.includes('####')) return 'course';
  if (/算法|完播率|推流|违禁词/.test(text))              return 'platform_rule';
  if (/步骤\d|第[一二三]步|\bsop\b/.test(text))          return 'process';
  if (/模板|话术|怎么回|聊天技巧/.test(text))            return 'chat';
  if (/脚本|钩子|爆款|标题公式/.test(text))              return 'social';

  return 'course'; // 现有数据默认课程知识
}

function inferKnowledgePurpose(pt, sourceType) {
  const { content = '' } = pt.payload ?? {};
  if (sourceType === 'process') return 'process';
  if (/模板|公式|钩子|话术|脚本框架/.test(content)) return 'production';
  return 'understanding';
}

function calcExpiry(sourceType, createdAt) {
  const ttlSecs = TTL_MAP[sourceType];
  if (ttlSecs === null || ttlSecs === undefined) return null;
  const base = createdAt ? new Date(createdAt).getTime() : Date.now();
  return new Date(base + ttlSecs * 1000).toISOString();
}

async function req(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  const json = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, body: json };
}

async function ensureTarget() {
  const check = await req(`${QDRANT}/collections/${TARGET_COLL}`);
  if (check.ok) {
    console.log(`集合 ${TARGET_COLL} 已存在`);
    return;
  }
  const cr = await req(`${QDRANT}/collections/${TARGET_COLL}`, 'PUT', {
    vectors:           { size: VECTOR_DIM, distance: 'Cosine' },
    on_disk_payload:   true,
    optimizers_config: { memmap_threshold: 20000 },
  });
  if (!cr.ok) throw new Error(`创建集合失败: ${JSON.stringify(cr.body)}`);
  console.log(`集合 ${TARGET_COLL} 创建成功`);

  const indexDefs = [
    { field_name: 'source_type',       field_schema: 'keyword' },
    { field_name: 'knowledge_purpose', field_schema: 'keyword' },
    { field_name: 'platform',          field_schema: 'keyword' },
    { field_name: 'expires_at',        field_schema: 'datetime' },
    { field_name: 'domain',            field_schema: 'keyword' },
    { field_name: 'level',             field_schema: 'integer' },
    { field_name: 'status',            field_schema: 'keyword' },
  ];
  await Promise.allSettled(indexDefs.map(d =>
    req(`${QDRANT}/collections/${TARGET_COLL}/index`, 'PUT', d)
  ));
  console.log('Payload 索引创建完成');
}

async function scrollAll() {
  const all = [];
  let offset = null;
  do {
    const body = { limit: 100, with_payload: true, with_vector: true };
    if (offset != null) body.offset = offset;
    const r = await req(`${QDRANT}/collections/${SOURCE_COLL}/points/scroll`, 'POST', body);
    if (!r.ok) throw new Error(`读取源集合失败: ${JSON.stringify(r.body)}`);
    all.push(...(r.body?.result?.points ?? []));
    offset = r.body?.result?.next_page_offset ?? null;
    process.stdout.write(`\r  已读取 ${all.length} 条...`);
  } while (offset != null);
  console.log('');
  return all;
}

async function upsertBatch(points) {
  const r = await req(`${QDRANT}/collections/${TARGET_COLL}/points?wait=true`, 'PUT', { points });
  if (!r.ok) throw new Error(`写入失败: ${JSON.stringify(r.body)}`);
}

async function main() {
  console.log('=== ATLAS v1 → v2 迁移 ===\n');

  await ensureTarget();

  console.log(`\n读取 ${SOURCE_COLL}...`);
  const v1 = await scrollAll();
  console.log(`共 ${v1.length} 条\n`);

  const dist = {};
  let migrated = 0, skipped = 0, alreadyExpired = 0;
  const BATCH = 20;
  const batch = [];

  for (const pt of v1) {
    if (!pt.vector) { skipped++; continue; }

    const st = inferSourceType(pt);
    const kp = inferKnowledgePurpose(pt, st);
    const ex = calcExpiry(st, pt.payload?.created_at);

    dist[st] = (dist[st] ?? 0) + 1;

    if (ex && new Date(ex) < new Date()) {
      alreadyExpired++;
      console.log(`  [已过期] id=${pt.id} type=${st} expires=${ex}`);
    }

    batch.push({
      id:      pt.id,
      vector:  pt.vector,
      payload: {
        ...pt.payload,
        source_type:       st,
        knowledge_purpose: kp,
        expires_at:        ex,
        platform:          null,
        migrated_from:     'atlas_memories',
        migrated_at:       new Date().toISOString(),
      },
    });

    if (batch.length >= BATCH) {
      await upsertBatch([...batch]);
      migrated += batch.length;
      batch.length = 0;
      process.stdout.write(`\r  已迁移 ${migrated}/${v1.length - skipped} 条`);
    }
  }

  if (batch.length > 0) {
    await upsertBatch([...batch]);
    migrated += batch.length;
  }
  console.log('');

  const verify = await req(`${QDRANT}/collections/${TARGET_COLL}`);
  const targetCount = verify.body?.result?.points_count ?? '?';

  console.log('\n=== 完成 ===');
  console.log(`源集合: ${v1.length} 条`);
  console.log(`已迁移: ${migrated} 条`);
  console.log(`跳过(无向量): ${skipped} 条`);
  console.log(`已过期记录: ${alreadyExpired} 条（已迁移，TTL扫描器会处理）`);
  console.log(`目标集合验证: ${targetCount} 条`);

  console.log('\nsource_type 分布:');
  for (const [k, v] of Object.entries(dist).sort((a, b) => b[1] - a[1]))
    console.log(`  ${k.padEnd(15)}: ${v} 条`);
}

main().catch(e => { console.error('\n迁移失败:', e.message); process.exit(1); });
