## Guardrails

- 验证强度匹配风险，选择能直接证明主张的最小 fresh evidence：文档与结构用静态、schema 或 render 检查；普通行为用 focused command/tests；runtime、release、currentness 和 owner claim 用 live/readback/artifact/receipt。不要把 TDD 或全量测试当作默认仪式。
- runtime truth、readiness、currentness、release、CI、owner route 等结论必须以 fresh evidence 为准；不要把 docs/read-model/refs-only/测试绿包装成目标态 ready claim。
- 长时间停滞、反复失败、监控告警或自动推进循环必须解释状态为什么存在，并分类到目标产物、gate/evaluator、read-model/currentness、owner route/authority/handoff、runtime/control-plane 或合法 human gate。
- 对停滞、反复失败、heartbeat 告警、runtime/currentness/readiness 漂移或多线程任务停住，必须通过 Root-Cause Depth Gate：至少区分表层症状、直接断点、跨面证据、owner surface，以及修复或决策路径。只复述状态标签、blocked reason、no live session、queue empty 或“缺少 X”不能作为 closeout。
- 对长期停滞的任务，输出应包含 blocker-to-owner map、证据 ref、合法入口、预期产物、验证方式和停止条件；如果只有表层状态而没有可执行下一步，视为审计不完整。
- 自动推进任务的成功标准是产生可接力的目标进展、有效 owner handoff、稳定 typed blocker/human gate，或修复阻断目标推进的根因；不要把重复检查、重复同一动作、队列为空、测试通过或 read-model 清洁当作推进。
- 用户要求“彻底落地 / 全部落地 / 一步到位 / 完善后立刻吸收 / 持续推进直到完成 / 能做的都做掉”等目标态交付时，最终声称完成前必须执行“完成度审计”（Plan Completion Audit）。
- 完成度审计的验收项来自用户最新目标、原始规划、已落盘 plan/runbook/contract 或 lane 目标，并用中文逐项给出 `done / partial / not_started / blocked`、完成度、新鲜证据、缺口和后续动作。
- `100%` 需要 fresh claim-appropriate evidence：文档或结构目标可由 fresh render、schema、diff 或检查证明；行为、runtime、release、currentness 或 owner claim 必须有 executable/live/artifact/receipt evidence。
- 同类 bug、CI 失败、release gate、远端同步、auth/secret、runtime authority、路径/工具边界、工作流漂移等问题形成可复用经验后，写回拥有该事实或合同的 repo-native authority surface；一次性现象或未验证猜测不固化。
