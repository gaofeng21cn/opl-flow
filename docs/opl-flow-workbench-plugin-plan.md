# OPL Flow 控制塔插件与跨载体人机交互落地规划（SSOT）

Owner: `opl-flow`  
Consumers: `one-person-lab-app` / `opl-studio` / `opl-dsh`  
State: `approved_architecture_plan`

本文定义 **OPL Flow 在 OPL App 与 OPL DSH 中的一级侧栏插件（「更多」收纳）落地规划**，解决多载体统一零 Token 自动路由上线后“脱离单次对话的全局控制台入口”缺口，并严格划定与 `智能体协作（Team）`、`Superagent 工单台` 的三层产品边界。

---

## 1. 背景与设计目标

随着 OPL Flow 落地**统一零 Token 多载体事件路由器**（`opl-flow up --bridge auto`），同一个后台路由器已经能够在一份 Beads/Dolt 总账下同时协调 Codex、Google AntiGravity 与 OPL DSH 活跃会话，并执行工作区防撞车保护。

此前 OPL Flow 只通过 `opl-package.json` 的 `ui.mcp_apps`（`ui://opl-flow/decision-dashboard.html`）与 `ui.declarative.views`（`runtime.detail`）向宿主暴露交互界面，存在一个核心使用断点：**用户必须先在某个宿主里打开/选中一段对话，才能调起 MiniApp 查看全局看板**。

本规划将 OPL Flow 的人机交互入口补齐为**双平面协同**：
1. **全局控制塔平面（新增）**：以标准一级插件形式挂载在 OPL App 与 OPL DSH 首页侧栏的**「更多」**菜单中（默认不占用常驻主导航栏），随时脱离单次对话全局查看并拍板。
2. **对话内工作台平面（保留互补）**：保留会话内标准 MCP App（`ui://opl-flow/decision-dashboard.html`）与 `runtime.detail` 贡献视图，用于当前线程内的上下文联动操作。

---

## 2. 核心定位切分：控制塔 vs 主对话

**硬性原则：OPL Flow 一级侧栏页只做「控制塔 / 决策看板」，绝不自建第二套聊天输入框或第二份线程存储。**

| 职责 | 归属平面 | 说明 |
| :--- | :--- | :--- |
| 跨载体 Beads 总账概览、待拍板事项、待批归档、外部阻塞、待排期目标 | **OPL Flow 总控台（侧栏「更多」）** | 消费 `opl-flow.decision.v1#dashboard` 净化投影 |
| 三载体活跃会话感知（Codex / AntiGravity / OPL DSH）与工作区防撞车占用 | **OPL Flow 总控台（侧栏「更多」）** | 展示各工作区当前持有者与活跃载体标识 |
| 后台零 Token Router 服务状态与手动触发一轮评估（`tick`）、快速投递任务/批准归档 | **OPL Flow 总控台（侧栏「更多」）** | 复用 `opl-flow.decision.v1#send / approve / tick / service` |
| 需要针对某个目标展开长程多轮推理、改代码或交互式主控讨论 | **宿主原生对话（Codex / AntiGravity / OPL DSH）** | 从控制塔条目点击“在原生会话继续/新建”，一键拉起或聚焦宿主原生对话，不重复造聊天壳 |

---

## 3. 双宿主落地架构

### 3.1 OPL App（`opl-studio`）侧：Tier 2 侧栏扩展（首选完整体）

