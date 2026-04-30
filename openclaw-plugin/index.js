/**
 * ATLAS Memory Core v7.0.0 — OpenClaw Plugin
 * 双轨记忆系统：Qdrant 结构化知识库 + QMD 日记搜索引擎
 * 压缩后端：oMLX Qwen3.5-9B-OptiQ-4bit（本地，零云端 token）
 */
import { spawnSync, spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import http from 'http';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_PY = path.join(__dirname, 'atlas_skill.py');
const SERVER_PORT = 16334;
const PROXY_BYPASS = { NO_PROXY: 'localhost,127.0.0.1', no_proxy: 'localhost,127.0.0.1' };

// Token 预算：注入上下文最大字符数
const MAX_INJECT_CHARS = 800;

export const name = 'atlas-memory';
export const description = 'ATLAS Memory Core v7.0.0 — 双轨记忆（Qdrant + QMD）+ oMLX 压缩';

// ── 持久化 Python server 管理 ─────────────────────────────────────────────────

let _serverProc = null;
let _serverReady = false;

function _launchServer() {
  if (_serverProc) return;
  _serverProc = spawn('/opt/homebrew/bin/python3', [SKILL_PY, '--server'], {
    env: { ...process.env, ...PROXY_BYPASS },
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
  });
  _serverProc.stdout.on('data', (d) => {
    if (d.toString().includes('server ready')) _serverReady = true;
  });
  _serverProc.on('exit', () => { _serverProc = null; _serverReady = false; });
}

function _startServer() {
  if (_serverProc || _serverReady) return;
  const probe = http.request(
    { hostname: '127.0.0.1', port: SERVER_PORT, path: '/stats', method: 'GET', timeout: 2000 },
    (res) => {
      if (res.statusCode === 200) { _serverReady = true; } else { _launchServer(); }
    }
  );
  probe.on('error', _launchServer);
  probe.on('timeout', () => { probe.destroy(); _launchServer(); });
  probe.end();
}

function _callServer(cmd, args = []) {
  return new Promise((resolve) => {
    const argsParam = args.length ? '&args=' + encodeURIComponent(args.join('\x00')) : '';
    const options = {
      hostname: '127.0.0.1',
      port: SERVER_PORT,
      path: `/${cmd}?${argsParam}`,
      method: 'GET',
      timeout: 12000,
    };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch { resolve({ raw: data }); }
      });
    });
    req.on('error', (e) => resolve({ error: e.message }));
    req.on('timeout', () => { req.destroy(); resolve({ error: 'timeout' }); });
    req.end();
  });
}

function _callSubprocess(cmd, args = []) {
  const r = spawnSync('/opt/homebrew/bin/python3', [SKILL_PY, cmd, ...args], {
    encoding: 'utf-8',
    timeout: 30000,
    env: { ...process.env, ...PROXY_BYPASS },
  });
  if (r.error) return { error: r.error.message };
  try { return JSON.parse(r.stdout.trim()); } catch { return { raw: r.stdout.trim() }; }
}

async function callSkill(cmd, args = []) {
  if (_serverReady) {
    const result = await _callServer(cmd, args);
    if (!result.error) return result;
  }
  return _callSubprocess(cmd, args);
}

// ── 工具注册 ──────────────────────────────────────────────────────────────────

