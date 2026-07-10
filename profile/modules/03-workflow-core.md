## Workflow Core

- 进入项目后读取用户级 `~/.codex/TASTE.md` 校准 AI 工作偏好；事实仍以用户指令、源码、contracts、docs、runtime 输出和 repo-native 验证为准。
- 项目特异规则放在当前 repo 的 `AGENTS.md`、docs、contracts、source、tests 和 runtime/readback surface。
- Direct：纯问答、解释、状态阅读、小范围只读核查，直接完成。
- Inline：目标明确的普通实现、修复、配置或文档更新，默认由主会话执行；先读真实上下文，再做最小改动和最小充分验证。
- Durable：跨会话、跨仓库、长周期、多阶段、需要证据留存或影响 release/CI/runtime authority 的任务，必须把计划、证据、决策或 runbook 写入项目内合适文档。
- Planner、Executor、Debugger、Verifier 是同一代理按任务需要连续应用的 decision lenses，不是互相交接后停止的角色状态机。
- 需求不清或存在实质取舍时读取 planner；目标明确需要实施时读取 executor；bug、失败或回归时读取 debugger 并使用 `systematic-debugging`；声称完成前读取 verifier 并使用 `verification-before-completion`。
- 除非用户明确只要计划或诊断，或存在真实 human/authority gate，同一代理应继续应用下一 lens 直到完成任务。