遵循 OPL App [插件 UI、设置接入与全插件理想态标准](https://github.com/gaofeng21cn/one-person-lab-app/blob/main/docs/product/gui/plugin-ui-and-settings-standard.md)：

1. **扩展包形态与宿主边界**：严格遵循 Framework v2 架构（见 `one-person-lab/docs/architecture.md` 与 `status.md`）——由 **Studio（DSH/Cordis）**承载交互界面与插件组合，**Framework `opld`** 仅通过公开本地 JSON-RPC 提供状态投影与动作执行。在 `opl-studio/plugins/extensions/` 新增标准 Tier 2 DSH Client 插件 `@gaofeng21cn/opl-flow-workbench`（包裹 `PluginErrorBoundary`，仅消费公开 `@gaofeng21cn/opl-plugin-ui-kit` 与受控宿主投影，零 `vendor/` 相对直连）。
2. **侧栏注册与默认收纳**：
   - 向 `sidebar.panellist` 注册 `id: "opl-flow"`、`order: 34`（位于 `workspace`/`schedules` 与 `teams`/`superagent` 邻近区间），显示名 `OPL Flow 总控` / `OPL Flow`。
   - 纳入 `app-product-profile.json` 的 `default_unpinned_panel_ids`，**默认折叠于侧栏「更多」菜单**，不影响首页主侧栏默认的 4 个固定入口（应用管理、运行状态、资料空间、工作区）；用户若重度使用，可点击「更多」里的图钉一键置顶。
3. **条件显隐原则（零打扰）与生命周期命令**：
   - 宿主通过 `opld` 公开 RPC **`app.state.get`** 读取 `application_management` / 已安装启用 Package 状态投影：仅当用户已安装并启用 `opl-flow` Package 时注册或显示 `opl-flow` 侧栏入口；未安装 `opl-flow` 的普通用户完全不可见，也不启动任何后台轮询。
   - `opl-flow` 自身及关联舰队的安装、修复与同步统一使用 Framework v2 CLI **`opl pack ensure` / `opl pack sync`**（及只读诊断 `opl pack list` / `opl pack inspect`），**严禁依赖已删除的 v1 CLI 命令**。
4. **控制面 RPC 与跳转**：
   - 数据读写统一经 Framework `opld` 公开 RPC 边界流转：**`app.contribution.read`** 读取 `opl-flow.decision.v1#dashboard` 投影，**`app.action.execute`** 执行已投影动作（`send` / `approve` / `tick` / `service`），背后由 `app-contribution-adapter.json` 与 `opl_app_contribution.py` 承接；
   - 点击“拉起新会话接管”或“跳转活跃会话”时，通过 Studio DSH 宿主桥接直接打开对应工作区的原生 Codex 会话或提示当前持有载体（AntiGravity / DSH）。

### 3.2 OPL DSH（`@one-person-lab/dsh-opl`）侧：轻量条件入口

遵循 OPL DSH「轻量化公式：独立官方增强套件、不强依赖 Framework `opld`」定位（详见 `opl-dsh` 仓 `docs/opl-flow-workbench-integration.md`）：

1. **严格条件显隐**：
   - 启动时仅做轻量只读探测（检查 `~/.config/opl-flow/instance.json` 及本机 `opl-flow` 可执行入口是否存在）；
   - **未安装或未初始化 `opl-flow` 实例时**：侧栏「更多」完全不注册该条目，零背景进程、零多余菜单、零异常报错，也不依赖任何已删除的 Framework v1 CLI。
2. **已绑定实例时的轻量复用**：
   - 检测到本机已有有效 `opl-flow` 实例时，在 `@one-person-lab/dsh-opl` 客户端通过 `sidebar.panellist` 注册 `id: "opl-flow"`（并配置默认 unpinned 折叠进「更多」）。
   - 前端直接复用与 `decision-dashboard` 同源的精简视图原语或嵌入本地静态 dashboard 视图，后端通过增强层 Remote 调用 `python3 <flow_root>/scripts/opl_app_contribution.py` 消费同一份总账与路由真相，**禁止在 OPL DSH 内复制 Beads 状态存储或规则逻辑**。
   - **原生会话接力**：选中目标点击“在 DSH 中执行”时，直接创建或打开 DSH 原生会话（透传目标 `bead_id`、工作区路径与 `opl_dsh_bridge.py` 约定的载体提示），在 DSH 对话中继续推进。

---

## 4. 三层协作心智与防混淆规范

OPL App 的「更多」菜单及文档统一采用**强场景化中文命名**，严禁裸露模糊的英文概念导致用户在 `OPL Flow`、`Superagent` 与 `Team` 之间迷失：

| 侧栏入口名称 | 底层插件 / 包 | 面向谁 / 解决什么问题 | 核心抽象 | 默认位置与可见性 |
| :--- | :--- | :--- | :--- | :--- |
| **智能体协作** | `opl-team-bots`（官方 DSH Team） | **当前这一次对话内**的多角色组队分工 | `Lead → Teammates + 会话共享任务板` | 收于「更多」；随 App/DSH 协作开关按需启停 |
| **OPL Flow 总控** | `opl-flow` + `@gaofeng21cn/opl-flow-workbench` | **“你自己”**跨 Codex / AntiGravity / DSH 与多机器的长期目标总账、防撞车与自动路由 | `Objective (Bead) → Slice/Attempt → Owner 验收` | 收于「更多」；**仅安装/绑定 `opl-flow` 时可见** |
| **Superagent 工单台** | `opl-superagent`（DSH 原型独立托管） | **“外部来单”**（GitHub / 飞书）按策略自动接单、修复与回帖的无人值守值班 | `Source → Policy → Ticket → Assignment` | 收于「更多」；默认停机，未配来源与策略不接单 |

**防混淆页面护栏**：
1. 三个页面的顶部简介与空态均须用一句话写清“我管什么、不管什么”，并给出相邻入口指引（例如在 Superagent 页提示：个人跨工具长期任务请使用「OPL Flow 总控」）。同时与首页主侧栏的**「运行状态（Runtime）」**明确区分：「运行状态」展示 Framework `Runway` 的本机领域阶段任务，「OPL Flow 总控」管理个人跨 Codex / AntiGravity / DSH 与多机器 Fleet 的 Beads/Dolt 长期目标总账与自动路由。
2. 三者状态完全隔离：`OPL Flow` 只写 Beads/Dolt；`Superagent` 只写 `$DSH_HOME/opl-superagent`；`智能体协作` 只写 `$DSH_HOME/opl-collaboration` 与 Codex 线程。

---

## 5. 数据与动作契约增量清单

现有 [app-contribution-adapter.json](../app-contribution-adapter.json) 与 [opl_app_contribution.py](../scripts/opl_app_contribution.py) 已提供以下稳定入口：
- 读：`opl-flow.decision.v1#dashboard`（已含 `service`、`counts`、`inbox`、`active_sessions`、`items`、`validation_errors`）
- 写：`opl-flow.decision.v1#send`（支持 `executor: codex | antigravity | dsh`）、`opl-flow.decision.v1#approve`、`opl-flow.decision.v1#tick`，以及 CLI `service`（`up`/`down`）

后续落地控制塔 UI 时，须在 `opl_app_contribution.py`、`opl_session_discovery.py`、`opl-package.json` 与 `app-contribution-adapter.json` 补齐以下**向后兼容的可选字段与动作**：
1. **服务启停与派单契约对齐**：在 `app-contribution-adapter.json` 与 `opl-package.json` 补齐 `opl-flow.decision.v1#service`（`action: up | down`, `bridge: auto | codex | antigravity`, `confirmed: true`），同时在 `opl-flow.decision.v1#send` 的 schema 中显式声明 `executor`（`codex | antigravity | dsh`）与可选 `session_ref`，使控制塔与 `opld` `app.action.execute` 校验完全一致。
2. **受信任本机跳转元数据与脱敏投影分口径**：默认读取保持严格脱敏（仅返回 `workspace_label` 与截断 `session_ref`，不暴露本机绝对路径与完整 ID）；仅当本机可信控制面传入 `include_local_navigation: true` 与 `host_carrier`（`codex | antigravity | dsh`）时，返回 `workspace_path`、`session_id` / `thread_id`、非正文只读标题与只读能力标记 `jump_mode`（`native_switch | launch_new | external_focus_only`），防止对跨宿主会话显示无效跳转按钮，且原始定位信息严禁进入日志、诊断或 Linear 投影。
3. **条目载体徽标（只读）**：`items[]` 携带 `execution_carrier`、`preferred_adapter`、`bound_session_ref` 与（受信任本机模式下的）`jump_mode`，用于控制塔列表展示当前执行载体标签。
4. **单源 UI 复用纪律**：OPL DSH（P3）通过轻量包装复用与标准决策看板一致的数据与展示模型，不复制第二套 Beads 状态或演进第三套平行看板逻辑。

---

## 6. 分阶段实施路线与验收门禁

| 阶段 | 核心交付 | 验收门禁 |
| :--- | :--- | :--- |
| **P1 · 控制面契约补齐（`opl-flow`）** | `app-contribution-adapter.json` 补充 `opl-flow.decision.v1#service`；`opl_app_contribution.py` 补全 `active_sessions` 与 `items` 跳转元数据，保持与 `decision-dashboard` MCP Server 共用同一函数；对接 Framework v2 `opld` 公开 RPC（`app.contribution.read` / `app.action.execute`）与 `opl pack ensure` / `opl pack sync` | `scripts/verify.sh full` 全绿；单测验证未绑定实例时返回干净 `unavailable`，且不泄露凭据、私有正文或引用已删除的 v1 CLI |
| **P2 · OPL App Tier 2 侧栏插件（`opl-studio` / `one-person-lab-app`）** | 在 Studio（DSH/Cordis）新增 `@gaofeng21cn/opl-flow-workbench`，注册 `sidebar.panellist`（`id: "opl-flow"`, 默认收于「更多」），经 `opld` 公开 RPC `app.state.get`、`app.contribution.read` 与 `app.action.execute` 实现条件显隐、总账看板、三载体活跃会话感知、快捷投递/批准/`tick`/启停，以及一键拉起或切换宿主原生 Codex 对话 | 通过 `plugin-conformance-gate`、`ui-contribution-composition`、light/dark 对比度及未安装 `opl-flow` 零露出回归测试 |
| **P3 · OPL DSH 条件入口（`opl-dsh`）** | 在 `@one-person-lab/dsh-opl` 增加轻量实例探测与「更多」条件挂载，复用 `opl_app_contribution.py` 与标准界面，支持在 DSH 会话接力目标 | 未装 `opl-flow` 时零 UI/零报错/零后台进程；已绑定实例时通过隔离官方桌面资格验证（`qualify-official-runtime`） |
| **P4 · 三层命名收敛与实机闭环验收** | 在 OPL App 统一落地「智能体协作 / OPL Flow 总控 / Superagent 工单台」中文命名与空态边界指引；完成同机 Codex + AntiGravity + OPL DSH 真机看板联动验证 | 在已安装态与未安装态双场景实机回读截图，确认防撞车提示、跨载体投递与归档回读一次闭环 |
