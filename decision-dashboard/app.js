import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
} from '@modelcontextprotocol/ext-apps';

const app = new App(
  {
    name: 'opl-flow-decision-dashboard',
    version: typeof __OPL_FLOW_VERSION__ === 'string' ? __OPL_FLOW_VERSION__ : '0.1.96',
  },
  { tools: { listChanged: false } },
  { strict: true },
);

const root = document.getElementById('app');

const VIEW_TABS = [
  { id: 'attention', label: '待我处理' },
  { id: 'objectives', label: '长期目标' },
  { id: 'sessions', label: '本机对话' },
  { id: 'events', label: '事件队列' },
];

const LEGACY_TAB_MAP = {
  needs_action: 'attention',
  safe_to_archive: 'attention',
  active_objectives: 'objectives',
  blocked: 'objectives',
  backlog: 'objectives',
  active_sessions: 'sessions',
  pending_events: 'events',
};

const state = {
  payload: null,
  focus: {},
  activeTab: '',
  selectedId: '',
  busy: false,
  bannerText: '',
  bannerError: false,
  composeOpen: false,
  objectiveId: '',
  newTitle: '',
  newMessage: '',
  newMode: 'active',
  newExecutor: '',
  newNow: false,
  serviceBridge: 'auto',
  approverName: 'owner',
  sessionScope: 'running',
  sessionScopeInitialized: false,
  sessionCarrier: 'all',
  showSubagents: false,
  sessionSearch: '',
  dialogMode: null,
  dialogTarget: null,
};

let readGeneration = 0;

function record(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function listOf(value) {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === 'object') : [];
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[ch]);
}

function instanceArg() {
  return state.focus.instance_path ? { instance_path: state.focus.instance_path } : {};
}

function applyHostContext(context) {
  if (context?.theme) applyDocumentTheme(context.theme);
  document.body.toggleAttribute(
    'data-ds-dark-theme',
    document.documentElement.dataset.theme === 'dark',
  );
  if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables);
  if (context?.styles?.css?.fonts) applyHostFonts(context.styles.css.fonts);
  if (context?.locale) document.documentElement.lang = context.locale;
  if (context?.displayMode) document.documentElement.dataset.displayMode = context.displayMode;
}

function setBanner(text, isError = false) {
  state.bannerText = text;
  state.bannerError = isError;
}

function dashboardData() {
  const envelope = record(state.payload);
  const result = record(envelope.data);
  const data = record(result.data);
  return { result, data };
}

function carrierLabel(carrier) {
  if (carrier === 'codex') return 'Codex';
  if (carrier === 'antigravity') return 'AntiGravity';
  if (carrier === 'dsh') return 'OPL DSH';
  return '自动路由';
}

function formatStatusLabel(status) {
  const s = String(status || '').toLowerCase();
  if (s === 'active' || s === 'busy') return '运行中';
  if (s === 'idle') return '空闲';
  if (s === 'error') return '异常';
  if (s === 'deferred') return '已冻结';
  if (s === 'in_progress') return '推进中';
  if (s === 'open') return '待处理';
  if (s === 'closed') return '待归档';
  return String(status || '—');
}

function formatBlockerText(blocker) {
  if (!blocker) return '';
  if (blocker === 'user_directed_freeze') return '用户已冻结，等待手动重启';
  return String(blocker);
}

