---
name: coordinate-concurrent-tasks
description: Coordinate multiple Codex conversations, agents, repositories, or worktrees so unfinished work stays ACTIVE, independent work proceeds in parallel, multi-machine task branches stay recoverable, conflicts resolve against fresh SSOT at integration, only fully authoritative work becomes SAFE_TO_ARCHIVE, and actual thread archival requires fresh user acceptance. Use when reorganizing active threads, eliminating wait or blocked states, assigning parallel owners or subagents, resolving dependency or write-set overlap, finding unowned task gaps, reviewing archive safety, or accelerating multi-task delivery. 适用于多对话并发、多机远端同步、等待与锁处理、主线吸收、任务缺口审计和需用户验收的安全归档。
---

# 并发任务协调

## 核心原则

采用 `parallel_work_serialized_integration`：并行完成可独立推进的工作，只在最终共享 mutation 的短临界区串行。

### 用户所说的 SSOT

区分两种 SSOT，不能混用：

- **指令 SSOT**：当前用户的最新直接指令，决定 objective、scope 和终态；
- **产物 SSOT**：用户说“更新为 SSOT”“落实为 SSOT”时指定的真实 authority。除非用户明确指定其他 authority，Git 产物的 SSOT 就是远端 canonical `main` 的回读结果。

因此，worktree、本地分支、task branch、远端 task ref、PR、候选提交、checkpoint、测试通过或文档草稿都只能是开发或恢复证据，**绝不是产物 SSOT**。只有内容进入 canonical `main`、远端 commit/tree（必要时 blob）回读一致后，才能称已更新为 SSOT；否则必须报告为 `ACTIVE`/可恢复。

### 把内容判定为偏差之前先追溯 provenance

当前内容与旧规划、memory、交接摘要或 AI 偏好不一致，不足以证明它是偏差。修改前必须
先查明它如何形成：优先读取最新的用户直接指令，必要时再检查文档历史、blame、commit、
相关对话和 runtime readback。commit author 只能证明谁写入字节，不能单独证明谁作出了
产品决策；AI 写入的 commit 也可能是在落实用户后来明确提出的选择。

如果当前内容来自用户更晚的明确选择，该选择就是最新指令 SSOT，必须保留；与之冲突的
旧设计、memory、ledger、handoff 或 AI 判断应标记为 `stale`，不得把 authority “修正”
回旧方案。只有 provenance 仍不明确、且不同解释会实质改变终态时，才在 mutation 前向
用户澄清。

把任务生命周期、执行占用和用户可见标题分开。标题可使用五种状态：

- `ACTIVE`：当前确有 Agent/owner 推进可立即执行的工作；
- `NEEDS_ACTION`：下一步必须由用户登录、决策或授权，当前不占用 Agent；
- `BLOCKED`：下一步被外部事件或依赖阻止，当前不占用 Agent；
- `MONITORING`：长期工作台、主控或总账中的持续监督责任；只有真正的工作台/主控保留常驻对话，单纯的长期责任不需要空闲 thread；
- `SAFE_TO_ARCHIVE`：全部成果已进入真实 authority 并实际生效，证据闭合且 `remaining=[]`。

依赖、冲突、currentness drift、候选提交或普通失败不能自动把任务降为等待；先完成仍可执行的切片。只有存在不可替代的用户动作或外部事件时才使用 `NEEDS_ACTION`/`BLOCKED`，并写明谁需要做什么。不要使用含义不明的 `WAIT`、`HOLD`、`HANDOFF`、`CANDIDATE_ONLY` 或 `ARCHIVE_CANDIDATE`。

### 并行规模不是固定上限

- `ACTIVE` 对话、objective 数量和同时拥有 canonical mutation 权限的 writer 数量是三个不同概念；不能用一个 writer 数字限制所有独立对话。
- 并行规模按 fresh execution graph 动态决定：每条 lane 只要有唯一 owner、可立即执行的 next action、边界明确的 write set、可恢复 checkpoint，且不争用同一稀缺资源，就应并行推进。
- 只有真实的共享 mutation、宿主容量、受保护权限、安全边界或外部服务配额可以限制并行；同一 repo 的 `main` 吸收只在最终短临界区串行，不构成开发期总锁。
- `4`、`8` 或其他数字只能作为当轮资源规划参考，永远不是全局 `ACTIVE` 上限。若当前资源允许更多独立 lane，必须说明 write-set/resource 证据后继续并行，而不是把它们改成等待。

