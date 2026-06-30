## Capability Adapters

- 新功能、行为变更、结构调整：`planner -> executor -> verifier`。
- bug 修复、失败排查、回归定位：`debugger -> executor -> verifier`。
- 新功能或 bug 修复只有在 `risk-based-development-flow` 判定需要先锁定高风险行为、稳定低成本 bug 回归、durable contract/authority 边界，或用户明确要求 TDD 时，使用 `test-driven-development`。
- 需要隔离并行改动、避免污染当前工作区或用户明确要求 worktree 时，使用 `using-git-worktrees`。
- Superpowers 作为按安装状态启用的能力 adapter 使用；默认保持本机当前 Superpowers profile，仅在用户明确要求切换时按对应安装指引操作。
- Ponytail 可作为按需简化 lens 使用；默认应为 `off` 或 `lite`，只在 YAGNI、stdlib-first、native-first 或 over-engineering review 场景显式触发，不能覆盖 `risk-based-development-flow`、`codex-ops-kit`、verifier、fresh evidence、runtime/currentness/readiness 或完成度审计规则。
- 跨仓/全仓清理候选发现、历史残留梳理或“哪里可以删/收薄”使用 `ponytail-audit`；已有具体 diff、PR、worktree lane、cleanup/refactor/替代旧面准备吸收或提交时，默认用 `ponytail-review` 做复杂度回归检查，确认本次改动没有新 wrapper、compat 层、无请求抽象、无必要依赖或死 flexibility。该检查只补充复杂度维度，不替代正确性、安全、authority、runtime 或 verifier 证据；纯文档、只读审计、紧急 hotfix 或微小一行改动可跳过并说明理由。
- 用户明确触发 `grill-with-docs`、`zoom-out`、`prototype`、`improve-codebase-architecture` 等补充技能时，按对应 skill 使用；它们不替代项目 facts、contracts、runtime 输出和 repo-native 验证。
