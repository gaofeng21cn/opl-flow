# Verifier Compatibility Prompt

显式兼容入口，用于用户要求独立验证或旧自动化依赖。root 的正常终局验证直接按 `AGENTS.md` 和 `verification-before-completion` 执行。

1. 验收优先级：冻结的用户目标、已落盘 plan/runbook/contract、lane 目标，最后才是实现者自述。
2. 为每条主张运行 fresh claim-appropriate evidence；tests 不外推 runtime/currentness/release/owner claim。
3. 目标态任务只由 root 在终局输出一次完成度审计；subagent 调用本兼容 prompt 时只返回证据、缺口与目标映射，root 仍按 `AGENTS.md` 完成终局审计。
4. 发现原验收范围内的可执行缺口就继续修复；新机会另立目标，不让验证循环扩张当前任务。
