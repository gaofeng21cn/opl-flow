# Verifier Lens

在声称完成、修复、通过、ready、current 或可合并前使用。由 `verification-before-completion` 执行 fresh run/read/claim，本文件只定义验收对象和 OPL 完整性边界。

## 验收对象

优先级依次为：用户最新目标和验收口径、已落盘 plan/runbook/contract、subagent/worktree lane 目标，最后才是提交摘要或实现者自述。不能把实际完成切片改写成完整规划。

## 验收规则

1. 为每条主张选择 fresh claim-appropriate evidence。文档或结构目标可由 fresh render、schema、diff 或检查证明；行为、runtime、release、currentness 和 owner claim 必须有 executable/live/artifact/receipt evidence。
2. 用户要求“全部落地、一步到位、彻底解决、持续推进直到完成”时，输出中文“完成度审计”，逐项给出 `done / partial / not_started / blocked`、完成度、fresh evidence、缺口和后续动作。
3. bug、停滞、heartbeat、runtime/currentness/readiness 或多线程修复必须验收表层症状、直接断点、跨面证据、owner surface 和修复路径；不满足时只能判 partial 或未通过。
4. subagent 结果必须由主会话独立核对写集、diff、验证和规划映射。
5. Durable 任务检查计划、证据、决策或 runbook 是否写回约定 authority surface。

只根据证据给出通过、部分通过或未通过。发现缺口时，同一代理继续应用所需 Planner、Debugger 或 Executor lens；不要用验证报告掩盖未完成范围。
