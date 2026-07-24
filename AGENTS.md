# OPL Flow

本仓持有 OPL Flow 的最小用户 Profile 源码、Package/Plugin payload、workflow policy 和仓库开发工具。

- `profile/manifest.json`、`profile/modules/01-user-preferences.md`、`templates/AGENTS.md` 与 `templates/TASTE.md` 是 Profile 权威链；`contracts/workflow-policy.json` 持有机器策略。
- OPL Framework 持有正式安装、更新、carrier reconciliation 和 installed currentness；`scripts/install_local_plugin.py` 只用于本仓开发验证。
- OPL Flow 不拥有 consumer repo 的 `AGENTS.md`、项目事实或领域 truth；repo profile 工具只管理 `contracts/opl-native-profile.json` 元数据并移除已知 legacy marker。
- 目标架构、迁移状态和安装说明留在 `README.md` 与 `docs/`，不得用根规则替代 contracts、source、tests 或 fresh readback。
- 默认验证运行 `scripts/verify.sh`；涉及完整 payload、插件或安装工具时运行 `scripts/verify.sh full`。

<!-- CODEGRAPH_START -->
## CodeGraph

- 本仓库使用本地 `.codegraph/` 索引；该目录不得纳入 Git。
- 定义、调用、影响范围和代码路径等结构检索优先使用 CodeGraph；字面文本检索使用 `rg`。
- 索引缺失或过期时运行 `codegraph init .` 或 `codegraph sync .`。
<!-- CODEGRAPH_END -->
