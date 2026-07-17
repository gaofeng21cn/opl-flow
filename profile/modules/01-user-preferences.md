你始终用中文回复。

- 先给结论，表达专业、简洁、高信息密度。
- 说明必要的逻辑、决策依据和影响范围。
- 默认停留在用户有用的抽象层，回答长度与任务复杂度匹配。
- 修改前先确认真实生效位置、调用链和当前项目约束。
- 进入仓库后，以更具体的 repo-local `AGENTS.md`、合同和真实实现为准。
- Git 仓库写入任务默认使用任务自有 worktree 和分支；根仓 `main` 只用于短时集成、最终验证和必要的发布操作，普通开发不直接写根仓。
- 唯一写入 owner 只约束精确写集或正在进行的 `main` 集成窗口，不默认锁住整个仓库；同仓非重叠任务应在独立 worktree 并行，重叠写集先通过任务消息或主集成任务明确交接。
- 吸收前必须同步并复核最新 canonical `main` 与远端 currentness，按当前 SSOT 解决冲突，禁止用旧基线覆盖新主线；吸收后在最终 `main` 字节上验证，并清理任务自有 worktree、临时分支、stash 和 patch。
- Shell 默认使用 `rtk`；需要完整原始输出或精确流行为时使用原生命令。
- 进入开发仓库时，若缺少 `.codegraph/` 则运行 `codegraph init .`，确保它被 Git ignore，并在 repo-local `AGENTS.md` 保留简短 CodeGraph block；结构检索优先 CodeGraph，字面文本检索使用 `rg`。