### 执行连续性

- 控制面分三层：全局 Supervisor 只持有总账、宏观调控和异常兜底；产品总控持有本产品的 objective graph、结果验收、首个真实断点修复和续派；executor 只持有一个有界切片。产品总控是逻辑责任，不要求另建一个常驻轮询对话。
- executor 在可恢复 checkpoint、terminal 或 real blocker 时主动回调产品总控；产品总控在同一执行轮次验收、修复或续派。回调只是触发与 provenance，不替代 checkpoint、canonical、runtime 或 cleanup 证据。
- 全局 Supervisor 不按 heartbeat 常规轮询产品 executor。只有 executor 失联、应有 callback 缺失或跨 objective owner/write-set 冲突时，才对精确目标执行兜底回读；无事件时不读取产品、不续派、不写语义状态。
- `ACTIVE` 标题或总账登记不等于活跃执行。每个 `ACTIVE` objective 必须同时有 live execution owner、可立即执行的 `next_action` 和本轮推进证据。
- **Active-progress invariant**：只有同时满足以下条件时才可保留 `ACTIVE`：存在唯一 live owner/execution owner；精确 write set 已登记；`next_action` 现在即可执行；当前 worktree/branch/checkpoint 可回读；最近一轮包含真实推进证据（实现、验证、commit、checkpoint、吸收、安装生效、发布回读或清理之一）。标题、spinner、未归档状态、callback、候选 commit 或测试通过都不能单独证明活跃执行。
- 子任务、callback、测试或一次 operation 结束后，产品总控必须在同一轮验收结果并立即继续、修复首个真实断点或重分配；不得停在回调、候选、失败回执或等待另一个对话自行醒来。
- 一个切片完成后不得因等待冲突而停住：owner 应先完成本地等价门禁，commit 并 push 可恢复 task checkpoint，回读远端 SHA/tree/blob，再把精确 integration boundary 交给唯一 Integrator；冲突只在 fresh main 的 canonical integration 临界区解决。
- currentness drift 由原 owner 基于 fresh SSOT 做 semantic replay 并继续验证，不以漂移为理由进入等待或遗弃责任。
- fail-closed 只终止当前 operation，不终止 objective。若没有不可替代的权限、外部输入或安全边界，主控修复断点后发起新的合法 operation，并持续到 `SAFE_TO_ARCHIVE`。
- 每个非根 worktree 都必须有 `thread_id`、objective、该切片 owner、execution owner、`next_action` 与精确 write set 的 ACTIVE 收据；只有 `scripts/worktree_lifecycle.py register` 写入的全局 ledger 才构成 owner 登记，旁路 `.task-receipts` 或自定义 JSON 只作补充证据。不同 worktree 的重叠 write set 记录为 `integration_overlaps`，不阻止注册或开发；共享 checkout、canonical 吸收和外部 mutation 仍必须有短时唯一 operation owner。用 `checkpoint` 建立远端恢复点，用 `status` 核对 holder、吸收、远端 task ref 与 canonical wire。无 owner 的 lane 只能进入 recovery 或 proof-backed cleanup，不得按年龄批量删除。
- source canonical 后同轮完成远端 ref/tree/blob 或等价 parity readback，并使用本仓 `scripts/worktree_absorption_audit.py` 或 fleet audit 确认吸收，再清理 task-owned worktree/branch；审计工具只提供证据，不代替 owner 判断或执行删除。
- `.worktrees` 目录只保存 `git worktree list` 可识别的 worktree；build、release、preflight、日志和证据必须写入各自任务命名空间，并由创建任务在终态提取必要 receipt 后清理。

### 状态与归档操作分离

