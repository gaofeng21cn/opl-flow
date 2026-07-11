## Ops And Authority Core

- worktree/subagent Git lane 的 start/resume/delegate/absorb/merge/delete/closeout，以及公开 GitHub release URL、asset 或安装命令核验，使用 `codex-ops-kit` 获取 fail-closed 机械证据；普通 subagent 协作、RHO/session 审计、广域扫描、cache/runtime currentness、artifact QA 和 phase tracking 不由该 skill 管理。
- generated artifact、source/route authority 和 public-surface binding 由 `evidence-bound-closeout` 管理，不重复接管 Git lane lifecycle。
- repo 边界不构成开发禁区，但只有冻结验收明确包含跨仓改动，或同一合同闭环不可避免且 ownership 清楚时才扩写集；commit、push、release 和远端同步仍需当前任务授权。
- dirty worktree、ahead/behind 和并发 lane 是前置事实。仅在当前任务确实命中同一写集时做一次 owner 协调、迁移或隔离；不全局巡检线程，不默认接管其他 lane，也不覆盖活跃未提交修改。
- 涉及已有 repo/domain authority、runtime/readback、owner receipt、release authority 或既有 ledger 的项目，不创建第二套真相源；项目事实留在 repo 自身 contracts、runtime status、owner receipts、read models、release authority 或既有 ledgers。
- 对可以独立描述、并行收益明确且不会造成同写集冲突的研究、核查、测试、审阅和实现切片，默认主动使用 subagent；root 负责冻结目标、分配 exact paths/write sets、整合结果和终局验证。实现 lane 数按任务收益、当前容量和写集隔离决定，不设固定两条上限；协调成本超过收益时及时收敛或复用已有 agent。
- 自包含 brief 使用 `fork_turns="none"`；确实依赖近期决策时使用 `"3"`；`"all"` 仅在 brief 或文件无法传递完整语义时使用。brief 必须给出目标、exact paths、禁止写集、验证和停止条件。
- 使用 subagent / worktree 时，root 独立复核 diff、验证和规划映射。未明确要求独立 Codex task 时，subagent 指当前对话内子代理；独立 task 完成后还需吸收或废弃、清理并归档。
