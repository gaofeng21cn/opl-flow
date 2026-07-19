你始终用中文回复。

- 先给结论，专业、简洁、高信息密度；说明必要的逻辑、决策依据和影响范围，长度与任务复杂度匹配。
- 修改前确认真实生效位置、调用链和项目约束；进入仓库后，以更具体的 repo-local `AGENTS.md`、合同和真实实现为准。
- 可独立任务积极并行，不因单个等待项停工；多对话只设一个主控，负责分工、集成窗口和终态，不与执行任务共享普通写集。
- 每个 Git 写任务及写入型子任务必须独占自己的 worktree 和分支，其他参与者默认只读；唯一 owner 只约束精确写集。暂停或写锁必须声明精确作用域、唯一 owner 和恢复条件，只冻结对应写集或外部 mutation；只有真实依赖、重叠写集、`main` 或发布集成窗口才串行。
- 吸收前同步并复核最新 canonical `main` 与远端 currentness，按当前 SSOT 解决冲突，禁止旧基线覆盖新主线；吸收后验证最终 `main` 字节，并清理任务 worktree、临时分支、stash 和 patch。
- Shell 默认使用 `rtk`；需要完整原始输出或精确流行为时使用原生命令。
- 进入开发仓库时，若缺少 `.codegraph/` 则运行 `codegraph init .`，确保它被 Git ignore，并在 repo-local `AGENTS.md` 保留简短 CodeGraph block；结构检索优先 CodeGraph，字面文本检索使用 `rg`。
