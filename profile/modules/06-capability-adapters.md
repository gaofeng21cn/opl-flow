## Capability Adapters

- 新功能、行为变更、结构调整：`planner -> executor -> verifier`。
- bug 修复、失败排查、回归定位：`debugger -> executor -> verifier`。
- 新功能或 bug 修复只有在 `risk-based-development-flow` 判定需要先锁定高风险行为、稳定低成本 bug 回归、durable contract/authority 边界，或用户明确要求 TDD 时，使用 `test-driven-development`。
- 需要隔离并行改动、避免污染当前工作区或用户明确要求 worktree 时，使用 `using-git-worktrees`。
- Superpowers 作为按安装状态启用的能力 adapter 使用；默认保持本机当前 Superpowers profile，仅在用户明确要求切换时按对应安装指引操作。
- Codex 下 Superpowers 默认走原生 skill discovery 与本机 `superpowers-lite`，不启用 upstream `using-superpowers` conversation-wide bootstrap，也不依赖 SessionStart hook；只有用户明确要求 full upstream profile 时才切换。
- Ponytail 默认保持 `lite`，用于日常问答、状态阅读、方案比较、任务拆解、报告、completion audit、runtime/readiness/currentness 判断；它不能覆盖 `risk-based-development-flow`、`codex-ops-kit`、debugger、verifier、fresh evidence、owner route、completion audit、runtime/readiness/currentness 证据要求。
- 具体开发任务自动提升到 `ponytail full`：实现功能、修 bug、重构、配置改动、脚本改动、测试改动、PR/diff review、worktree lane 吸收。`full` 下主动执行 Ponytail ladder：先判断是否需要存在，优先删除或复用现有代码，优先 stdlib/native/已有依赖，避免新增 wrapper/factory/未来扩展位，保持最小 diff；非平凡逻辑留下最小可运行检查。
- 删除/瘦身专项才使用 `ponytail ultra`：用户明确要求“删除、瘦身、反过度设计、砍 wrapper、清历史残留、找哪里可以删、YAGNI audit、ponytail-audit”时触发；`ultra` 默认先输出候选清单和风险排序，只有用户明确要求执行时才做删除性修改。
- 当任务同时命中 `full` 和 `ultra`，默认使用 `full`；只有任务主目标是删除/瘦身时才使用 `ultra`。用户要求“彻底落地 / 全部落地 / 一步到位 / 持续推进直到完成”时，Ponytail 只能压缩实现方式，不能缩小验收范围或把缺少 runtime/owner/end-to-end evidence 的条目报告为完成。
- 跨仓/全仓清理候选发现、历史残留梳理或“哪里可以删/收薄”使用 `ponytail-audit`；已有具体 diff、PR、worktree lane、cleanup/refactor/替代旧面准备吸收或提交时，默认用 `ponytail-review` 做复杂度回归检查，确认本次改动没有新 wrapper、compat 层、无请求抽象、无必要依赖或死 flexibility。该检查只补充复杂度维度，不替代正确性、安全、authority、runtime 或 verifier 证据；纯文档、只读审计、紧急 hotfix 或微小一行改动可跳过并说明理由。
- 用户明确触发 `grill-with-docs`、`zoom-out`、`prototype`、`improve-codebase-architecture` 等补充技能时，按对应 skill 使用；它们不替代项目 facts、contracts、runtime 输出和 repo-native 验证。
