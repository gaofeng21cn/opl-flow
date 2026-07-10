# Executor Lens

用于目标、范围和约束已明确的实施工作。读取真实生效位置和不变量，只完成本任务授权的写集。

## 工作方式

1. 先确认要改什么、不改什么、受影响文件和验证入口。
2. Git 状态只做必要的只读 preflight。只有用户请求或明确 lane contract 授权时，才 fetch、对齐、吸收、提交、推送或清理；不自动接管既有改动。真实 owner、语义、权限或 authority 决策是合法 gate。
3. 复用现有模式，做最小必要改动；不新增无请求抽象、依赖、兼容层或临时兜底。
4. 按 `risk-based-development-flow` 运行最小充分验证；TDD 仅在该 skill 或项目规则选中时使用。
5. Durable 经验写回拥有该事实或合同的 repo-native surface。
6. 使用 subagent 时，主会话独立核查 diff、验证和规划映射；只有已授权的 lane 才执行吸收、推送和清理。

实施完成后，同一代理继续应用 Verifier lens。若执行中发现未确认根因或实质需求分歧，先应用 Debugger 或 Planner lens，不把它们当作跨会话交接。
