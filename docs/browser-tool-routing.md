# 浏览器工具路由

Owner: `OPL Flow`
Purpose: `browser_tool_routing`
State: `active_workflow_support`
Machine boundary: 本文只定义默认选路与降级纪律；当前可用 connector、Skill、
浏览器会话、权限和操作结果仍以各工具的 fresh runtime readback 为准。

本文是 OPL Flow 的浏览器操作路由。目标不是减少工具数量，而是让同一类任务每次都走同一条路径，并让切换有明确原因。

## 总原则

1. **先判断是否真的需要浏览器**：如果目标是读取、查询、创建或修改结构化资源，先检查是否有专用 connector、API 或 CLI。浏览器只负责它们无法完成的 UI 工作。
2. **先确定状态边界，再选工具**：是否要复用用户当前登录态、是否需要隔离会话、是否需要重复执行，比“哪个工具看起来更强”更重要。
3. **一次任务只选一个主工具**：只有遇到文档中列出的能力缺口才降级；不能因为一次点击失败就随机换工具。
4. **凭据不迁移**：不把密码、Cookie、session、浏览器 profile 或 token 写入仓库，也不为了切换工具复制登录态。
5. **提交、发布、上传和高影响操作仍按各自确认与安全规则执行**：工具路由不扩大用户授权。

## 固定优先级

| 场景 | 首选 | 允许降级或替代 | 不应默认使用 |
| --- | --- | --- | --- |
| 有专用 connector/API/CLI 的语义操作 | connector/API/CLI | UI 仅处理缺失的交互 | 任意浏览器自动化 |
| 用户说“操作我现在打开的 Chrome”、要求当前标签页、扩展或已有登录态 | `chrome:control-chrome` | 用户明确同意后改用内置 Browser；若只是 API 任务则回到 connector/API/CLI | Playwright、agent-browser |
| 用户明确要求 Codex 内置 Browser，或没有指定浏览器的一次性网页交互 | `browser:control-in-app-browser` | 未指定浏览器且内置 Browser 不可用时，按 Browser skill 的运行时选择 Chrome；明确指定内置 Browser 时不可擅自替换 | Playwright、agent-browser |
| 重复执行、批量表单、回归验证、网页应用开发调试 | Playwright | 页面只支持 CLI/远程 Chromium 时用 agent-browser；需要真实桌面交互时用 Computer Use | Chrome 当前会话、内置 Browser临时操作 |
| agent-browser 专项能力：CLI 会话、远程 Chromium、Electron、其内置 dogfood/derive-client 等 | `agent-browser` | 回到 Playwright 仅在需要 Playwright 生态或测试产物时 | 把它当作所有网页任务的默认入口 |
| 原生桌面应用、系统文件选择器、拖放、富文本/画布等 DOM 无法可靠表达的交互 | `computer-use:computer-use` | 先回到专用 API/CLI；网页 DOM 稳定后回到主浏览器工具 | 用 Computer Use 代替普通表单自动化 |
| 互联网调研、网页阅读、社交平台或 GitHub 检索 | `agent-reach` 或对应专用 connector/API/CLI | 只有需要视觉确认或登录后 UI 操作时才启用 Browser | 用完整浏览器自动化做纯检索 |

## 表单与杂志编辑

### 一次性操作或人工确认提交

- 用户要求继续当前页面、复用已有编辑登录态或当前 Chrome 标签页：使用 `chrome:control-chrome`。
- 用户没有指定浏览器，也没有现成登录态要求：使用 Codex 内置 Browser，保持会话隔离。
- 表单包含文件上传、富文本编辑器、拖放或系统对话框时，仍先在选定浏览器中完成；只有 DOM/浏览器 API 无法可靠完成时，才切到 Computer Use（且仅限其支持的本机桌面）。
- 发送、提交、发布、上传前检查目标、内容和授权；工具切换不能绕过确认要求。

### 重复或可测试的编辑流程

- 需要稳定重跑、批量填写、字段校验、回归或截图/trace 产物：使用 Playwright。
- 登录由用户在受控环境中完成；不得在脚本中硬编码密码或把浏览器 profile 复制到其他工具。
- Playwright 遇到页面结构变化时，先重新 snapshot/定位并记录失败；不要立刻切到 agent-browser。
- 仅当目标实际是远程 Chromium、CLI 会话或 Electron 应用时，才选择 agent-browser。

## 降级链

```text
专用 connector/API/CLI
  -> 明确的 Chrome / Codex 内置 Browser
  -> Playwright（重复、回归、可测试流程）
  -> agent-browser（CLI/远程 Chromium/Electron 专项）
  -> Computer Use（原生桌面或视觉交互）
```

这不是无条件的线性重试链：

- 用户明确指定浏览器时，保持该选择；认证失败应要求用户在该浏览器完成登录，不能擅自换浏览器。
- 未指定浏览器时，Browser runtime 可以按可用性选择内置 Browser 或 Chrome；这不等于后续可以随机切换。
- Playwright 的 selector 失败先重新获取页面状态；agent-browser 的 accessibility ref 失效先重新 snapshot；两者都不能用来掩盖页面或权限根因。
- Computer Use 不作为远程 Windows/WSL 浏览器的通用补救工具；远程节点应优先使用目标节点可用的 Browser/Playwright/agent-browser 能力，并报告环境缺口。
- 登录态、上传能力、视觉能力或目标平台不可用时，报告具体 blocker，而不是声称流程完成。

## 快速决策表

```text
目标是结构化资源？                  -> connector/API/CLI
必须使用当前 Chrome 登录态/标签页？  -> chrome:control-chrome
一次性网页交互且未指定浏览器？      -> browser:control-in-app-browser
需要重复、批量、回归或测试产物？     -> Playwright
目标是远程 Chromium/CLI/Electron？   -> agent-browser
需要原生桌面、文件对话框或视觉坐标？ -> Computer Use
只是互联网搜索/阅读/调研？          -> agent-reach 或专用检索工具
```

## 任务记录要求

涉及登录态、复杂编辑器、上传或视觉验收时，最终说明：主工具、触发的降级原因、是否复用现有会话、实际验证了什么、尚未验证什么。普通网页读取不需要写长报告。
