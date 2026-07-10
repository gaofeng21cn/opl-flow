# Planner Lens

用于需求、范围、验收或方案存在实质不确定时。先读项目上下文，明确目标、非目标、约束、风险和成功标准。

## 工作方式

1. 优先从源码、docs、contracts、tests 和 runtime/readback 获取答案，只询问真正阻塞的问题。
2. 只有存在实质取舍时比较方案，并直接给出推荐及理由；不要机械提供 2 至 3 个选项。
3. 使用 `risk-based-development-flow` 选择风险档、验证预算、证据类型和是否需要 TDD。
4. Inline 计划只写到足以指导当前会话实施；Durable 计划写入项目内合适文件，并注明范围、interfaces、步骤、风险和验收。
5. 不把假设写成事实，不用规划仪式替代交付。

Planner 是 decision lens，不是停止点。除非用户明确只要计划，或存在真实 human/authority gate，同一代理应继续进入实施或诊断。
