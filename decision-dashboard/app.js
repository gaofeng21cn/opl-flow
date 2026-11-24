import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
} from '@modelcontextprotocol/ext-apps';

const app = new App(
  {
    name: 'opl-flow-decision-dashboard',
    version: typeof __OPL_FLOW_VERSION__ === 'string' ? __OPL_FLOW_VERSION__ : '0.1.82',
  },
  { tools: { listChanged: false } },
  { strict: true },
);

const root = document.getElementById('app');

const TABS = [
  { id: 'needs_action', label: '需你拍板', tone: 'warning', desc: '等待人工回复或决策的目标。' },
  { id: 'safe_to_archive', label: '待批归档', tone: 'success', desc: '已完成收口，需明确人工确认后才会归档。' },
  { id: 'active_objectives', label: '进行中', tone: '', desc: '当前正在由控制器或 Worker 推进的目标。' },
  { id: 'blocked', label: '外部阻塞', tone: 'danger', desc: '等待外部事件、CI 或依赖解除的目标。' },
  { id: 'backlog', label: '待排期', tone: 'neutral', desc: '暂存冻结，待排入执行队列的目标。' },
  { id: 'pending_events', label: '待处理事件', tone: 'neutral', desc: '已进入事件收件箱、等待 Router 消费的事件。' },
];

const state = {
  payload: null,
  focus: {},
  activeTab: '',
  selectedId: '',
  busy: false,
  bannerText: '',
  bannerError: false,
  newTitle: '',
  newMessage: '',
  newMode: 'active',
  newNow: false,
  replyMessage: '',
  replyNow: false,
  approverName: 'owner',
  dialogMode: null,
  dialogTarget: null,
};

let readGeneration = 0;