function formatRelativeTime(iso) {
  if (!iso) return '—';
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return String(iso);
  const diffSec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (diffSec < 60) return '刚刚';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`;
  return `${Math.floor(diffSec / 86400)} 天前`;
}

function isSubagentSession(sess) {
  return Boolean(sess?.is_subagent) || sess?.surface === 'subagent';
}

function extractSessions(data, inbox) {
  const inInbox = listOf(inbox.active_sessions);
  if (inInbox.length) return inInbox;
  return listOf(record(data.active_sessions).sessions);
}

function extractOccupants(data, inbox) {
  const inInbox = listOf(inbox.active_workspace_occupants);
  if (inInbox.length) return inInbox;
  return listOf(record(data.active_sessions).active_workspace_occupants);
}

function summarizeWorkspaces(occupants) {
  const counts = new Map();
  for (const occ of occupants) {
    const label = String(occ.workspace_label || '').trim();
    if (!label) continue;
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const collisions = [];
  for (const [workspace, count] of counts.entries()) {
    if (count >= 2) collisions.push({ workspace, count });
  }
  return { uniqueCount: counts.size, collisions };
}

function normalizeFocusTab(tab) {
  if (!tab) return '';
  if (VIEW_TABS.some((t) => t.id === tab)) return tab;
  return LEGACY_TAB_MAP[tab] || '';
}

function chooseDefaultTab(counts) {
  const requested = normalizeFocusTab(state.focus.tab);
  if (requested) return requested;
  if (Number(counts.needs_action || 0) + Number(counts.safe_to_archive || 0) > 0) return 'attention';
  if (Number(counts.active_objectives || 0) + Number(counts.blocked || 0) > 0) return 'objectives';
  if (Number(counts.pending_events || 0) > 0) return 'events';
  if (Number(counts.active_sessions || 0) > 0) return 'sessions';
  return Number(counts.backlog || 0) > 0 ? 'objectives' : 'attention';
}

function filterSessions(sessions) {
  const q = String(state.sessionSearch || '').trim().toLowerCase();
  return sessions.filter((sess) => {
    if (!state.showSubagents && isSubagentSession(sess)) return false;
    if (state.sessionCarrier !== 'all' && sess.carrier !== state.sessionCarrier) return false;
    if (state.sessionScope === 'running' && sess.status !== 'active' && sess.status !== 'busy') return false;
    if (!q) return true;
    const hay = [
      sess.title,
      sess.model_label,
      sess.workspace_label,
      sess.carrier,
      sess.session_ref,
      sess.bound_bead_id,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return hay.includes(q);
  });
}

function findEntryById(inbox, sessions, activeTab, selectedId) {
  if (!selectedId) return null;
  if (activeTab === 'sessions') return sessions.find((s) => s.session_ref === selectedId) || null;
  if (activeTab === 'events') return listOf(inbox.pending_events).find((e) => e.event_id === selectedId) || null;
  const allBeads = [
    ...listOf(inbox.needs_action),
    ...listOf(inbox.safe_to_archive),
    ...listOf(inbox.active_objectives),
    ...listOf(inbox.blocked),
    ...listOf(inbox.backlog),
  ];
  return allBeads.find((b) => b.bead_id === selectedId) || null;
}

function syncModelContext(data, inbox, sessions, activeTab) {
  if (!app.getHostCapabilities?.()?.updateModelContext) return;
  const selectedEntry = findEntryById(inbox, sessions, activeTab, state.selectedId);
  const isBeadTab = activeTab === 'attention' || activeTab === 'objectives';
  const navigation = {
    ...instanceArg(),
    tab: activeTab,
    ...(selectedEntry && isBeadTab && selectedEntry.bead_id ? { bead_id: selectedEntry.bead_id } : {}),
  };
  const label = selectedEntry
    ? activeTab === 'events'
      ? `正在查看待处理事件 ${selectedEntry.event_id}`
      : activeTab === 'sessions'
        ? `正在查看本机对话 ${selectedEntry.title || selectedEntry.session_ref}（${selectedEntry.model_label || selectedEntry.carrier || ''}）`
        : `正在查看 OPL Flow 目标 ${selectedEntry.bead_id}（${selectedEntry.title || ''}）`
    : `正在查看 OPL Flow 总控（${VIEW_TABS.find((t) => t.id === activeTab)?.label || activeTab}）`;
  app
    .updateModelContext({
      content: [{ type: 'text', text: label }],
      structuredContent: {
        navigation,
        instance_name: data.instance_name || null,
        active_tab: activeTab,
        selected_bead_id: isBeadTab ? selectedEntry?.bead_id || null : null,
      },
    })
    .catch(() => {});
}

async function callServer(name, args) {
  const result = await app.callServerTool({ name, arguments: args });
  if (result.isError) {
    throw new Error(
      record(result.structuredContent?.error).message ||
        result.content?.find((part) => part.type === 'text')?.text ||
        '操作未完成，请刷新后重试。',
    );
  }
  return result.structuredContent || {};
}

async function refresh(bannerOnSuccess = '') {
  const generation = ++readGeneration;
  setBanner('正在刷新 OPL Flow 状态…', false);
  render();
  try {
    const isBeadTab = state.activeTab === 'attention' || state.activeTab === 'objectives';
    const payload = await callServer('open_opl_flow_dashboard', {
      ...instanceArg(),
      ...(state.activeTab ? { tab: state.activeTab } : {}),
      ...(state.selectedId && isBeadTab ? { bead_id: state.selectedId } : {}),
    });
    if (generation !== readGeneration) return;
    applyPayload(payload);
    setBanner(bannerOnSuccess, false);
    render();
  } catch (error) {
    if (generation !== readGeneration) return;
    setBanner(error?.message || '读取 OPL Flow 状态失败。', true);
    render();
  }
}

function applyPayload(payload) {
  const next = record(payload);
  state.payload = next;
  state.focus = record(next.focus);
  const { data } = dashboardData();
  const counts = record(data.counts);
  const inbox = record(data.inbox);
  const sessions = extractSessions(data, inbox);

  if (!state.activeTab || !VIEW_TABS.some((t) => t.id === state.activeTab)) {
    state.activeTab = chooseDefaultTab(counts);
  }
  if (!state.sessionScopeInitialized) {
    state.sessionScopeInitialized = true;
    const hasRunningPrimary = sessions.some(
      (s) => (s.status === 'active' || s.status === 'busy') && !isSubagentSession(s),
    );
    if (!hasRunningPrimary) state.sessionScope = 'all';
  }
  if (state.focus.bead_id) {
    const bid = String(state.focus.bead_id);
    if ([...listOf(inbox.needs_action), ...listOf(inbox.safe_to_archive)].some((i) => i.bead_id === bid)) {
      state.activeTab = 'attention';
      state.selectedId = bid;
    } else if ([...listOf(inbox.active_objectives), ...listOf(inbox.blocked), ...listOf(inbox.backlog)].some((i) => i.bead_id === bid)) {
      state.activeTab = 'objectives';
      state.selectedId = bid;
    }
  }
}

function renderObjectiveRow(entry, isArchiveCandidate) {
  const remaining = Array.isArray(entry.remaining) ? entry.remaining : [];
  const blockerText = formatBlockerText(entry.first_blocker);
  const statusText = formatStatusLabel(entry.status || entry.category);
  const carrier = entry.execution_carrier ? carrierLabel(entry.execution_carrier) : '';
  const selected = state.selectedId === entry.bead_id;
  return `<div class="row" data-row-id="${escapeHtml(entry.bead_id)}" data-selected="${selected ? 'true' : 'false'}">
    <div class="row-main">
      <div class="row-title">
        <strong>${escapeHtml(entry.title || entry.bead_id)}</strong>
        <span class="pill">${escapeHtml(statusText)}</span>
        ${carrier ? `<span class="pill">${escapeHtml(carrier)}</span>` : ''}
      </div>
      ${
        blockerText || entry.next_action
          ? `<div class="row-meta">${blockerText ? `<span>阻塞：${escapeHtml(blockerText)}</span>` : ''}${blockerText && entry.next_action ? ' · ' : ''}${entry.next_action ? `<span>下一步：${escapeHtml(entry.next_action)}</span>` : ''}</div>`
          : ''
      }
      ${
        remaining.length > 0
          ? `<details class="row-details"><summary>剩余步骤（${remaining.length} 项）</summary><ul>${remaining.map((r) => `<li>${escapeHtml(r)}</li>`).join('')}</ul></details>`
          : ''
      }
    </div>
    <div class="row-actions">
      ${
        entry.execution_carrier
          ? `<span class="pill">持有方：${escapeHtml(carrier)}</span>`
          : ''
      }
      ${
        isArchiveCandidate
          ? `<button class="dsh-button primary" type="button" data-open-approve="${escapeHtml(entry.bead_id)}" ${state.busy ? 'disabled' : ''}>批准归档…</button>`
          : `<button class="dsh-button" type="button" data-reply-bead="${escapeHtml(entry.bead_id)}" ${state.busy ? 'disabled' : ''}>追加指令</button>`
      }
    </div>
  </div>`;
}

function renderSessionRow(sess) {
  const carrierName = carrierLabel(sess.carrier);
  const displayTitle =
    sess.title ||
    (sess.workspace_label
      ? `${sess.workspace_label} · ${sess.model_label || carrierName}`
      : sess.model_label || sess.session_ref);
  const statusTone = sess.status === 'active' || sess.status === 'busy' ? 'running' : sess.status === 'error' ? 'warn' : '';
  const modelPart = sess.model_label && sess.model_label !== carrierName ? ` · ${sess.model_label}` : '';
  const boundText = sess.bound_bead_id ? '已纳管' : '自由对话（防撞车）';
  const selected = state.selectedId === sess.session_ref;
  return `<div class="row" data-row-id="${escapeHtml(sess.session_ref)}" data-selected="${selected ? 'true' : 'false'}">
    <div class="row-main">
      <div class="row-title">
        <span class="pill" ${statusTone ? `data-tone="${statusTone}"` : ''}><span class="dot" aria-hidden="true"></span><span>${escapeHtml(formatStatusLabel(sess.status || 'idle'))}</span></span>
        <strong>${escapeHtml(displayTitle)}</strong>
        ${sess.workspace_label ? `<span class="pill">${escapeHtml(sess.workspace_label)}</span>` : ''}
        ${sess.bound_bead_id ? `<span class="pill">Bead: ${escapeHtml(sess.bound_bead_id)}</span>` : ''}
        ${isSubagentSession(sess) ? '<span class="pill">子代理</span>' : ''}
      </div>
      <div class="row-meta" title="${escapeHtml(sess.updated_at || '')}">${escapeHtml(`${carrierName}${modelPart} · ${formatRelativeTime(sess.updated_at)} · ${boundText}`)}</div>
      <details class="row-details">
        <summary>会话标识与接管说明</summary>
        <div class="row-details-body">
          <div>会话标识：<code>${escapeHtml(sess.session_ref)}</code></div>
          ${sess.workspace_path ? `<div>工作目录：<code>${escapeHtml(sess.workspace_path)}</code></div>` : ''}
          ${
            sess.bound_bead_id
              ? `<div>已绑定总账目标：<code>${escapeHtml(sess.bound_bead_id)}</code></div>`
              : `<div>如需由 OPL Flow 跟踪接管，可绑定投递：<code>opl-flow send "目标描述" --session "${escapeHtml(sess.session_ref)}"</code></div>`
          }
        </div>
      </details>
    </div>
    <div class="row-actions">
      <span class="pill">${escapeHtml(carrierName)}</span>
      <button class="dsh-button" type="button" data-bind-session="${escapeHtml(sess.session_ref)}" ${state.busy ? 'disabled' : ''}>投递任务到此会话</button>
    </div>
  </div>`;
}

function renderDialog() {
  if (!state.dialogMode) return '';
  if (state.dialogMode === 'approve' && state.dialogTarget) {
    return `<dialog id="confirm-dialog" class="confirm-dialog" aria-labelledby="confirm-dialog-title">
      <div class="dialog-body">
        <h1 id="confirm-dialog-title">确认批准归档</h1>
        <p class="dialog-summary"><strong>目标编号：</strong>${escapeHtml(state.dialogTarget.bead_id)}<br><strong>目标标题：</strong>${escapeHtml(state.dialogTarget.title)}</p>
        <div class="field">
          <label for="approver-input">批准人标识 <span aria-hidden="true">*</span></label>
          <input id="approver-input" name="approved_by" type="text" class="dsh-input" required maxlength="120" autocorrect="off" autocapitalize="none" spellcheck="false" enterkeyhint="done" value="${escapeHtml(state.approverName)}" aria-describedby="approver-error">
          <span id="approver-error" class="field-error" role="alert"></span>
        </div>
        <div class="dialog-actions">
          <button class="dsh-button quiet" type="button" data-dialog-cancel autofocus>取消</button>
          <button class="dsh-button primary" type="button" data-dialog-confirm ${state.busy ? 'disabled' : ''}>${state.busy ? '提交中…' : '确认批准归档'}</button>
        </div>
      </div>
    </dialog>`;
  }
  if (state.dialogMode === 'service') {
    const starting = state.dialogTarget?.action === 'up';
    return `<dialog id="confirm-dialog" class="confirm-dialog" aria-labelledby="confirm-dialog-title">
      <div class="dialog-body">
        <h1 id="confirm-dialog-title">${starting ? '确认启动后台自动路由' : '确认停止后台自动路由'}</h1>
        <p class="dialog-summary">${
          starting
            ? '将在本机注册并启动 OPL Flow 后台事件引擎（LaunchAgent / systemd user），按事件增量触发控制流，无事件时不消耗模型额度。'
            : '将停止并卸载本机 OPL Flow 后台事件引擎服务；已有账本与未处理事件会完整保留。'
        }</p>
        ${
          starting
            ? `<div class="field">
                <label for="service-bridge-select">默认控制桥接器</label>
                <select id="service-bridge-select" name="bridge" class="dsh-input">
                  <option value="auto" ${state.serviceBridge === 'auto' ? 'selected' : ''}>Auto（多载体自动路由：Codex + AntiGravity + DSH）</option>
                  <option value="codex" ${state.serviceBridge === 'codex' ? 'selected' : ''}>Codex CLI (codex exec)</option>
                  <option value="antigravity" ${state.serviceBridge === 'antigravity' ? 'selected' : ''}>AntiGravity CLI (agy --print)</option>
                </select>
              </div>`
            : ''
        }
        <div class="dialog-actions">
          <button class="dsh-button quiet" type="button" data-dialog-cancel autofocus>取消</button>
          <button class="dsh-button primary" type="button" data-dialog-confirm ${state.busy ? 'disabled' : ''}>${state.busy ? '执行中…' : starting ? '确认启动' : '确认停止'}</button>
        </div>
      </div>
    </dialog>`;
  }
  return '';
}

function renderPanelBody(activeTab, inbox, allSessions, visibleSessions, attentionCount, objectivesCount, runningPrimaryCount, primaryTotalCount, subagentCount) {
  const needsActionList = listOf(inbox.needs_action);
  const archiveList = listOf(inbox.safe_to_archive);
  const activeObjectivesList = listOf(inbox.active_objectives);
  const blockedList = listOf(inbox.blocked);
  const backlogList = listOf(inbox.backlog);
  const pendingEvents = listOf(inbox.pending_events);

  if (activeTab === 'attention') {
    if (attentionCount === 0) {
      return `<div class="surface"><div class="empty-state"><strong>当前无需人工拍板或归档批准</strong><p>有需要拍板的任务或完成待归档项时会自动汇总到这里。</p></div></div>`;
    }
    return `<div class="surface">
      ${needsActionList.length ? `<div class="section-header"><span>需你拍板</span><span>${needsActionList.length}</span></div>${needsActionList.map((e) => renderObjectiveRow(e, false)).join('')}` : ''}
      ${archiveList.length ? `<div class="section-header"><span>待批归档</span><span>${archiveList.length}</span></div>${archiveList.map((e) => renderObjectiveRow(e, true)).join('')}` : ''}
    </div>`;
  }

  if (activeTab === 'objectives') {
    if (objectivesCount === 0) {
      return `<div class="surface"><div class="empty-state"><strong>暂无纳入总账的长期目标</strong></div></div>`;
    }
    return `<div class="surface">
      ${activeObjectivesList.length ? `<div class="section-header"><span>进行中</span><span>${activeObjectivesList.length}</span></div>${activeObjectivesList.map((e) => renderObjectiveRow(e, false)).join('')}` : ''}
      ${blockedList.length ? `<div class="section-header"><span>外部阻塞</span><span>${blockedList.length}</span></div>${blockedList.map((e) => renderObjectiveRow(e, false)).join('')}` : ''}
      ${backlogList.length ? `<div class="section-header"><span>待排期 / 冻结保留</span><span>${backlogList.length}</span></div>${backlogList.map((e) => renderObjectiveRow(e, false)).join('')}` : ''}
    </div>`;
  }

  if (activeTab === 'sessions') {
    return `<div class="toolbar">
        <div class="segmented" role="group" aria-label="活跃范围">
          <button type="button" class="seg-button" data-sess-scope="running" aria-pressed="${state.sessionScope === 'running' ? 'true' : 'false'}">运行中 (${runningPrimaryCount})</button>
          <button type="button" class="seg-button" data-sess-scope="all" aria-pressed="${state.sessionScope === 'all' ? 'true' : 'false'}">全部近期 (${primaryTotalCount})</button>
        </div>
        <select class="dsh-input session-select" id="session-carrier-filter" aria-label="载体筛选">
          <option value="all" ${state.sessionCarrier === 'all' ? 'selected' : ''}>全部载体</option>
          <option value="antigravity" ${state.sessionCarrier === 'antigravity' ? 'selected' : ''}>AntiGravity</option>
          <option value="codex" ${state.sessionCarrier === 'codex' ? 'selected' : ''}>Codex</option>
          <option value="dsh" ${state.sessionCarrier === 'dsh' ? 'selected' : ''}>OPL DSH</option>
        </select>
        ${
          subagentCount > 0
            ? `<label class="check-inline"><input type="checkbox" id="session-subagents-toggle" ${state.showSubagents ? 'checked' : ''}><span>显示子代理 (${subagentCount})</span></label>`
            : ''
        }
        <input type="search" class="dsh-input session-search" id="session-search-input" aria-label="搜索对话标题或工作区" placeholder="搜索标题、工作区或模型…" value="${escapeHtml(state.sessionSearch)}">
      </div>
      <div class="surface">
        ${
          visibleSessions.length === 0
            ? '<div class="empty-state"><strong>当前筛选下无匹配对话</strong></div>'
            : visibleSessions.map((sess) => renderSessionRow(sess)).join('')
        }
      </div>`;
  }

  return `<div class="surface">
    ${
      pendingEvents.length === 0
        ? '<div class="empty-state"><strong>当前无待处理事件</strong></div>'
        : pendingEvents
            .map(
              (ev) => `<div class="row" data-row-id="${escapeHtml(ev.event_id)}">
                <div class="row-main">
                  <div class="row-title">
                    <span class="pill">${escapeHtml(ev.event_type || 'event')}</span>
                    <strong>${escapeHtml(ev.objective_id || '全局')}</strong>
                    <span class="pill">${escapeHtml(ev.status || 'pending')}</span>
                  </div>
                  <div class="row-meta" title="${escapeHtml(ev.created_at || '')}">${escapeHtml(ev.summary || ev.source || '无附加摘要')} · ${escapeHtml(formatRelativeTime(ev.created_at))}</div>
                </div>
                <div class="row-actions">
                  <button class="dsh-button primary" type="button" data-action="tick" ${state.busy ? 'disabled' : ''}>立即评估 (Tick)</button>
                </div>
              </div>`,
            )
            .join('')
    }
  </div>`;
}

function render() {
  const { result, data } = dashboardData();
  const svc = record(data.service);
  const counts = record(data.counts);
  const inbox = record(data.inbox);

  if (!state.payload) {
    root.innerHTML = `<header class="topbar">
      <div class="topbar-copy"><div class="family-heading"><h1>OPL Flow 总控</h1><span class="family-label">OPL Apps · OPL Flow</span></div></div>
      <div class="topbar-actions"><button class="dsh-button" type="button" data-refresh>读取看板</button></div>
    </header>
    <div class="live-region" aria-live="polite"></div>
    <div class="loading-state" role="status" aria-live="polite">正在等待宿主提供 OPL Flow 决策看板数据…</div>`;
    root.querySelector('[data-refresh]')?.addEventListener('click', () => void refresh());
    return;
  }

  if (result.state === 'unavailable') {
    root.innerHTML = `<header class="topbar">
      <div class="topbar-copy"><div class="family-heading"><h1>OPL Flow 总控</h1><span class="family-label">OPL Apps · OPL Flow</span></div></div>
      <div class="topbar-actions"><button class="dsh-button" type="button" data-refresh>重新读取</button></div>
    </header>
    <div class="live-region" aria-live="polite"></div>
    <div class="error-state" role="alert"><strong>暂无法读取 OPL Flow 实例</strong><p>${escapeHtml(result.reason || '请先完成 OPL Flow 实例绑定。')}</p><button class="dsh-button primary" type="button" data-refresh>重试</button></div>`;
    root.querySelectorAll('[data-refresh]').forEach((btn) => btn.addEventListener('click', () => void refresh()));
    return;
  }

  const activeTab = VIEW_TABS.some((t) => t.id === state.activeTab) ? state.activeTab : chooseDefaultTab(counts);
  state.activeTab = activeTab;

  const allSessions = extractSessions(data, inbox);
  const occupants = extractOccupants(data, inbox);
  const wsSummary = summarizeWorkspaces(occupants);
  const attentionCount = Number(counts.needs_action || 0) + Number(counts.safe_to_archive || 0);
  const objectivesCount = Number(counts.active_objectives || 0) + Number(counts.blocked || 0) + Number(counts.backlog || 0);
  const subagentCount = Number(
    counts.subagent_sessions ?? allSessions.filter((s) => isSubagentSession(s)).length,
  );
  const runningPrimaryCount = Number(
    counts.running_sessions ??
      allSessions.filter((s) => (s.status === 'active' || s.status === 'busy') && !isSubagentSession(s)).length,
  );
  const primaryTotalCount = Number(
    counts.primary_sessions ?? allSessions.filter((s) => !isSubagentSession(s)).length,
  );
  const visibleSessions = filterSessions(allSessions);

  const running = allSessions.filter((s) => (s.status === 'active' || s.status === 'busy') && !isSubagentSession(s));
  const codexN = running.filter((s) => s.carrier === 'codex').length;
  const agyN = running.filter((s) => s.carrier === 'antigravity').length;
  const dshN = running.filter((s) => s.carrier === 'dsh').length;
  const breakdownParts = [];
  if (agyN) breakdownParts.push(`AntiGravity ${agyN}`);
  if (codexN) breakdownParts.push(`Codex ${codexN}`);
  if (dshN) breakdownParts.push(`DSH ${dshN}`);
  const carrierBreakdown = breakdownParts.join(' · ') || `最近 ${primaryTotalCount} 个主对话`;

  const uniqueWsCount = Number(counts.unique_occupied_workspaces ?? wsSummary.uniqueCount);
  const wsHint = wsSummary.collisions.length
    ? `并发目录：${wsSummary.collisions.map((c) => `${c.workspace}(${c.count})`).join('、')}`
    : '各工作区无冲突';

  const serviceRunning = Boolean(svc.running);
  const serviceBridge = svc.bridge || 'auto';
  const serviceAction = serviceRunning ? 'down' : 'up';
  const serviceLabel = serviceRunning
    ? `自动路由 · ${serviceBridge}`
    : svc.installed
      ? `已安装未启动 · ${serviceBridge}`
      : '路由已停止';

  const isFullscreen = app.getHostContext?.()?.displayMode === 'fullscreen';
  const tabCountFor = (tabId) => {
    if (tabId === 'attention') return attentionCount;
    if (tabId === 'objectives') return objectivesCount;
    if (tabId === 'sessions') return runningPrimaryCount || primaryTotalCount;
    return Number(counts.pending_events || 0);
  };

  root.innerHTML = `<header class="topbar">
      <div class="topbar-copy">
        <div class="family-heading">
          <h1>OPL Flow 总控</h1>
          <span class="family-label">OPL Apps · OPL Flow</span>
          <span class="pill" ${serviceRunning ? 'data-tone="running"' : ''}><span class="dot" aria-hidden="true"></span><span>${escapeHtml(serviceLabel)}</span></span>
          ${data.instance_name ? `<span class="pill">${escapeHtml(data.instance_name)}</span>` : ''}
        </div>
        <details class="boundary-details">
          <summary>定位与三端分工说明</summary>
          <p>个人跨 Codex / AntiGravity / OPL DSH 的 Beads/Dolt 长期目标总账与零 Token 自动路由控制塔（不自建第二套聊天框）；自由对话仅作工作区防撞车保护。</p>
        </details>
      </div>
      <div class="topbar-actions">
        <button class="dsh-button primary" type="button" data-toggle-compose ${state.busy ? 'disabled' : ''}>${state.composeOpen ? '收起投递' : '新建 / 投递任务'}</button>
        <button class="dsh-button" type="button" data-action="tick" ${state.busy ? 'disabled' : ''}>立即评估 (Tick)</button>
        <button class="dsh-button quiet" type="button" data-open-service="${serviceAction}" ${state.busy ? 'disabled' : ''}>${serviceRunning ? '停止路由' : '启动路由'}</button>
        <button class="dsh-button quiet hide-narrow" type="button" data-fullscreen>${isFullscreen ? '收起' : '展开'}</button>
        <button class="dsh-button" type="button" data-refresh ${state.busy ? 'disabled' : ''}>刷新</button>
      </div>
    </header>

    <div class="live-region" aria-live="polite">${
      state.bannerText
        ? `<div class="status-banner ${state.bannerError ? 'error' : ''}" role="${state.bannerError ? 'alert' : 'status'}"><span>${escapeHtml(state.bannerText)}</span><button class="dsh-button small quiet" type="button" data-dismiss-banner>关闭</button></div>`
        : ''
    }</div>

    <div class="summary-strip" role="region" aria-label="总控关键指标">
      <button type="button" class="summary-tile" data-jump-tab="attention">
        <span class="summary-label">待我处理</span>
        <span class="summary-value">${attentionCount}</span>
        <span class="summary-hint">${attentionCount > 0 ? `拍板 ${Number(counts.needs_action || 0)} · 归档 ${Number(counts.safe_to_archive || 0)}` : '已清空'}</span>
      </button>
      <button type="button" class="summary-tile" data-jump-tab="objectives">
        <span class="summary-label">长期目标</span>
        <span class="summary-value">${Number(counts.active_objectives || 0)}</span>
        <span class="summary-hint">${`进行中 ${Number(counts.active_objectives || 0)} · 阻塞 ${Number(counts.blocked || 0)} · 待排期 ${Number(counts.backlog || 0)}`}</span>
      </button>
      <button type="button" class="summary-tile" data-jump-tab="sessions" data-jump-scope="running">
        <span class="summary-label">运行中对话</span>
        <span class="summary-value">${runningPrimaryCount}</span>
        <span class="summary-hint">${escapeHtml(carrierBreakdown)}</span>
      </button>
      <button type="button" class="summary-tile" data-jump-tab="sessions" data-jump-scope="running">
        <span class="summary-label">工作区防撞车</span>
        <span class="summary-value">${uniqueWsCount}</span>
        <span class="summary-hint">${escapeHtml(wsHint)}</span>
      </button>
    </div>

    ${
      state.composeOpen
        ? `<form class="compose-card" id="new-task-form" aria-label="新建或投递任务" novalidate>
            <div class="form-grid">
              <div class="field">
                <label for="new-obj">目标编号（留空则新建）</label>
                <input id="new-obj" name="objective_id" type="text" class="dsh-input" maxlength="128" placeholder="opl-123" value="${escapeHtml(state.objectiveId)}">
              </div>
              ${
                !state.objectiveId.trim()
                  ? `<div class="field">
                      <label for="new-title">目标标题（可选）</label>
                      <input id="new-title" name="title" type="text" class="dsh-input" maxlength="120" enterkeyhint="next" placeholder="留空将自动取正文首行" value="${escapeHtml(state.newTitle)}">
                    </div>`
                  : ''
              }
              <div class="field">
                <label for="new-executor">执行载体</label>
                <select id="new-executor" name="executor" class="dsh-input">
                  <option value="" ${state.newExecutor === '' ? 'selected' : ''}>自动路由 (auto)</option>
                  <option value="antigravity" ${state.newExecutor === 'antigravity' ? 'selected' : ''}>AntiGravity</option>
                  <option value="codex" ${state.newExecutor === 'codex' ? 'selected' : ''}>Codex</option>
                  <option value="dsh" ${state.newExecutor === 'dsh' ? 'selected' : ''}>OPL DSH</option>
                </select>
              </div>
              <div class="field">
                <label for="new-mode">队列模式</label>
                <select id="new-mode" name="execution_mode" class="dsh-input">
                  <option value="active" ${state.newMode === 'active' ? 'selected' : ''}>立即排入进行中</option>
                  <option value="backlog" ${state.newMode === 'backlog' ? 'selected' : ''}>暂存待排期</option>
                </select>
              </div>
            </div>
            <div class="field">
              <label for="new-message">任务内容或拍板指令 <span aria-hidden="true">*</span></label>
              <textarea id="new-message" name="message" class="dsh-input" required maxlength="4000" enterkeyhint="send" aria-describedby="new-message-help new-message-error" placeholder="输入新任务需求或对目标的拍板意见（支持 Cmd/Ctrl + Enter 提交）…">${escapeHtml(state.newMessage)}</textarea>
              <span id="new-message-help" class="field-hint">写入总账并触发事件路由，无需额外消耗扫描 Token。</span>
              <span id="new-message-error" class="field-error" role="alert"></span>
            </div>
            <div class="topbar-actions">
              <label class="check-inline" for="new-now"><input id="new-now" name="now" type="checkbox" ${state.newNow ? 'checked' : ''}><span>投递后立即执行一轮评估</span></label>
              <button class="dsh-button quiet" type="button" data-cancel-compose>取消</button>
              <button class="dsh-button primary" type="submit" ${state.busy ? 'disabled' : ''}>${state.busy ? '投递中…' : '确认投递'}</button>
            </div>
          </form>`
        : ''
    }

    <div class="tablist" role="tablist" aria-label="OPL Flow 视图切换">
      ${VIEW_TABS.map(
        (tab) => `<button id="tab-${tab.id}" type="button" role="tab" class="tab" data-tab="${tab.id}" aria-selected="${tab.id === activeTab ? 'true' : 'false'}">
          <span>${escapeHtml(tab.label)}</span>
          <span class="tab-count">${tabCountFor(tab.id)}</span>
        </button>`,
      ).join('')}
    </div>

    <div role="tabpanel" aria-labelledby="tab-${activeTab}">
      ${renderPanelBody(activeTab, inbox, allSessions, visibleSessions, attentionCount, objectivesCount, runningPrimaryCount, primaryTotalCount, subagentCount)}
    </div>
    ${renderDialog()}`;

  bindEvents(data, inbox, allSessions, activeTab);
  syncModelContext(data, inbox, allSessions, activeTab);
}

function attachFieldValidation(inputEl, errorEl, emptyMsg) {
  if (!inputEl || !errorEl) return;
  let edited = false;
  const validate = () => {
    const valid = Boolean(inputEl.value.trim());
    if (!valid) {
      inputEl.setAttribute('aria-invalid', 'true');
      errorEl.textContent = emptyMsg;
      return false;
    }
    inputEl.removeAttribute('aria-invalid');
    errorEl.textContent = '';
    return true;
  };
  inputEl.addEventListener('input', () => {
    edited = true;
    if (inputEl.value.trim()) {
      inputEl.removeAttribute('aria-invalid');
      errorEl.textContent = '';
    }
  });
  inputEl.addEventListener('blur', () => {
    if (edited) validate();
  });
  return validate;
}

function bindEvents(data, inbox, allSessions, activeTab) {
  root.querySelector('[data-refresh]')?.addEventListener('click', () => void refresh('已刷新最新状态。'));
  root.querySelector('[data-dismiss-banner]')?.addEventListener('click', () => {
    setBanner('', false);
    render();
  });
  root.querySelector('[data-fullscreen]')?.addEventListener('click', () => {
    const nextMode = app.getHostContext?.()?.displayMode === 'fullscreen' ? 'inline' : 'fullscreen';
    void app.requestDisplayMode({ mode: nextMode }).catch(() => {});
  });
  root.querySelector('[data-toggle-compose]')?.addEventListener('click', () => {
    state.composeOpen = !state.composeOpen;
    render();
  });
  root.querySelector('[data-cancel-compose]')?.addEventListener('click', () => {
    state.composeOpen = false;
    render();
  });

  root.querySelectorAll('[data-jump-tab]').forEach((btn) =>
    btn.addEventListener('click', () => {
      state.activeTab = btn.dataset.jumpTab;
      if (btn.dataset.jumpScope) state.sessionScope = btn.dataset.jumpScope;
      render();
    }),
  );

  const tabEls = Array.from(root.querySelectorAll('[role="tab"]'));
  tabEls.forEach((btn, idx) => {
    btn.addEventListener('click', () => {
      state.activeTab = btn.dataset.tab;
      state.selectedId = '';
      render();
    });
    btn.addEventListener('keydown', (e) => {
      let next = -1;
      if (e.key === 'ArrowRight') next = (idx + 1) % VIEW_TABS.length;
      else if (e.key === 'ArrowLeft') next = (idx - 1 + VIEW_TABS.length) % VIEW_TABS.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = VIEW_TABS.length - 1;
      if (next < 0) return;
      e.preventDefault();
      state.activeTab = VIEW_TABS[next].id;
      state.selectedId = '';
      render();
      root.querySelector(`#tab-${VIEW_TABS[next].id}`)?.focus();
    });
  });

  root.querySelectorAll('[data-sess-scope]').forEach((btn) =>
    btn.addEventListener('click', () => {
      state.sessionScope = btn.dataset.sessScope;
      render();
    }),
  );
  root.querySelector('#session-carrier-filter')?.addEventListener('change', (e) => {
    state.sessionCarrier = e.target.value;
    render();
  });
  root.querySelector('#session-subagents-toggle')?.addEventListener('change', (e) => {
    state.showSubagents = e.target.checked;
    render();
  });
  root.querySelector('#session-search-input')?.addEventListener('input', (e) => {
    state.sessionSearch = e.target.value;
    render();
    const el = root.querySelector('#session-search-input');
    if (el) {
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  });

  root.querySelectorAll('[data-action="tick"]').forEach((btn) =>
    btn.addEventListener('click', () => void runTick()),
  );
  root.querySelector('[data-open-service]')?.addEventListener('click', (event) => {
    const action = event.currentTarget.dataset.openService;
    state.dialogMode = 'service';
    state.dialogTarget = { action };
    render();
  });
  root.querySelectorAll('[data-open-approve]').forEach((btn) =>
    btn.addEventListener('click', () => {
      const bid = btn.dataset.openApprove;
      const entry = findEntryById(inbox, allSessions, activeTab, bid);
      state.selectedId = bid;
      state.dialogMode = 'approve';
      state.dialogTarget = { bead_id: bid, title: entry?.title || bid };
      render();
    }),
  );
  root.querySelectorAll('[data-reply-bead]').forEach((btn) =>
    btn.addEventListener('click', () => {
      state.objectiveId = btn.dataset.replyBead || '';
      state.selectedId = state.objectiveId;
      state.composeOpen = true;
      render();
      root.querySelector('#new-message')?.focus();
    }),
  );
  root.querySelectorAll('[data-bind-session]').forEach((btn) =>
    btn.addEventListener('click', () => {
      const ref = btn.dataset.bindSession || '';
      state.selectedId = ref;
      state.composeOpen = true;
      state.newExecutor = ref.startsWith('antigravity:') ? 'antigravity' : ref.startsWith('codex:') ? 'codex' : ref.startsWith('dsh:') ? 'dsh' : '';
      render();
      root.querySelector('#new-message')?.focus();
    }),
  );

  // Composer form
  const newForm = root.querySelector('#new-task-form');
  const objEl = root.querySelector('#new-obj');
  const newTitleEl = root.querySelector('#new-title');
  const newMsgEl = root.querySelector('#new-message');
  const newMsgErr = root.querySelector('#new-message-error');
  const newModeEl = root.querySelector('#new-mode');
  const newExecutorEl = root.querySelector('#new-executor');
  const newNowEl = root.querySelector('#new-now');
  const validateNewMsg = attachFieldValidation(newMsgEl, newMsgErr, '请输入任务内容或拍板指令。');

  objEl?.addEventListener('input', (e) => {
    const prevEmpty = !state.objectiveId.trim();
    state.objectiveId = e.target.value;
    if (prevEmpty !== !state.objectiveId.trim()) {
      render();
      const restored = root.querySelector('#new-obj');
      if (restored) {
        restored.focus();
        restored.setSelectionRange(restored.value.length, restored.value.length);
      }
    }
  });
  newTitleEl?.addEventListener('input', (e) => { state.newTitle = e.target.value; });
  newMsgEl?.addEventListener('input', (e) => { state.newMessage = e.target.value; });
  newModeEl?.addEventListener('change', (e) => { state.newMode = e.target.value; });
  newExecutorEl?.addEventListener('change', (e) => { state.newExecutor = e.target.value; });
  newNowEl?.addEventListener('change', (e) => { state.newNow = e.target.checked; });
  newMsgEl?.addEventListener('keydown', (e) => {
    if (e.isComposing) return;
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      newForm?.requestSubmit();
    }
  });
  newForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    if (state.busy) return;
    if (validateNewMsg && !validateNewMsg()) {
      newMsgEl?.focus();
      return;
    }
    void submitNewTask();
  });

  // Native modal dialog wiring
  const dialog = root.querySelector('#confirm-dialog');
  if (dialog && typeof dialog.showModal === 'function') {
    if (!dialog.open) dialog.showModal();
    const approverInput = dialog.querySelector('#approver-input');
    const approverErr = dialog.querySelector('#approver-error');
    const bridgeSelect = dialog.querySelector('#service-bridge-select');
    const validateApprover = attachFieldValidation(approverInput, approverErr, '请输入批准人标识。');
    approverInput?.addEventListener('input', (e) => { state.approverName = e.target.value; });
    bridgeSelect?.addEventListener('change', (e) => { state.serviceBridge = e.target.value; });
    dialog.querySelector('[data-dialog-cancel]')?.addEventListener('click', () => {
      dialog.close('cancel');
    });
    dialog.querySelector('[data-dialog-confirm]')?.addEventListener('click', () => {
      if (state.busy) return;
      if (state.dialogMode === 'approve') {
        if (validateApprover && !validateApprover()) {
          approverInput?.focus();
          return;
        }
        const beadId = state.dialogTarget?.bead_id;
        dialog.close('confirm');
        if (beadId) void confirmApproveArchive(beadId);
      } else if (state.dialogMode === 'service') {
        const action = state.dialogTarget?.action;
        dialog.close('confirm');
        if (action) void confirmServiceAction(action);
      }
    });
    dialog.addEventListener('close', () => {
      dialog.returnValue = '';
      if (state.dialogMode) {
        state.dialogMode = null;
        state.dialogTarget = null;
        render();
      }
    });
  }
}

