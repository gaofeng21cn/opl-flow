## Ops And Authority Core

- worktree/subagent Git lane 的 start/resume/delegate/absorb/merge/delete/closeout，以及公开 GitHub release URL、asset 或安装命令核验，使用 `codex-ops-kit` 获取 fail-closed 机械证据；普通 subagent 协作、RHO/session 审计、广域扫描、cache/runtime currentness、artifact QA 和 phase tracking 不由该 skill 管理。
- dirty worktree、main 落后远端、ahead/behind、已有 worktree、未推本地提交、并发 lane 是可治理工程前置条件；对涉及的 lane 用 `codex-ops-kit` 读回 Git 事实，再按 executor prompt 处理。只有同一写集冲突、source of truth 不清、验证无法覆盖、权限/外部依赖无法满足或需要真实 owner 决策时，才 blocked。
- 并发多会话/多 lane 时，若发现共享根 checkout 有脏写入，不要无限等待或阻断原任务；先定位对应对话、lane 和写集，可用时通过 thread steering 要求 owner 停止继续写根 checkout，把现有 dirty diff 迁入/吸收到隔离 worktree，在 worktree 内完成实现、验证后再吸收清理。当前会话不得覆盖该写集；只有 owner 不活跃、交出写集或 ownership gate 明确允许时，才可接管修复。
- 涉及已有 repo/domain authority、runtime/readback、owner receipt、release authority 或既有 ledger 的项目，不创建第二套真相源；项目事实留在 repo 自身 contracts、runtime status、owner receipts、read models、release authority 或既有 ledgers。
- 对彼此独立、无冲突、可并行的任务，可使用 subagent；仅在确有收益时启用，完成后及时关闭。
- 用户要求“一起推进 / 全部落地 / 并行 worktree / 能做的都做掉”时，默认扩大到可安全并行的多 lane；subagent 提示、复核与任务管理按本 profile，Git lane 的 preflight、absorption 和 cleanup evidence 按 `codex-ops-kit`。
- 未明确要求独立 Codex thread / background task 时，subagent 默认指当前对话内子代理。使用独立 Codex thread 时，主会话必须读结果、吸收或废弃、清理 worktree、归档 thread。
- 使用 subagent / worktree 时，主会话必须独立复核 diff、验证和 lane 到规划条目的映射。
- 多 subagent / worktree 任务默认借鉴 Superpowers v6 的轻量审查方式：长任务 brief、diff、review package 用文件传递；reviewer 只读且独立，不得被提示忽略发现或预设严重度；每任务优先一次合并审查 spec compliance 与 quality，重大多任务变更最后再做一次全局审查。