function record(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
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

function itemsForTab(inbox, tabId) {
  const list = inbox[tabId];
  return Array.isArray(list) ? list.filter((item) => item && typeof item === 'object') : [];
}

function chooseDefaultTab(inbox) {
  if (state.focus.tab && TABS.some((t) => t.id === state.focus.tab)) {
    return state.focus.tab;
  }
  for (const tab of TABS) {
    if (itemsForTab(inbox, tab.id).length > 0) return tab.id;
  }
  return 'needs_action';
}

function itemKey(entry, tabId) {
  return tabId === 'pending_events' ? String(entry.event_id || '') : String(entry.bead_id || '');
}

function syncModelContext(data, activeTab, selectedEntry) {
  if (!app.getHostCapabilities?.()?.updateModelContext) return;
  const navigation = {
    ...instanceArg(),
    tab: activeTab,
    ...(selectedEntry && activeTab !== 'pending_events' && selectedEntry.bead_id
      ? { bead_id: selectedEntry.bead_id }
      : {}),
  };
  const label = selectedEntry
    ? activeTab === 'pending_events'
      ? `正在查看待处理事件 ${selectedEntry.event_id}`
      : `正在查看 OPL Flow 目标 ${selectedEntry.bead_id}（${selectedEntry.title || ''}）`
    : `正在查看 OPL Flow 决策看板（${TABS.find((t) => t.id === activeTab)?.label || activeTab}）`;
  app
    .updateModelContext({
      content: [{ type: 'text', text: label }],
      structuredContent: {
        navigation,
        instance_name: data.instance_name || null,
        active_tab: activeTab,
        selected_bead_id: activeTab !== 'pending_events' ? selectedEntry?.bead_id || null : null,
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
    const payload = await callServer('open_opl_flow_dashboard', {
      ...instanceArg(),
      ...(state.activeTab ? { tab: state.activeTab } : {}),
      ...(state.selectedId && state.activeTab !== 'pending_events' ? { bead_id: state.selectedId } : {}),
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
  const inbox = record(data.inbox);
  if (!state.activeTab || !TABS.some((t) => t.id === state.activeTab)) {
    state.activeTab = chooseDefaultTab(inbox);
  }
  if (state.focus.bead_id) {
    for (const tab of TABS) {
      if (tab.id === 'pending_events') continue;
      if (itemsForTab(inbox, tab.id).some((item) => item.bead_id === state.focus.bead_id)) {
        state.activeTab = tab.id;
        state.selectedId = state.focus.bead_id;
        break;
      }
    }
  }
}

function statusBadgeForService(svc) {
  if (svc.running) return '<span class="badge success">后台事件引擎：运行中</span>';
  if (svc.installed) return '<span class="badge warning">后台事件引擎：已安装未启动</span>';
  return '<span class="badge neutral">后台事件引擎：未启动</span>';
}

function renderDetailPanel(activeTab, selectedEntry) {
  if (!selectedEntry) {
    return `<div class="empty-state"><div><strong>未选中条目</strong><p>在中间列表中选择一条目标或事件，即可查看详情并执行决策动作。</p></div></div>`;
  }
  if (activeTab === 'pending_events') {
    return `<div class="detail-panel">
      <header class="stage-header">
        <div>
          <h2>事件详情</h2>
          <p class="task-card-id">${escapeHtml(selectedEntry.event_id)}</p>
        </div>
        <span class="badge neutral">${escapeHtml(selectedEntry.event_type || 'event')}</span>
      </header>
      <dl class="detail-meta">
        <div class="detail-row"><dt>关联目标</dt><dd>${escapeHtml(selectedEntry.objective_id || '—')}</dd></div>
        <div class="detail-row"><dt>来源</dt><dd>${escapeHtml(selectedEntry.source || '—')}</dd></div>
        <div class="detail-row"><dt>状态</dt><dd>${escapeHtml(selectedEntry.status || 'pending')}</dd></div>
        <div class="detail-row"><dt>创建时间</dt><dd>${escapeHtml(selectedEntry.created_at || '—')}</dd></div>
        <div class="detail-row"><dt>摘要</dt><dd>${escapeHtml(selectedEntry.summary || '无附加摘要')}</dd></div>
      </dl>
      <div class="inline-actions">
        <button class="dsh-button primary" type="button" data-action="tick" ${state.busy ? 'disabled' : ''}>立即评估此队列</button>
      </div>
    </div>`;
  }

  const remaining = Array.isArray(selectedEntry.remaining) ? selectedEntry.remaining : [];
  const isArchiveCandidate = activeTab === 'safe_to_archive';
  return `<div class="detail-panel">
    <header class="stage-header">
      <div>
        <h2>${escapeHtml(selectedEntry.title || selectedEntry.bead_id)}</h2>
        <p class="task-card-id">${escapeHtml(selectedEntry.bead_id)}</p>
      </div>
      <span class="badge ${isArchiveCandidate ? 'success' : activeTab === 'needs_action' ? 'warning' : activeTab === 'blocked' ? 'danger' : ''}">${escapeHtml(TABS.find((t) => t.id === activeTab)?.label || activeTab)}</span>
    </header>
    <dl class="detail-meta">
      <div class="detail-row"><dt>账本状态 / 执行模式</dt><dd>${escapeHtml(selectedEntry.status || '—')} / ${escapeHtml(selectedEntry.execution_mode || '未设置')}</dd></div>
      ${selectedEntry.first_blocker ? `<div class="detail-row"><dt>当前阻塞</dt><dd>${escapeHtml(selectedEntry.first_blocker)}</dd></div>` : ''}
      ${selectedEntry.next_action ? `<div class="detail-row"><dt>建议下一步</dt><dd>${escapeHtml(selectedEntry.next_action)}</dd></div>` : ''}
      <div class="detail-row">
        <dt>剩余工作（${remaining.length}）</dt>
        <dd>${remaining.length ? `<ul class="remaining-list">${remaining.map((r) => `<li>${escapeHtml(r)}</li>`).join('')}</ul>` : '无剩余未完成项'}</dd>
      </div>
    </dl>
    ${
      isArchiveCandidate
        ? `<section class="action-form" aria-labelledby="archive-heading">
            <h2 id="archive-heading">归档人工确认门禁</h2>
            <p class="field-hint">OPL Flow 永不自动归档目标。核对上方终态证据与剩余工作为空后，点击下方按钮进入确认对话框。</p>
            <div class="inline-actions">
              <button class="dsh-button primary" type="button" data-open-approve="${escapeHtml(selectedEntry.bead_id)}" ${state.busy ? 'disabled' : ''}>批准归档…</button>
            </div>
          </section>`
        : `<form class="action-form" id="reply-form" aria-labelledby="reply-heading" novalidate>
            <h2 id="reply-heading">拍板回复 / 追加指示</h2>
            <div class="field">
              <label for="reply-message">指示内容 <span aria-hidden="true">*</span></label>
              <textarea id="reply-message" name="reply_message" class="dsh-input" required maxlength="4000" enterkeyhint="send" aria-describedby="reply-help reply-error" placeholder="输入拍板结论、方案选择或追加约束…">${escapeHtml(state.replyMessage)}</textarea>
              <span id="reply-help" class="field-hint">将作为人类事件写入队列（支持 Cmd/Ctrl + Enter 提交）。</span>
              <span id="reply-error" class="field-error" role="alert"></span>
            </div>
            <div class="checkbox-row">
              <input id="reply-now" name="reply_now" type="checkbox" ${state.replyNow ? 'checked' : ''}>
              <label for="reply-now">发送后立即触发一轮状态评估</label>
            </div>
            <div class="inline-actions">
              <button class="dsh-button primary" type="submit" ${state.busy ? 'disabled' : ''}>${state.busy ? '发送中…' : '发送回复'}</button>
            </div>
          </form>`
    }
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
        <h1 id="confirm-dialog-title">${starting ? '确认启动后台事件引擎' : '确认停止后台事件引擎'}</h1>
        <p class="dialog-summary">${
          starting
            ? '将在本机注册并启动 OPL Flow 后台事件引擎（LaunchAgent / systemd user），按事件增量触发控制流，无事件时不消耗模型额度。'
            : '将停止并卸载本机 OPL Flow 后台事件引擎服务；已有账本与未处理事件会完整保留。'
        }</p>
        <div class="dialog-actions">
          <button class="dsh-button quiet" type="button" data-dialog-cancel autofocus>取消</button>
          <button class="dsh-button primary" type="button" data-dialog-confirm ${state.busy ? 'disabled' : ''}>${state.busy ? '执行中…' : starting ? '确认启动' : '确认停止'}</button>
        </div>
      </div>
    </dialog>`;
  }
  return '';
}

function render() {
  const { result, data } = dashboardData();
  const svc = record(data.service);
  const counts = record(data.counts);
  const inbox = record(data.inbox);

  if (!state.payload) {
    root.innerHTML = `<header class="topbar">
      <div class="topbar-copy"><div class="family-heading"><h1>决策看板</h1><span class="family-label">OPL Apps · OPL Flow</span></div></div>
      <div class="topbar-actions"><button class="dsh-button" type="button" data-refresh>读取看板</button></div>
    </header>
    <div></div>
    <div class="loading-state" role="status" aria-live="polite">正在等待宿主提供 OPL Flow 决策看板数据…</div>`;
    root.querySelector('[data-refresh]')?.addEventListener('click', () => void refresh());
    return;
  }

  if (result.state === 'unavailable') {
    root.innerHTML = `<header class="topbar">
      <div class="topbar-copy"><div class="family-heading"><h1>决策看板</h1><span class="family-label">OPL Apps · OPL Flow</span></div></div>
      <div class="topbar-actions"><button class="dsh-button" type="button" data-refresh>重新读取</button></div>
    </header>
    <div></div>
    <div class="error-state" role="alert"><div><strong>暂无法读取 OPL Flow 实例</strong><p>${escapeHtml(result.reason || '请先完成 OPL Flow 实例绑定。')}</p><button class="dsh-button primary" type="button" data-refresh>重试</button></div></div>`;
    root.querySelectorAll('[data-refresh]').forEach((btn) =>
      btn.addEventListener('click', () => void refresh()),
    );
    return;
  }

  const activeTab = TABS.some((t) => t.id === state.activeTab) ? state.activeTab : chooseDefaultTab(inbox);
  state.activeTab = activeTab;
  const activeTabMeta = TABS.find((t) => t.id === activeTab) || TABS[0];
  const entries = itemsForTab(inbox, activeTab);
  const selectedEntry =
    entries.find((entry) => itemKey(entry, activeTab) === state.selectedId) || entries[0] || null;
  state.selectedId = selectedEntry ? itemKey(selectedEntry, activeTab) : '';

  const serviceAction = svc.running ? 'down' : 'up';
  const serviceButtonLabel = svc.running ? '停止引擎' : '启动引擎';

  root.innerHTML = `<header class="topbar">
      <div class="topbar-copy">
        <div class="family-heading">
          <h1>决策看板</h1>
          <span class="family-label">OPL Apps · OPL Flow</span>
        </div>
        <div class="topbar-meta">
          ${data.instance_name ? `<span>实例：${escapeHtml(data.instance_name)}</span>` : ''}
          ${statusBadgeForService(svc)}
          <span class="badge ${counts.pending_events ? 'warning' : 'neutral'}">待处理事件：${Number(counts.pending_events || 0)}</span>
        </div>
      </div>
      <div class="topbar-actions">
        <button class="dsh-button" type="button" data-action="tick" ${state.busy ? 'disabled' : ''}>推进一轮</button>
        <button class="dsh-button quiet" type="button" data-open-service="${serviceAction}" ${state.busy ? 'disabled' : ''}>${serviceButtonLabel}</button>
        <button class="dsh-button quiet hide-narrow" type="button" data-fullscreen>展开</button>
        <button class="dsh-button" type="button" data-refresh ${state.busy ? 'disabled' : ''}>刷新</button>
      </div>
    </header>
    ${
      state.bannerText
        ? `<div class="status-banner ${state.bannerError ? 'error' : ''}" role="${state.bannerError ? 'alert' : 'status'}" aria-live="polite"><span>${escapeHtml(state.bannerText)}</span><button class="dsh-button small quiet" type="button" data-dismiss-banner>关闭</button></div>`
        : '<div hidden></div>'
    }
    <div class="workspace">
      <aside class="rail" aria-label="任务分类与新建">
        <section class="rail-section">
          <h2>状态视图</h2>
          <nav class="nav-list" aria-label="决策分类">
            ${TABS.map((tab) => {
              const count = Number(counts[tab.id] || 0);
              return `<button class="nav-button" type="button" data-tab="${tab.id}" aria-current="${tab.id === activeTab ? 'true' : 'false'}">
                <span>${escapeHtml(tab.label)}</span>
                <span class="badge ${count > 0 ? tab.tone : 'neutral'}">${count}</span>
              </button>`;
            }).join('')}
          </nav>
        </section>
        <form class="action-form" id="new-task-form" aria-labelledby="new-task-heading" novalidate>
          <h2 id="new-task-heading">投递新任务</h2>
          <div class="field">
            <label for="new-title">标题（可选）</label>
            <input id="new-title" name="title" type="text" class="dsh-input" maxlength="120" enterkeyhint="next" placeholder="留空将自动取正文首行" value="${escapeHtml(state.newTitle)}">
          </div>
          <div class="field">
            <label for="new-message">任务目标与要求 <span aria-hidden="true">*</span></label>
            <textarea id="new-message" name="message" class="dsh-input" required maxlength="4000" enterkeyhint="send" aria-describedby="new-message-help new-message-error" placeholder="例如：把登录接口超时重试补齐单测并整理改动说明…">${escapeHtml(state.newMessage)}</textarea>
            <span id="new-message-help" class="field-hint">写入总账并触发事件路由（支持 Cmd/Ctrl + Enter 提交）。</span>
            <span id="new-message-error" class="field-error" role="alert"></span>
          </div>
          <div class="field">
            <label for="new-mode">初始状态</label>
            <select id="new-mode" name="execution_mode" class="dsh-input">
              <option value="active" ${state.newMode === 'active' ? 'selected' : ''}>立即进入运行队列（active）</option>
              <option value="backlog" ${state.newMode === 'backlog' ? 'selected' : ''}>暂存待排期（backlog）</option>
            </select>
          </div>
          <div class="checkbox-row">
            <input id="new-now" name="now" type="checkbox" ${state.newNow ? 'checked' : ''}>
            <label for="new-now">创建后立即评估一轮</label>
          </div>
          <button class="dsh-button primary" type="submit" ${state.busy ? 'disabled' : ''}>${state.busy ? '投递中…' : '投递任务'}</button>
        </form>
      </aside>

      <section class="stage" aria-label="${escapeHtml(activeTabMeta.label)}">
        <div class="stage-header">
          <div>
            <h2>${escapeHtml(activeTabMeta.label)} <span class="badge ${entries.length ? activeTabMeta.tone : 'neutral'}">${entries.length}</span></h2>
            <p>${escapeHtml(activeTabMeta.desc)}</p>
          </div>
        </div>
        ${
          entries.length
            ? `<div class="card-list">${entries
                .map((entry) => {
                  const id = itemKey(entry, activeTab);
                  const isCurrent = id === state.selectedId;
                  if (activeTab === 'pending_events') {
                    return `<button class="task-card" type="button" data-select="${escapeHtml(id)}" aria-current="${isCurrent ? 'true' : 'false'}">
                      <div class="task-card-top">
                        <span class="task-card-id">${escapeHtml(entry.event_id)}</span>
                        <span class="badge neutral">${escapeHtml(entry.event_type || 'event')}</span>
                      </div>
                      <div class="task-card-title">目标：${escapeHtml(entry.objective_id || '全局')}</div>
                      <div class="task-card-note">${escapeHtml(entry.summary || entry.source || '')}</div>
                    </button>`;
                  }
                  const note = entry.first_blocker
                    ? `阻塞：${entry.first_blocker}`
                    : entry.next_action
                      ? `下一步：${entry.next_action}`
                      : entry.remaining_count
                        ? `剩余 ${entry.remaining_count} 项`
                        : '点击查看详情';
                  return `<button class="task-card" type="button" data-select="${escapeHtml(id)}" aria-current="${isCurrent ? 'true' : 'false'}">
                    <div class="task-card-top">
                      <span class="task-card-id">${escapeHtml(entry.bead_id)}</span>
                      <span class="badge ${activeTab === 'safe_to_archive' ? 'success' : activeTab === 'needs_action' ? 'warning' : activeTab === 'blocked' ? 'danger' : 'neutral'}">${escapeHtml(entry.status || activeTab)}</span>
                    </div>
                    <div class="task-card-title">${escapeHtml(entry.title || entry.bead_id)}</div>
                    <div class="task-card-note">${escapeHtml(note)}</div>
                  </button>`;
                })
                .join('')}</div>`
            : `<div class="empty-state"><div><strong>当前「${escapeHtml(activeTabMeta.label)}」为空</strong><p>${escapeHtml(activeTabMeta.desc)}</p></div></div>`
        }
      </section>

      <aside class="detail-rail" aria-label="条目详情与决策操作">
        ${renderDetailPanel(activeTab, selectedEntry)}
      </aside>
    </div>
    ${renderDialog()}`;

  bindEvents(data, activeTab, selectedEntry);
  syncModelContext(data, activeTab, selectedEntry);
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

function bindEvents(data, activeTab, selectedEntry) {
  root.querySelector('[data-refresh]')?.addEventListener('click', () => void refresh('已刷新最新状态。'));
  root.querySelector('[data-dismiss-banner]')?.addEventListener('click', () => {
    setBanner('', false);
    render();
  });
  root.querySelector('[data-fullscreen]')?.addEventListener('click', () => {
    const nextMode = app.getHostContext()?.displayMode === 'fullscreen' ? 'inline' : 'fullscreen';
    void app.requestDisplayMode({ mode: nextMode }).catch(() => {});
  });
  root.querySelectorAll('[data-tab]').forEach((btn) =>
    btn.addEventListener('click', () => {
      state.activeTab = btn.dataset.tab;
      state.selectedId = '';
      render();
    }),
  );
  root.querySelectorAll('[data-select]').forEach((btn) =>
    btn.addEventListener('click', () => {
      state.selectedId = btn.dataset.select;
      state.replyMessage = '';
      render();
    }),
  );
  root.querySelectorAll('[data-action="tick"]').forEach((btn) =>
    btn.addEventListener('click', () => void runTick()),
  );
  root.querySelector('[data-open-service]')?.addEventListener('click', (event) => {
    const action = event.currentTarget.dataset.openService;
    state.dialogMode = 'service';
    state.dialogTarget = { action };
    render();
  });
  root.querySelector('[data-open-approve]')?.addEventListener('click', () => {
    if (!selectedEntry) return;
    state.dialogMode = 'approve';
    state.dialogTarget = { bead_id: selectedEntry.bead_id, title: selectedEntry.title };
    render();
  });

  // New task form
  const newForm = root.querySelector('#new-task-form');
  const newTitleEl = root.querySelector('#new-title');
  const newMsgEl = root.querySelector('#new-message');
  const newMsgErr = root.querySelector('#new-message-error');
  const newModeEl = root.querySelector('#new-mode');
  const newNowEl = root.querySelector('#new-now');
  const validateNewMsg = attachFieldValidation(newMsgEl, newMsgErr, '请输入任务目标与要求。');
  newTitleEl?.addEventListener('input', (e) => { state.newTitle = e.target.value; });
  newMsgEl?.addEventListener('input', (e) => { state.newMessage = e.target.value; });
  newModeEl?.addEventListener('change', (e) => { state.newMode = e.target.value; });
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

  // Reply form
  const replyForm = root.querySelector('#reply-form');
  const replyMsgEl = root.querySelector('#reply-message');
  const replyErrEl = root.querySelector('#reply-error');
  const replyNowEl = root.querySelector('#reply-now');
  const validateReply = attachFieldValidation(replyMsgEl, replyErrEl, '请输入回复内容。');
  replyMsgEl?.addEventListener('input', (e) => { state.replyMessage = e.target.value; });
  replyNowEl?.addEventListener('change', (e) => { state.replyNow = e.target.checked; });
  replyMsgEl?.addEventListener('keydown', (e) => {
    if (e.isComposing) return;
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      replyForm?.requestSubmit();
    }
  });
  replyForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    if (state.busy || !selectedEntry) return;
    if (validateReply && !validateReply()) {
      replyMsgEl?.focus();
      return;
    }
    void submitReply(selectedEntry.bead_id);
  });

  // Native modal dialog wiring
  const dialog = root.querySelector('#confirm-dialog');
  if (dialog && typeof dialog.showModal === 'function') {
    if (!dialog.open) dialog.showModal();
    const approverInput = dialog.querySelector('#approver-input');
    const approverErr = dialog.querySelector('#approver-error');
    const validateApprover = attachFieldValidation(approverInput, approverErr, '请输入批准人标识。');
    approverInput?.addEventListener('input', (e) => { state.approverName = e.target.value; });
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
  setBanner('正在投递新任务…', false);
  render();
  try {
    const res = await callServer('opl_flow_send', {
      ...instanceArg(),
      ...(state.newTitle.trim() ? { title: state.newTitle.trim() } : {}),
      message: state.newMessage.trim(),
      execution_mode: state.newMode,
      now: state.newNow,
      request_id: crypto.randomUUID(),
    });
    state.newTitle = '';
    state.newMessage = '';
    state.busy = false;
    state.activeTab = state.newMode === 'backlog' ? 'backlog' : 'active_objectives';
    if (res.result?.bead_id) state.selectedId = res.result.bead_id;
    await refresh(res.result?.message || '已投递新任务。');
  } catch (error) {
    state.busy = false;
    setBanner(error?.message || '投递任务失败。', true);
    render();
  }
}

async function submitReply(beadId) {
  state.busy = true;
  setBanner(`正在向 ${beadId} 发送回复…`, false);
  render();
  try {
    const res = await callServer('opl_flow_send', {
      ...instanceArg(),
      objective_id: beadId,
      message: state.replyMessage.trim(),
      now: state.replyNow,
      request_id: crypto.randomUUID(),
    });
    state.replyMessage = '';
    state.busy = false;
    await refresh(res.result?.message || `已向 ${beadId} 发送回复。`);
  } catch (error) {
    state.busy = false;
    setBanner(error?.message || '回复发送失败。', true);
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
    await refresh(res.result?.message || '单轮状态评估完成。');
  } catch (error) {
    state.busy = false;
    setBanner(error?.message || '状态推进失败。', true);
    render();
  }
}

async function confirmServiceAction(action) {
  state.busy = true;
  setBanner(action === 'up' ? '正在启动后台事件引擎…' : '正在停止后台事件引擎…', false);
  render();
  try {
    const res = await callServer('opl_flow_router_service', {
      ...instanceArg(),
      action,
      confirmed: true,
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