async function submitNewTask() {
  state.busy = true;
  setBanner('正在投递至 OPL Flow 队列…', false);
  render();
  try {
    const cleanObj = state.objectiveId.trim();
    const res = await callServer('opl_flow_send', {
      ...instanceArg(),
      ...(cleanObj ? { objective_id: cleanObj } : state.newTitle.trim() ? { title: state.newTitle.trim() } : {}),
      message: state.newMessage.trim(),
      execution_mode: state.newMode,
      ...(state.newExecutor ? { executor: state.newExecutor } : {}),
      now: state.newNow,
      request_id: crypto.randomUUID(),
    });
    state.objectiveId = '';
    state.newTitle = '';
    state.newMessage = '';
    state.composeOpen = false;
    state.busy = false;
    state.activeTab = 'objectives';
    if (res.result?.bead_id) state.selectedId = res.result.bead_id;
    await refresh(res.result?.message || '已投递至 OPL Flow 队列。');
  } catch (error) {
    state.busy = false;
    setBanner(error?.message || '投递任务失败。', true);
    render();
  }
}

async function confirmApproveArchive(beadId) {
  state.busy = true;
  setBanner(`正在记录归档批准：${beadId}…`, false);
  render();
  try {
    const res = await callServer('opl_flow_approve_archive', {
      ...instanceArg(),
      bead_id: beadId,
      approved_by: state.approverName.trim() || 'owner',
      confirmed: true,
    });
    state.busy = false;
    await refresh(res.result?.message || `已记录归档批准：${beadId}。`);
  } catch (error) {
    state.busy = false;
    setBanner(error?.message || '归档批准失败。', true);
    render();
  }
}

