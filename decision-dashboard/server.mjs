import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  getUiCapability,
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from '@modelcontextprotocol/ext-apps/server';
import { z } from 'zod';
import { execFile } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(root, '..');
const defaultAdapter = resolve(packageRoot, 'scripts/opl_app_contribution.py');
const defaultHtmlPath = resolve(root, 'index.html');

function readPackageVersion() {
  for (const candidate of [resolve(packageRoot, 'opl-package.json'), resolve(root, 'package.json')]) {
    try {
      const parsed = JSON.parse(readFileSync(candidate, 'utf8'));
      const version = parsed.identity?.version ?? parsed.version;
      if (typeof version === 'string' && version.trim()) return version.trim();
    } catch {}
  }
  return '0.1.82';
}

export const RESOURCE_URI = 'ui://opl-flow/decision-dashboard.html';
export const SERVER_NAME = 'opl-flow-decision-dashboard';
export const SERVER_VERSION = readPackageVersion();

const TAB_VALUES = [
  'needs_action',
  'safe_to_archive',
  'active_objectives',
  'active_sessions',
  'blocked',
  'backlog',
  'pending_events',
];

const openInputSchema = z
  .object({
    instance_path: z.string().min(1).optional(),
    tab: z.enum(TAB_VALUES).optional(),
    bead_id: z.string().min(1).optional(),
  })
  .strict();

const sendInputSchema = z
  .object({
    instance_path: z.string().min(1).optional(),
    objective_id: z.string().min(1).max(128).optional(),
    title: z.string().min(1).max(120).optional(),
    message: z.string().min(1).max(4000),
    execution_mode: z.enum(['active', 'backlog']).optional(),
    executor: z.enum(['codex', 'antigravity', 'dsh']).optional(),
    priority: z.number().int().min(0).max(4).optional(),
    now: z.boolean().optional(),
    request_id: z.string().regex(/^[A-Za-z0-9_-]{1,100}$/).optional(),
  })
  .strict();

const approveInputSchema = z
  .object({
    instance_path: z.string().min(1).optional(),
    bead_id: z.string().min(1).max(128),
    approved_by: z.string().min(1).max(120),
    confirmed: z.literal(true),
  })
  .strict();

const tickInputSchema = z
  .object({
    instance_path: z.string().min(1).optional(),
    dry_run: z.boolean().optional(),
  })
  .strict();

const serviceInputSchema = z
  .object({
    instance_path: z.string().min(1).optional(),
    action: z.enum(['up', 'down']),
    confirmed: z.literal(true),
    bridge: z.enum(['auto', 'codex', 'antigravity']).optional(),
    interval_seconds: z.number().min(5).max(3600).optional(),
    dry_run: z.boolean().optional(),
  })
  .strict();

function supportsUi(server) {
  return (
    getUiCapability(server.server.getClientCapabilities())?.mimeTypes?.includes(
      RESOURCE_MIME_TYPE,
    ) === true
  );
}

export function runPythonAdapter(
  operation,
  input,
  {
    adapterPath = defaultAdapter,
    pythonBin = process.env.OPL_FLOW_PYTHON_BIN || 'python3',
    cwd = packageRoot,
    env = process.env,
  } = {},
) {
  return new Promise((resolvePromise, reject) => {
    const child = execFile(
      pythonBin,
      [adapterPath, operation],
      { cwd, env, timeout: 120000, maxBuffer: 16 * 1024 * 1024 },
      (error, stdout) => {
        try {
          const parsed = JSON.parse(stdout || '{}');
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            if (parsed.ok === false) {
              const msg =
                parsed.error?.message ||
                parsed.reason ||
                'OPL Flow 决策看板操作未完成。';
              reject(Object.assign(new Error(msg), { result: parsed }));
              return;
            }
            if (error && parsed.state !== 'unavailable') {
              reject(
                new Error(
                  parsed.error?.message ||
                    parsed.reason ||
                    error.message ||
                    'OPL Flow 适配器调用失败。',
                ),
              );
              return;
            }
            resolvePromise(parsed);
            return;
          }
          reject(new Error('OPL Flow 适配器返回了无效结构。'));
        } catch {
          reject(
            new Error(
              error?.message || 'OPL Flow 适配器返回不可解析结果，请重新读取。',
            ),
          );
        }
      },
    );
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(input ?? {}));
  });
}

