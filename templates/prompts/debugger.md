# Debugger Lens

用于 bug、失败、异常行为、性能回退或重复停滞。使用 `systematic-debugging` 复现、隔离变量并验证候选根因；本文件只增加 OPL 的根因深度和 owner 路由要求。

## 根因深度门

根因结论必须同时包含：

1. 表层症状：用户或系统看到什么。
2. 直接断点：哪个命令、projection、contract、owner route、gate、queue、read model 或外部依赖在什么输入下失败。
3. 跨面证据：相邻 truth surface 如何支持或反驳该断点。
4. owner 与修复路径：谁能合法改变该断点，应修代码、contract、read model、owner route，还是进入 human gate。

少于四层只能报告“根因未确认”。状态标签、错误码、queue empty、no live session 或“缺少 X”都不是完整根因。

对重复问题补充 break-loop 结论：已有机制为什么没拦住、以后查哪个 source of truth、应写回哪个 authority surface。根因确认后，如果用户授权包含修复，同一代理继续应用 Executor 和 Verifier lenses；只有用户明确只要诊断或存在真实 gate 才停止。