async function runTick() {
  state.busy = true;
  setBanner('正在执行单轮状态推进…', false);
  render();
  try {
    const res = await callServer('opl_flow_router_tick', { ...instanceArg() });
    state.busy = false;
    await refresh(res.result?.message || '已完成一轮状态评估。');
  } catch (error) {
    state.busy = false;
    setBanner(error?.message || '状态推进失败。', true);
    render();
  }
}

async function confirmServiceAction(action) {
  state.busy = true;
  setBanner(action === 'up' ? '正在启动后台路由…' : '正在停止后台路由…', false);
  render();
  try {
    const res = await callServer('opl_flow_router_service', {
      ...instanceArg(),
      action,
      confirmed: true,
      ...(action === 'up' && state.serviceBridge ? { bridge: state.serviceBridge } : {}),
    });
    state.busy = false;
    await refresh(res.result?.message || '后台引擎状态已更新。');
  } catch (error) {
    state.busy = false;
    setBanner(error?.message || '后台引擎启停失败。', true);
    render();
  }
}

app.ontoolinput = (params) => {
  const args = record(params?.arguments);
  if (Object.keys(args).length > 0) {
    state.focus = { ...state.focus, ...args };
  }
};

app.ontoolresult = (params) => {
  if (params?.isError) {
    setBanner(record(params.structuredContent?.error).message || '读取失败。', true);
    render();
    return;
  }
  const payload = record(params?.structuredContent);
  if (payload.data || payload.focus || payload.presentation) {
    applyPayload(payload);
    setBanner('', false);
    render();
  }
};

app.onhostcontextchanged = applyHostContext;

await app.connect();
applyHostContext(app.getHostContext?.() || {});