- `SAFE_TO_ARCHIVE` 只授权更新标题、登记终态证据、清空 objective owner；它不授权调用 `set_thread_archived(true)` 或任何等价归档操作。
- 实际归档必须得到用户在看过终态证据后，对具体任务或明确 thread ID 的 fresh 验收。总账 terminal、回调中的“可归档”、`remaining=[]`、历史许可、批量目标、controller 裁决或 agent 判断都不能替代本次用户验收。
- 用户没有明确验收时，保持线程未归档，并记录 `archive_performed=false`、`user_approval_required=true`。批量验收只覆盖用户本次明确列出的任务。
- 若误执行归档，立即恢复为未归档，保留 `SAFE_TO_ARCHIVE` 标题，如实登记纠正；不得等用户再次要求。

## 建立执行图

1. 从可用的 fresh thread readback、远端主线和机器合同重建当前事实。不要从过期标题、旧回执或历史 ledger 推断 owner。
2. 为每个对话记录 `thread_id`、`objective_id`、该切片的 owner、execution owner、精确 write set、当前 authority、具体 `next_action`、integration plan 和 completion gaps。
3. 保证每个切片只有一个 owner；同一 objective 可拆成多个独立切片并行。子智能体只承担边界清楚的只读审计、测试、研究或独立实现，父对话仍负责最终验收和吸收。
4. 同时检查两类缺口：没有 objective 的活跃对话，以及没有 owner 的未完成 objective。立即分工，不留空档。
5. 按 fresh execution state 使用 `ACTIVE`、`NEEDS_ACTION`、`BLOCKED`、`MONITORING` 或 `SAFE_TO_ARCHIVE` 前缀，后接 `<surface>｜<concrete state>`。标题只是人读投影，不能反向证明执行状态；`SAFE_TO_ARCHIVE` 标题仍保持线程未归档，直到用户 fresh 验收。没有实际线程操作能力时，只给出应更新的标题，不要声称已修改。

## 并行推进

- 为 Git 写任务使用独立 worktree 和分支，遵守目标仓库的 `AGENTS.md`、机器合同以及真实的共享 mutation、资源容量和权限边界；不要套用未经证明的固定并发上限。
- 依赖边只决定吸收顺序，不决定执行状态。先完成不依赖上游最终字节的实现、兼容桥、测试、生成、QA、审计和集成准备。
- write-set overlap 是集成风险，不是长期锁。允许各自 worktree 继续准备；共享路径在吸收时只有一个最终 mutation owner，其他成果按 fresh SSOT 语义重放。
- 重构或替换任务默认并行拆为 successor 实现、真实 caller 切换、验收和 legacy 退役；先用最小纵向链路证明 successor 可用并可回退，再切换 caller，随后在新路径上补强并批量删除旧实现。不要把每个旧字段的清理串行化为新模块可用的前置条件，也不要用永久双写或 runtime fallback 维持第二条生产路径。
- 不用驻留轮询、等待 ACK 或重复监测冒充 `next_action`。若一个对话没有真实可执行工作，立即重分配一个独立剩余切片；没有诚实切片时，报告分工错误并重组 scope，不制造忙碌证据。
- 如果对话没有真实可执行工作，不得继续标记为 `ACTIVE`：需要用户动作则转为 `NEEDS_ACTION`，需要外部事件则转为 `BLOCKED`，长期工作台或监督入口转为 `MONITORING`，成果已被 canonical authority 完整覆盖则转为 `SAFE_TO_ARCHIVE`。若仍有可执行缺口则登记最小切片和第一动作；若只是重复 writer 则改为只读审计或 superseded，不新建第二 writer。
- 有限执行轮次完成后，长期责任保留在 Bead/Linear 的 `MONITORING`，而不是保留一个空闲执行对话。清空 live `execution_thread`，保存 `last_execution_thread`、下次复核日期和事件触发条件；完成的对话按证据转为 `SAFE_TO_ARCHIVE`，得到用户 fresh 验收后归档。到期或事件发生时，未归档 executor 可恢复，已归档的 `last_execution_thread` 只能作为 provenance，必须新建有限 executor；完成回读后再次解除绑定。
- currentness 前进后由原对话、原 owner 继续 replay/rebase。不要仅因主线漂移创建等待 successor 或丢弃已有责任。

### 本地优先、远端最后

