## Workflow Core

- `AGENTS.md` 是唯一默认运行时 workflow profile。`TASTE.md` 是人类维护偏好的 authoring source，其稳定摘要已进入本文件；普通 session 和 subagent 不再重复读取它。
- 项目特异规则放在当前 repo 的 `AGENTS.md`、docs、contracts、source、tests 和 runtime/readback surface。
- Direct：纯问答、解释、状态阅读、小范围只读核查，直接完成。
- Inline：目标明确的普通实现、修复、配置或文档更新，默认由主会话执行；先读真实上下文，再做最小改动和最小充分验证。
- Durable：跨会话、跨仓库、长周期、多阶段、需要证据留存或影响 release/CI/runtime authority 的任务，必须把计划、证据、决策或 runbook 写入项目内合适文档。
- 同一代理按需要连续规划、实施、诊断和验证，不需要读取或切换四个 prompt 文件。`planner`、`executor`、`debugger`、`verifier` 只作为用户显式调用或旧自动化依赖时的兼容入口。
- 复杂任务开工前冻结用户验收目标、非目标和停止条件；实现中发现的新机会不自动扩张本任务。
- commentary 采用事件驱动：仅在启动、验收或路径变化、重要发现、真实等待或 blocker、关键验证结果和终局时更新；不做固定时钟心跳。