function summarizeDashboard(payload) {
  if (!payload || payload.state === 'unavailable') {
    return payload?.reason || 'OPL Flow 决策看板当前不可用。';
  }
  const data = payload.data || {};
  const counts = data.counts || {};
  const svc = data.service || {};
  const engineState = svc.running
    ? '后台事件引擎运行中'
    : svc.installed
      ? '后台事件引擎已安装未启动'
      : '后台事件引擎未启动';
  const instanceLabel = data.instance_name ? `（${data.instance_name}）` : '';
  return `OPL Flow 决策看板${instanceLabel}：${engineState}；需你拍板 ${counts.needs_action ?? 0}，待批归档 ${counts.safe_to_archive ?? 0}，进行中 ${counts.active_objectives ?? 0}，活跃对话 ${counts.active_sessions ?? 0}，外部阻塞 ${counts.blocked ?? 0}，待排期 ${counts.backlog ?? 0}，待处理事件 ${counts.pending_events ?? 0}。`;
}

function errorResult(code, error) {
  const message = error instanceof Error ? error.message : String(error);
  return {
    isError: true,
    structuredContent: { error: { code, message } },
    content: [{ type: 'text', text: message }],
  };
}

export function createMcpServer({
  adapterPath = defaultAdapter,
  pythonBin = process.env.OPL_FLOW_PYTHON_BIN || 'python3',
  htmlPath = process.env.OPL_FLOW_DASHBOARD_HTML || defaultHtmlPath,
  runAdapter = runPythonAdapter,
} = {}) {
  const server = new McpServer(
    { name: SERVER_NAME, version: SERVER_VERSION },
    {
      instructions:
        'OPL Flow Chinese decision dashboard MiniApp. Inspect needs-action objectives, submit new tasks or replies, trigger deterministic router ticks, and record explicit human archive approvals.',
    },
  );

  const resourceMeta = {
    ui: {
      prefersBorder: true,
      csp: { connectDomains: [], resourceDomains: [] },
    },
  };

  registerAppResource(
    server,
    'OPL Flow decision dashboard',
    RESOURCE_URI,
    { _meta: resourceMeta },
    async () => {
      const targetHtml = process.env.OPL_FLOW_DASHBOARD_HTML || htmlPath;
      const html = (await readFile(targetHtml, 'utf8')).replace(
        '"__OPL_FLOW_INSTALLED_VERSION__"', JSON.stringify(SERVER_VERSION),
      );
      return {
        contents: [
          {
            uri: RESOURCE_URI,
            mimeType: RESOURCE_MIME_TYPE,
            text: html,
            _meta: resourceMeta,
          },
        ],
      };
    },
  );

  const invoke = (operation, input) =>
    runAdapter(operation, input, { adapterPath, pythonBin });

  registerAppTool(
    server,
    'open_opl_flow_dashboard',
    {
      title: 'OPL Flow · 决策看板',
      description:
        '查看 OPL Flow 中文决策看板：后台事件引擎状态、需拍板事项、待批归档、运行中任务与待处理事件队列。所有参数均可留空。',
      inputSchema: openInputSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        ui: {
          resourceUri: RESOURCE_URI,
          appId: SERVER_NAME,
          'openai/outputTemplate': RESOURCE_URI,
        },
        'com.google.antigravity/ui': {
          entrypoints: [
            { type: 'aux_pane', title: 'OPL Flow 决策看板' },
            { type: 'global', title: 'OPL Flow 决策看板' },
          ],
        },
      },
    },
    async (rawInput = {}) => {
      try {
        const focus = openInputSchema.parse(rawInput ?? {});
        const data = await invoke('dashboard', focus.instance_path ? { instance_path: focus.instance_path } : {});
        const summary = summarizeDashboard(data);
        if (supportsUi(server)) {
          return {
            content: [{ type: 'text', text: summary }],
            structuredContent: {
              data,
              focus,
              presentation: { mode: 'mcp-app', resource_uri: RESOURCE_URI },
            },
          };
        }
        return {
          content: [{ type: 'text', text: `${summary}\n${JSON.stringify(data)}` }],
          structuredContent: {
            data,
            focus,
            presentation: { mode: 'structured-data' },
          },
        };
      } catch (error) {
        if (supportsUi(server)) {
          const message = error instanceof Error ? error.message : String(error);
          return {
            content: [{ type: 'text', text: message }],
            structuredContent: {
              data: { ok: true, state: 'unavailable', reason: message },
              focus: rawInput ?? {},
              presentation: { mode: 'mcp-app', resource_uri: RESOURCE_URI },
            },
          };
        }
        return errorResult('opl_flow_dashboard_failed', error);
      }
    },
  );

  registerAppTool(
    server,
    'opl_flow_send',
    {
      title: '投递新任务或追加回复',
      description:
        '向 OPL Flow 投递新任务，或向指定目标发送人类拍板/补充指示（通过事件队列交由 Router 推进）。',
      inputSchema: sendInputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        ui: { resourceUri: RESOURCE_URI, visibility: ['app'] },
      },
    },
    async (rawInput) => {
      try {
        const parsed = sendInputSchema.parse(rawInput);
        const res = await invoke('send', parsed);
        return {
          content: [{ type: 'text', text: res.result?.message || '已投递到 OPL Flow。' }],
          structuredContent: res,
        };
      } catch (error) {
        return errorResult('opl_flow_send_failed', error);
      }
    },
  );

  registerAppTool(
    server,
    'opl_flow_approve_archive',
    {
      title: '批准归档目标',
      description:
        '在人类明确确认后，为已收口且无剩余工作的目标记录正式归档批准。',
      inputSchema: approveInputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        ui: { resourceUri: RESOURCE_URI, visibility: ['app'] },
      },
    },
    async (rawInput) => {
      try {
        const parsed = approveInputSchema.parse(rawInput);
        const res = await invoke('approve', parsed);
        return {
          content: [{ type: 'text', text: res.result?.message || '已记录归档批准。' }],
          structuredContent: res,
        };
      } catch (error) {
        return errorResult('opl_flow_approve_failed', error);
      }
    },
  );

  registerAppTool(
    server,
    'opl_flow_router_tick',
    {
      title: '执行单轮状态推进',
      description:
        '立即执行一轮确定性状态差量检测与事件队列评估，并返回最新状态。',
      inputSchema: tickInputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        ui: { resourceUri: RESOURCE_URI, visibility: ['app'] },
      },
    },
    async (rawInput = {}) => {
      try {
        const parsed = tickInputSchema.parse(rawInput ?? {});
        const res = await invoke('tick', parsed);
        return {
          content: [{ type: 'text', text: res.result?.message || '已完成单轮状态评估。' }],
          structuredContent: res,
        };
      } catch (error) {
        return errorResult('opl_flow_tick_failed', error);
      }
    },
  );

  registerAppTool(
    server,
    'opl_flow_router_service',
    {
      title: '启停后台事件引擎',
      description: '在人工确认后启动（up）或停止（down）本机 OPL Flow 后台事件引擎服务。',
      inputSchema: serviceInputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        ui: { resourceUri: RESOURCE_URI, visibility: ['app'] },
      },
    },
    async (rawInput) => {
      try {
        const parsed = serviceInputSchema.parse(rawInput);
        const res = await invoke('service', parsed);
        return {
          content: [{ type: 'text', text: res.result?.message || '后台事件引擎状态已更新。' }],
          structuredContent: res,
        };
      } catch (error) {
        return errorResult('opl_flow_service_failed', error);
      }
    },
  );

  return server;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await createMcpServer().connect(new StdioServerTransport());
}