- 对手工开发，在 push task ref、canonical main 或触发远端 Actions 前，先在本机或本地等价环境运行全部可复现的 build、test、lint、workflow validator 和 packaging dry-run；修复首个真实断点并重跑受影响门禁。
- 显式列出本地无法等价验证的项目及原因，不把它们写成已验证。GitHub Actions 只承担本地不可替代的 hosted OS/arch、受保护凭据、public mutation 与 owner-authoritative readback。
- 远端 CI 结果仍可作为必要终态证据，但不得替代本地可复现验证，也不得用来进行第一轮试错或常规调试。

### 多机远端同步

- 默认按多机协同处理长任务。开始、恢复、交接和重要 checkpoint 前 fetch canonical remote refs，fresh 读取 `main`、task branch、当前 owner 和 write set；不得用本机旧 tracking ref 推断 currentness。
- 阶段成果已可验证、可恢复且不含敏感信息时，同轮 commit 并 ordinary non-force push 到 task-owned 远端分支，再回读远端 branch SHA/tree。不要让唯一可恢复成果长时间只存在于本机 worktree。
- 不得把 dirty、冲突中、测试 unknown、含敏感信息或外部 mutation 结果 unknown 的状态推成 checkpoint。尚不满足条件时继续本地修复，并明确报告 remote parity 尚未成立。
- 远端任务分支不等于 canonical、完成、SSOT 或可清理；它只承担跨机器恢复与交接。`main` 仍按最终吸收规则受控集成，主线漂移后由原 owner 基于 fresh SSOT 语义重放。

## 最终吸收

1. 在集成前重新 fetch 远端 `main`、相关 tag、installed/effective authority 和活跃 owner/write set。
2. 按当前 SSOT 做 semantic replay/rebase；对 catalog、lock、manifest、projection 等派生表面从最新输入重新生成，禁止机械选择旧 blob。
3. 重跑 replay 影响到的 focused、aggregate 和跨仓门禁。
4. 只对不可合并的共享 mutation 使用短临界区，例如 canonical `main` CAS/push、tag、managed install、release publication、数据库迁移或 VM 分配。
5. 使用 ordinary non-force mutation；authority 再次前进时回到步骤 1，不进入等待状态。
6. 吸收后验证远端 ref、commit、tree、blob/raw bytes，并按目标验证 installed/effective、publication 或 qualification 结果。
7. 只清理本任务拥有的 worktree、branch、process、cache 和临时文件。
8. 原 owner 必须持续负责到 `scripts/worktree_lifecycle.py close` 成功；handoff、callback、candidate、canonical push 或冲突本身都不解除 cleanup 义务。冲突由该 owner 基于 fresh SSOT 语义重放后解决。

## 归档判定

仅在以下适用条件全部成立时标记 `SAFE_TO_ARCHIVE`：

- 成果可从远端 canonical authority 到达；
- API/tree/blob/raw readback 与预期一致；
- 必需 focused、aggregate、跨仓门禁通过；
- 需要安装、生效、发布或 VM qualification 的目标已有真实终态回读；
- 自有临时表面已清理；
- `remaining=[]`，没有 successor obligation 或未吸收内容。

本地候选、commit、测试通过、handoff、fail-closed receipt 或“建议归档”都不等于完成。对于 mutation 为零的重复对话，只有在确认没有独立未吸收义务、其 objective 已由 canonical authority 完整覆盖后才可标记 `SAFE_TO_ARCHIVE`；实际归档仍需用户 fresh 验收。

## 输出要求

先给结论，再提供：

1. `SAFE_TO_ARCHIVE` 明细及逐项证据；
2. `ACTIVE` 对话明细，包含 owner、可立即执行的下一步、write set 和吸收计划；
3. objective-to-thread 覆盖检查，明确列出 ownerless gap，正常时写 `0`；
4. 依赖与吸收关系图；
5. 可立即增加的并行切片与适合的子智能体分工。

保持事实精度：只报告真实执行过的 thread、Git、install、release 或 archive mutation，不把建议写成已完成状态。对每个 `SAFE_TO_ARCHIVE` 项明确报告 `archive_performed` 与 `user_approval_required`，不得把改标题写成已归档。
