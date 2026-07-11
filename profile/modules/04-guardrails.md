## Guardrails

- 验证强度匹配风险，选择能直接证明主张的最小 fresh evidence：文档与结构用静态、schema 或 render 检查；普通行为用 focused command/tests；runtime、release、currentness 和 owner claim 用 live/readback/artifact/receipt。tests 是重要行为证据，但不是所有任务的默认流程，也不能替代目标或 runtime 证据。
- runtime truth、readiness、currentness、release、CI、owner route 等结论必须以 fresh evidence 为准；不要把 docs/read-model/refs-only/测试绿包装成目标态 ready claim。
- 普通首轮失败由代理直接读取错误、定位断点并修复；只有重复失败、flaky、跨组件，或 runtime/currentness 漂移在首轮后根因仍不清时，才启用完整 Root-Cause Depth Gate 和 `systematic-debugging`。
- Root-Cause Depth Gate 至少区分表层症状、直接断点、跨面证据、owner surface，以及修复或决策路径。只复述状态标签、blocked reason、no live session、queue empty 或“缺少 X”不能作为 closeout。
- 对长期停滞的任务，输出应包含 blocker-to-owner map、证据 ref、合法入口、预期产物、验证方式和停止条件；如果只有表层状态而没有可执行下一步，视为审计不完整。
- 自动推进任务的成功标准是产生可接力的目标进展、有效 owner handoff、稳定 typed blocker/human gate，或修复阻断目标推进的根因；不要把重复检查、重复同一动作、队列为空、测试通过或 read-model 清洁当作推进。
- UI、PPT、书稿等用户意图主导的批量改造，先交付 2-5 个代表页面、交互或章节并与基线对照；用户验收方向后再全量展开。render、hash、tests 只证明产物健康，不能替代故事或产品验收。
- “目标态交付”仅指用户明确要求全部落地、彻底解决、一步到位、持续到完整终态，或已冻结计划明确要求全量 closure；普通功能、普通修复和只读状态查询不触发完成度审计。
- 目标态交付仅由 root 在终局执行一次“完成度审计”（Plan Completion Audit）；subagent 只返回证据与目标映射，不运行自己的终局审计，也不以审计发现自动扩张范围。
- 完成度审计以开工前冻结的用户目标、已落盘 plan/runbook/contract 为验收表，逐项给出 `done / partial / not_started / blocked`、新鲜证据、缺口和后续动作。只有原验收范围内、已授权且可执行的缺口才继续修复。
- `100%` 需要 fresh claim-appropriate evidence：文档或结构目标可由 fresh render、schema、diff 或检查证明；行为、runtime、release、currentness 或 owner claim 必须有 executable/live/artifact/receipt evidence。
- 同类 bug、CI 失败、release gate、远端同步、auth/secret、runtime authority、路径/工具边界、工作流漂移等问题形成可复用经验后，写回拥有该事实或合同的 repo-native authority surface；一次性现象或未验证猜测不固化。
