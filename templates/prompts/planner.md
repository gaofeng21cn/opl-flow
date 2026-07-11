# Planner Compatibility Prompt

显式兼容入口，仅在用户调用 planner prompt 或旧自动化依赖它时使用。普通任务由当前代理直接完成必要规划，不默认读取本文件。

当需求、范围、验收或方案存在实质不确定时：

1. 从源码、docs、contracts、tests 和 runtime/readback 明确目标、非目标、约束与成功标准。
2. 只比较真实存在取舍的方案，并给出推荐与理由。
3. 为复杂任务冻结验收表和停止条件；Inline 计划只写到足以实施，Durable 计划写回 repo-native surface。
4. 选择直接证明目标的最小 fresh evidence，不用规划仪式替代交付。
