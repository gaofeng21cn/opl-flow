## Workflow Core

- 进入项目后按 planner/executor/debugger/verifier prompt 读取用户级 `~/.codex/TASTE.md` 校准 AI 工作偏好；事实仍以用户指令、源码、contracts、docs、runtime 输出和 repo-native 验证为准。
- 项目特异规则放在当前 repo 的 `AGENTS.md`、docs、contracts、source、tests 和 runtime/readback surface。
- Direct：纯问答、解释、状态阅读、小范围只读核查，直接完成。
- Inline：目标明确的普通实现、修复、配置或文档更新，默认由主会话执行；先读真实上下文，再做最小改动和最小充分验证。
- Durable：跨会话、跨仓库、长周期、多阶段、需要证据留存或影响 release/CI/runtime authority 的任务，必须把计划、证据、决策或 runbook 写入项目内合适文档。
- 需求不清、需要方案比较或拆解：读取 `~/.codex/prompts/planner.md`。
- 目标明确、需要实施：读取 `~/.codex/prompts/executor.md`。
- bug、失败、异常行为或回归：读取 `~/.codex/prompts/debugger.md`，并使用 `systematic-debugging`。
- 声称“已完成 / 已修复 / 已通过”前：读取 `~/.codex/prompts/verifier.md`，并使用 `verification-before-completion`。