export function register(api) {
  _startServer();

  // memory_store：存入 Qdrant 结构化知识库
  api.registerTool(
    () => ({
      name: 'memory_store',
      description: '存储记忆到 Qdrant 语义知识库（自动向量嵌入 + 分类）',
      parameters: {
        type: 'object',
        properties: {
          text: { type: 'string', description: '要存储的记忆内容' },
          importance: { type: 'string', enum: ['low', 'medium', 'high', 'critical'] },
          category: { type: 'string', enum: ['personal', 'work', 'learning', 'project', 'system', 'conversation'] },
          tags: { type: 'string', description: '逗号分隔标签' },
        },
        required: ['text'],
      },
      execute: () => (_id, { text, importance, category, tags }) => {
        const args = [text];
        if (importance) args.push('--importance', importance);
        if (category) args.push('--category', category);
        if (tags) args.push('--tags', tags);
        return callSkill('store', args);
      },
    }),
    { names: ['memory_store'] }
  );

  // atlas_search：Qdrant 结构化知识库搜索（原 memory_search 重命名，解冲突）
  api.registerTool(
    () => ({
      name: 'atlas_search',
      description: '语义搜索结构化知识库（Qdrant：交易/客户/情报/视频等领域数据）',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: '搜索查询' },
          limit: { type: 'number', description: '返回数量，默认 5' },
          threshold: { type: 'number', description: '相似度阈值，默认 0.55' },
        },
        required: ['query'],
      },
      execute: () => (_id, { query, limit, threshold }) => {
        const args = [query];
        if (limit) args.push('-n', String(limit));
        if (threshold !== undefined) args.push('--threshold', String(threshold));
        return callSkill('search', args);
      },
    }),
    { names: ['atlas_search'] }
  );

  // atlas_dual_search：双轨搜索（Qdrant + QMD 日记合并）
  api.registerTool(
    () => ({
      name: 'atlas_dual_search',
      description: '双轨记忆搜索：同时检索 Qdrant 结构化库 + QMD 日记库，自动合并排序。用于需要同时参考结构化知识和历史对话的场景。',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: '搜索查询' },
          limit: { type: 'number', description: '每路返回数量，默认 3' },
        },
        required: ['query'],
      },
      execute: () => (_id, { query, limit }) => {
        const args = [query];
        if (limit) args.push('-n', String(limit));
        return callSkill('dual_search', args);
      },
    }),
    { names: ['atlas_dual_search'] }
  );

  // memory_stats
  api.registerTool(
    () => ({
      name: 'memory_stats',
      description: '获取 ATLAS 记忆系统统计信息（Qdrant 向量数、分类分布、压缩后端状态）',
      parameters: { type: 'object', properties: {} },
      execute: () => (_id, _p) => callSkill('stats', []),
    }),
    { names: ['memory_stats'] }
  );

  // memory_list
  api.registerTool(
    () => ({
      name: 'memory_list',
      description: '列出最近存储的 Qdrant 记忆',
      parameters: {
        type: 'object',
        properties: { limit: { type: 'number', description: '数量，默认 10' } },
      },
      execute: () => (_id, { limit } = {}) => callSkill('list', limit ? [String(limit)] : []),
    }),
    { names: ['memory_list'] }
  );

  // memory_optimize
  api.registerTool(
    () => ({
      name: 'memory_optimize',
      description: '触发记忆优化（遗忘低分记忆，升级高分记忆到 QMD）',
      parameters: {
        type: 'object',
        properties: { force: { type: 'boolean' } },
      },
      execute: () => (_id, { force } = {}) => callSkill('optimize', force ? ['--force'] : []),
    }),
    { names: ['memory_optimize'] }
  );

  // memory_compress：oMLX 本地压缩
  api.registerTool(
    () => ({
      name: 'memory_compress',
      description: '用本地 oMLX Qwen3.5-9B-OptiQ-4bit 压缩长文本，不消耗云端 token',
      parameters: {
        type: 'object',
        properties: {
          text: { type: 'string', description: '要压缩的文本' },
          ratio: { type: 'number', description: '目标压缩比例，默认 0.3' },
        },
        required: ['text'],
      },
      execute: () => (_id, { text, ratio }) => {
        const args = [text];
        if (ratio !== undefined) args.push('--ratio', String(ratio));
        return callSkill('compress', args);
      },
    }),
    { names: ['memory_compress'] }
  );

  // ── before_prompt_build：双轨自动注入相关记忆 ─────────────────────────────

  api.registerHook(
    'before_prompt_build',
    async (event) => {
      const { prompt } = event;
      if (!prompt || prompt.trim().length < 10) return;
      if (prompt.trim().startsWith('/')) return;
      if (!_serverReady) return;

      try {
        // 并行查询 Qdrant + QMD（通过 dual_search）
        const result = await _callServer('dual_search', [
          prompt.slice(0, 300), '-n', '3', '--threshold', '0.58'
        ]);

        if (!result.success || !result.results || result.results.length === 0) return;

        // 分组格式化
        const qdrantItems = result.results.filter(r => r.source === 'qdrant');
        const qmdItems = result.results.filter(r => r.source === 'qmd');

        const lines = [];
        if (qdrantItems.length > 0) {
          lines.push('### 知识库');
          for (const m of qdrantItems) {
            lines.push(`- [${m.created || ''}][${m.category || ''}] ${m.text}`);
          }
        }
        if (qmdItems.length > 0) {
          lines.push('### 日记');
          for (const m of qmdItems) {
            lines.push(`- ${m.title || ''}: ${m.text}`);
          }
        }

        let memoryBlock = lines.join('\n');

        // token 预算控制：超出 MAX_INJECT_CHARS 时用 oMLX 压缩
        if (memoryBlock.length > MAX_INJECT_CHARS) {
          const compressed = await _callServer('compress', [memoryBlock, '--ratio', '0.4']);
          if (compressed.success && compressed.compressed) {
            memoryBlock = compressed.compressed;
          } else {
            // 压缩失败则截断
            memoryBlock = memoryBlock.slice(0, MAX_INJECT_CHARS) + '...';
          }
        }

        return {
          prependContext: `## 相关记忆（ATLAS v7）\n${memoryBlock}\n`,
        };
      } catch (e) {
        // 静默失败，不影响主流程
        return;
      }
    },
    { name: 'atlas-memory-context-inject', description: '每轮对话前双轨注入相关记忆（Qdrant + QMD）' }
  );

  // ── after_agent_turn：自动捕获对话写入 Qdrant ────────────────────────────

  api.registerHook(
    'before_agent_reply',
    async (event) => {
      if (!_serverReady) return;
      try {
        // before_agent_reply event 包含即将发出的 reply 内容
        const reply = event?.reply ?? event?.message ?? event?.assistantMessage ?? '';
        if (!reply || typeof reply !== 'string') return;
        if (reply.trim().length < 100) return;

        // 静默写入，不等待结果，不阻塞回复
        _callServer('auto_capture', [reply.slice(0, 800)]).catch(() => {});
      } catch (_e) {
        // 严格静默，任何错误都不影响主流程
      }
    },
    { name: 'atlas-memory-auto-capture', description: '每轮回复前静默捕获重要内容到 Qdrant' }
  );
}
