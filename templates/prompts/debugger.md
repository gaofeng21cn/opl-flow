# Debugger Compatibility Prompt

显式兼容入口，用于重复失败、flaky、跨组件或首轮根因不清。普通首轮错误由当前代理直接诊断。

1. 复现症状并定位直接断点，沿输入、状态和调用链追到真实 owner。
2. 用跨面证据支持或反驳断点；一次只测试一个可证伪假设。
3. 根因深度门包含表层症状、直接断点、跨面证据、owner 与修复路径；不足时明确写“根因未确认”。
4. 在 owner/source 边界修复并用 claim-appropriate evidence 验证；第三次失败后停止叠补丁，重审架构和 authority。
