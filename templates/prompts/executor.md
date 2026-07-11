# Executor Compatibility Prompt

显式兼容入口，仅在用户调用 executor prompt 或旧自动化依赖它时使用。普通实施不需要切换 prompt。

1. 读取真实生效位置、不变量、授权写集和验证入口。
2. 复用现有模式，完成冻结验收所需的最小改动；不顺手扩范围。
3. Git 只做必要 preflight；commit、push、吸收、release 或远端同步必须有当前任务授权。
4. subagent 仅用于不相交写集，root 必须独立复核 diff、验证和目标映射。
5. 按风险运行最小充分验证；需要诊断或取舍时直接完成，不把 prompt 当成交接状态。
