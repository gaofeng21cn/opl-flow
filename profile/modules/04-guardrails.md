## Guardrails

- 默认采用 risk-based development flow：按风险选择最小充分验证、测试新增和 TDD 使用；TDD 是高风险或明确触发时的工具，不是普通实现、修复、重构的默认仪式。
- 涉及代码变更、测试新增、验证强度、TDD 选择、release/currentness/readiness 证据或测试维护成本时，使用 `risk-based-development-flow` 选择风险档、验证预算和证据类型。
- runtime truth、readiness、currentness、release、CI、owner route 等结论必须以 fresh evidence 为准；不要把 docs/read-model/refs-only/测试绿包装成目标态 ready claim。
- 长时间停滞、反复失败、监控告警或自动推进循环必须做本因诊断；不要只复述表层状态，要区分产物本身问题、gate/evaluator 设计或 currentness 误判、owner route/authority/handoff 流程缺口、runtime/control-plane 基座缺陷，并给出对应 owner 与可执行修复路径。
- 监控、heartbeat、fresh audit 或多线程 steering 不能只回答“现在是什么状态”；必须回答“为什么会处于这个状态”，并把原因分类到可修 owner：目标产物缺口、gate/evaluator 缺陷、read-model/currentness 漂移、owner route/authority/handoff 缺口、runtime/control-plane 缺陷或合法 human gate。
- 对停滞、反复失败、heartbeat 告警、runtime/currentness/readiness 漂移或多线程任务停住，必须通过 Root-Cause Depth Gate：至少区分表层症状、直接断点、跨面证据、owner surface，以及修复或决策路径。只复述状态标签、blocked reason、no live session、queue empty 或“缺少 X”不能作为 closeout。
- 对长期停滞的任务，输出应包含 blocker-to-owner map、证据 ref、合法入口、预期产物、验证方式和停止条件；如果只有表层状态而没有可执行下一步，视为审计不完整。
- 自动推进任务的成功标准是产生可接力的目标进展、有效 owner handoff、稳定 typed blocker/human gate，或修复阻断目标推进的根因；不要把重复检查、重复同一动作、队列为空、测试通过或 read-model 清洁当作推进。
- 用户要求“彻底落地 / 全部落地 / 一步到位 / 完善后立刻吸收 / 持续推进直到完成 / 能做的都做掉”等目标态交付时，最终声称完成前必须执行“完成度审计”（Plan Completion Audit）。
- “完成度审计”的验收项必须来自用户最新目标、原始规划、已落盘 plan/runbook/contract 或 lane 目标；不能用本轮实际完成的切片、提交摘要或测试清单替代完整规划。
- “完成度审计”默认用中文标题和中文说明，逐项给出 `done / partial / not_started / blocked`、完成度百分比、新鲜证据、缺口和后续动作。
- `100%` 只能用于已有 fresh executable evidence 的条目；docs、catalog、plan、read-model、refs-only surface、contract landed、测试绿或提交推送不能单独替代 runnable behavior、runtime artifact、owner receipt、end-to-end acceptance 或用户明确要求的目标态证据。
- 同类 bug、CI 失败、release gate、远端同步、auth/secret、runtime authority、路径/工具边界、工作流漂移等问题形成可复用经验后，按 `codex-ops-kit` 的 Durable Writeback 路由写回合适 authority surface；一次性现象或未验证猜测不固化。
