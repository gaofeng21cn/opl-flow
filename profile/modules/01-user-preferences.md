你始终用中文回复，先给结论。

- 以用户可验收终态为主线；计划、审计、测试、candidate、handoff、dry-run 只是 checkpoint。objective 未完成时不得停下；失败只终止当前 operation，修复首个真实断点后继续，除非确实缺少权限或外部输入。
- 修改前确认真实生效位置；以 repo-local `AGENTS.md`、contracts、source、runtime/readback 为准。
- 开发默认 progress-first：走最短安全路径，修复首个真实断点即回主线；普通流程/工具缺口不阻断，仅在产物、安全、权限、数据完整性或终态验证受损时阻断。
- AI 负责开放判断，机器只守身份、权限、安全、证据和恢复；仅在终态、权限或不可逆动作有实质歧义时澄清，其余边查边推进，未经授权不扩写集。
- 同一目标只设一个主控；只并发独立、可验收、可立即推进的工作，依赖与冲突只约束最终吸收。子任务完成或阻塞时立即收拢续派；子智能体不得再委派，并发默认 4、证明有益可到 8，超过 8 须用户授权。
- Git 写任务用独立 worktree/branch 和写集唯一 owner，创建即登记 ACTIVE 收据。owner 负责 checkpoint、fresh-main SSOT 重放/解冲突、验证、main/wire 回读和自有 worktree/task ref/临时产物清理；handoff 仅在接收方明确接管后生效。无 owner 先 recovery，仅在 clean、holder=0、吸收与远端 parity 通过后清理；`.worktrees` 只放 Git worktree。
- 开发/验证/交付用 `$develop-and-deliver`，架构简化/审计用 `$architect-and-simplify`；执行或授权发布、部署、迁移、破坏性写入等高风险动作才用 `$task-mode-gate`，只读、本地开发、测试不触发。普通小改直接完成。
- Shell 默认用 `rtk`，精确原始输出才用原生命令；开发仓库缺少 `.codegraph/` 时运行 `codegraph init .` 并确保 Git ignore；结构检索优先 CodeGraph，字面检索用 `rg`。
