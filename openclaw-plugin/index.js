/**
 * ATLAS Memory Core — OpenClaw Plugin (plugin-system version, /Volumes/data)
 * Uses factory-format registerTool. No async default export (would break plugin loader).
 */
import { spawnSync, spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import http from 'http';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_PY = path.join(__dirname, 'atlas_skill.py');
const SERVER_PORT = 16334;
const PROXY_BYPASS = { NO_PROXY: 'localhost,127.0.0.1', no_proxy: 'localhost,127.0.0.1' };

export const name = 'atlas-memory';
export const description = 'ATLAS Memory Core — Qdrant vector memory backend';

// ── persistent server management ──────────────────────────────────────────────

let _serverProc = null;
let _serverReady = false;

function _startServer() {
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

function _callServer(cmd, args = []) {
  return new Promise((resolve) => {
    const argsParam = args.length ? '&args=' + encodeURIComponent(args.join('\x00')) : '';
    const options = {
      hostname: '127.0.0.1',
      port: SERVER_PORT,
      path: `/${cmd}?${argsParam}`,
      method: 'GET',
      timeout: 10000,
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

// ── plugin registration (must be synchronous, no async default export) ────────

export function register(api) {
  _startServer();

  // ── tools (factory format required by plugin system) ──────────────────────

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

  api.registerTool(
    () => ({
      name: 'memory_search',
      description: '语义向量搜索记忆（Qdrant + nomic-embed-text）',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: '搜索查询' },
          limit: { type: 'number', description: '返回数量，默认 5' },
          threshold: { type: 'number', description: '相似度阈值，默认 0.65' },
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
    { names: ['memory_search'] }
  );

  api.registerTool(
    () => ({
      name: 'memory_stats',
      description: '获取记忆系统统计信息',
      parameters: { type: 'object', properties: {} },
      execute: () => (_id, _p) => callSkill('stats', []),
    }),
    { names: ['memory_stats'] }
  );

  api.registerTool(
    () => ({
      name: 'memory_list',
      description: '列出最近存储的记忆',
      parameters: {
        type: 'object',
        properties: { limit: { type: 'number', description: '数量，默认 10' } },
      },
      execute: () => (_id, { limit } = {}) => callSkill('list', limit ? [String(limit)] : []),
    }),
    { names: ['memory_list'] }
  );

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

  // ── before_prompt_build: 每轮对话前自动注入相关记忆 ──────────────────────

  api.registerHook(
    'before_prompt_build',
    async (event) => {
      const { prompt } = event;
      if (!prompt || prompt.trim().length < 6) return;
      if (prompt.trim().startsWith('/')) return;
      if (!_serverReady) return;

      const result = await _callServer('search', [prompt.slice(0, 300), '-n', '3', '--threshold', '0.65']);
      if (!result.success || !result.results || result.results.length === 0) return;

      const lines = result.results.map((m) =>
        `- [${m.created}][${m.category}] ${m.text}`
      );
      return {
        prependContext: `## 相关记忆（ATLAS 记忆库）\n${lines.join('\n')}\n`,
      };
    },
    { name: 'atlas-memory-context-inject', description: '每轮对话前注入相关 Qdrant 记忆' }
  );
}
