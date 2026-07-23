---
name: coordinate-concurrent-tasks
description: Coordinate multiple Codex conversations, agents, repositories, or worktrees so unfinished work stays ACTIVE, independent work proceeds in parallel, conflicts resolve against fresh SSOT at integration, only fully authoritative work becomes SAFE_TO_ARCHIVE, and actual thread archival requires fresh user acceptance. Use when reorganizing active threads, eliminating wait or blocked states, assigning parallel owners or subagents, resolving dependency or write-set overlap, finding unowned task gaps, reviewing archive safety, or accelerating multi-task delivery. 适用于多对话并发、等待与锁处理、主线吸收、任务缺口审计和需用户验收的安全归档。
---

# 并发任务协调

## 核心原则

采用 `parallel_work_serialized_integration`：并行完成可独立推进的工作，只在最终共享 mutation 的短临界区串行。

只使用两种用户可见状态：

- `ACTIVE`：仍有任何实现、验证、吸收、安装生效、发布、回读或清理未完成。
- `SAFE_TO_ARCHIVE`：全部成果已进入真实 authority 并实际生效，证据闭合且 `remaining=[]`。

把依赖、冲突、currentness drift、外部门禁失败和候选提交记录为事实，不要把它们变成 `WAIT`、`BLOCKED`、`HOLD`、`HANDOFF`、`CANDIDATE_ONLY` 或 `ARCHIVE_CANDIDATE` 状态。未完成对话必须持续承接一个真实、可立即执行的 `ACTIVE` 任务。

### 状态与归档操作分离

- `SAFE_TO_ARCHIVE` 只授权更新标题、登记终态证据、清空 objective owner；它不授权调用 `set_thread_archived(true)` 或任何等价归档操作。
- 实际归档必须得到用户在看过终态证据后，对具体任务或明确 thread ID 的 fresh 验收。总账 terminal、回调中的“可归档”、`remaining=[]`、历史许可、批量目标、controller 裁决或 agent 判断都不能替代本次用户验收。
- 用户没有明确验收时，保持线程未归档，并记录 `archive_performed=false`、`user_approval_required=true`。批量验收只覆盖用户本次明确列出的任务。
- 若误执行归档，立即恢复为未归档，保留 `SAFE_TO_ARCHIVE` 标题，如实登记纠正；不得等用户再次要求。

## 建立执行图

1. 从可用的 fresh thread readback、远端主线和机器合同重建当前事实。不要从过期标题、旧回执或历史 ledger 推断 owner。
2. 为每个对话记录 `thread_id`、`objective_id`、唯一 owner、execution owner、精确 write set、当前 authority、具体 `next_action`、integration plan 和 completion gaps。
3. 保证一个 objective 只有一个主控；把可独立验收的切片分给不同对话。子智能体只承担边界清楚的只读审计、测试、研究或独立实现，父对话仍负责最终验收和吸收。
4. 同时检查两类缺口：没有 objective 的活跃对话，以及没有 owner 的未完成 objective。立即分工，不留空档。
5. 使用 `ACTIVE｜<owner/surface>｜<concrete objective>` 或 `SAFE_TO_ARCHIVE｜<surface>｜<completed objective>` 作为标题语义。`SAFE_TO_ARCHIVE` 标题仍保持线程未归档，直到用户 fresh 验收。没有实际线程操作能力时，只给出应更新的标题，不要声称已修改。

## 并行推进

- 为 Git 写任务使用独立 worktree 和分支，遵守目标仓库的 `AGENTS.md`、机器合同和并发上限。
- 依赖边只决定吸收顺序，不决定执行状态。先完成不依赖上游最终字节的实现、兼容桥、测试、生成、QA、审计和集成准备。
- write-set overlap 是集成风险，不是长期锁。允许各自 worktree 继续准备；共享路径在吸收时只有一个最终 mutation owner，其他成果按 fresh SSOT 语义重放。
- 不用驻留轮询、等待 ACK 或重复监测冒充 `next_action`。若一个对话没有真实可执行工作，立即重分配一个独立剩余切片；没有诚实切片时，报告分工错误并重组 scope，不制造忙碌证据。
- currentness 前进后由原对话、原 owner 继续 replay/rebase。不要仅因主线漂移创建等待 successor 或丢弃已有责任。

## 最终吸收

1. 在集成前重新 fetch 远端 `main`、相关 tag、installed/effective authority 和活跃 owner/write set。
2. 按当前 SSOT 做 semantic replay/rebase；对 catalog、lock、manifest、projection 等派生表面从最新输入重新生成，禁止机械选择旧 blob。
3. 重跑 replay 影响到的 focused、aggregate 和跨仓门禁。
4. 只对不可合并的共享 mutation 使用短临界区，例如 canonical `main` CAS/push、tag、managed install、release publication、数据库迁移或 VM 分配。
5. 使用 ordinary non-force mutation；authority 再次前进时回到步骤 1，不进入等待状态。
6. 吸收后验证远端 ref、commit、tree、blob/raw bytes，并按目标验证 installed/effective、publication 或 qualification 结果。
7. 只清理本任务拥有的 worktree、branch、process、cache 和临时文件。

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
