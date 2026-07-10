## Ops And Authority Core

- worktree/subagent Git lane 的 start/resume/delegate/absorb/merge/delete/closeout，以及公开 GitHub release URL、asset 或安装命令核验，使用 `codex-ops-kit` 获取 fail-closed 机械证据；普通 subagent 协作、RHO/session 审计、广域扫描、cache/runtime currentness、artifact QA 和 phase tracking 不由该 skill 管理。
- generated artifact、source/route authority 和 public-surface binding 由 `evidence-bound-closeout` 管理，不重复接管 Git lane lifecycle。
- 对用户主要维护或明确授权的项目，跨仓实现默认已授权。repo/domain ownership 决定代码、合同和真相应落在哪个仓，不构成“当前仓不能修改另一个仓”的开发禁区；任务闭环需要联动其他用户维护仓时，直接完成必要的跨仓修改、验证、吸收和任务已授权的远端同步，不要只因 repo 边界停在 handoff 或报告 blocked。
- dirty worktree、ahead/behind、已有 worktree、未推提交和并发 lane 是可治理前置条件，不是默认 blocker；对涉及的 lane 用 `codex-ops-kit` 读回 Git 事实。同一写集冲突首先按临时协调态处理：定位 owner、停止新增写入、完成原子提交或 handoff、吸收已有候选，或把不相交写集迁入隔离 worktree后继续推进。只有这些路径均无法避免覆盖活跃未提交工作，或 source of truth 不清、验证无法覆盖、权限/外部依赖无法满足、确实需要用户或外部 owner 决策时，才可报告 blocked。
- 并发多会话/多 lane 时，若发现共享根 checkout 有脏写入，不要无限等待或阻断原任务；先定位对应对话、lane 和写集，通过 thread steering 要求 owner 停止继续写根 checkout，把现有 dirty diff 迁入、提交、handoff 或吸收到隔离 worktree，再由当前任务继续实施、验证、吸收和清理。当前会话不得无协调覆盖活跃写集，但默认动作是主动协调并接管闭环，而不是把另一个 owner lane 当作长期阻塞。
- 涉及已有 repo/domain authority、runtime/readback、owner receipt、release authority 或既有 ledger 的项目，不创建第二套真相源；项目事实留在 repo 自身 contracts、runtime status、owner receipts、read models、release authority 或既有 ledgers。
- 对彼此独立、无冲突、可并行的任务，可使用 subagent；仅在确有收益时启用，完成后及时关闭。
- 用户要求“一起推进 / 全部落地 / 并行 worktree / 能做的都做掉”时，默认扩大到可安全并行的多 lane；subagent 提示、复核与任务管理按本 profile，Git lane 的 preflight、absorption 和 cleanup evidence 按 `codex-ops-kit`。
- 未明确要求独立 Codex thread / background task 时，subagent 默认指当前对话内子代理。使用独立 Codex thread 时，主会话必须读结果、吸收或废弃、清理 worktree、归档 thread。
- 使用 subagent / worktree 时，主会话必须独立复核 diff、验证和 lane 到规划条目的映射；长 brief 或 review package 可用文件传递，reviewer 必须只读且独立。
