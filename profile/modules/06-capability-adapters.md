## Capability Adapters

- 按任务需要连续应用 planner、executor、debugger、verifier lenses，不把箭头顺序当作会话交接或停止点。
- 仅在用户明确要求、稳定低成本且高价值的 bug 回归、durable contract/schema/CLI/API、权限边界、不可逆写路径，或 test-first API sketch 能显著降低接口歧义时使用 `test-driven-development`；普通功能、重构、docs/config、一次性运维或 runtime/currentness 证明不默认使用。
- Superpowers 作为按安装状态启用的能力 adapter 使用；默认保持本机当前 Superpowers profile，仅在用户明确要求切换时按对应安装指引操作。
- Codex 下 Superpowers 默认走原生 skill discovery 与本机 `superpowers-lite`，不启用 upstream `using-superpowers` conversation-wide bootstrap，也不依赖 SessionStart hook；只有用户明确要求 full upstream profile 时才切换。
- `brainstorming` 只在意图、验收或设计存在实质不确定，或用户明确要求方案比较时使用；不要因为任何 feature、config 或 docs 改动一律设置审批 hard gate。
- 只有隔离确有收益或用户明确要求时才创建 worktree；优先使用 Codex 原生能力，expanded/full Superpowers 可使用 `using-git-worktrees`，但不得因存在 implementation plan 自动改 `.gitignore`、安装依赖或提交。
- Ponytail 默认保持 `lite`，作为实现复杂度 lens；插件负责 mode 和 ladder，OPL Flow 不宣称按任务自动切换 `full/ultra`。广域清理候选使用 `ponytail-audit`，具体 diff/PR/lane 使用 `ponytail-review`。
- Ponytail 只能压缩实现复杂度，不能缩小用户范围或覆盖 risk、authority、fresh evidence、runtime/readiness/currentness 和完成度审计要求。
- 用户明确触发 `grill-with-docs`、`zoom-out`、`prototype`、`improve-codebase-architecture` 等补充技能时，按对应 skill 使用；它们不替代项目 facts、contracts、runtime 输出和 repo-native 验证。
