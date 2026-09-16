# OPL Flow

本仓持有 OPL Flow 的最小用户 Profile 源码、Package/Plugin payload、workflow policy 和仓库开发工具。

- `profile/manifest.json`、`profile/modules/01-user-preferences.md`、`templates/AGENTS.md` 与 `templates/TASTE.md` 是 Profile 权威链；`contracts/workflow-policy.json` 持有机器策略。
- OPL Framework 持有正式安装、更新、Profile materialization、carrier reconciliation 和 installed currentness；本仓只验证 source contracts。
- OPL Flow 不拥有 consumer repo 的 `AGENTS.md`、项目事实或领域 truth；consumer repo Profile 元数据和 legacy projection 迁移归 Framework。
- 目标架构、迁移状态和安装说明留在 `README.md` 与 `docs/`，不得用根规则替代 contracts、source、tests 或 fresh readback。
- 默认验证运行 `scripts/verify.sh`；涉及完整 payload 或插件 contract 时运行 `scripts/verify.sh full`。

<!-- CODEGRAPH_START -->
## CodeGraph

- 本仓库使用本地 `.codegraph/` 索引；该目录不得纳入 Git。
- 定义、调用、影响范围和代码路径等结构检索优先使用 CodeGraph；字面文本检索使用 `rg`。
- 索引缺失或过期时运行 `codegraph init .` 或 `codegraph sync .`。
<!-- CODEGRAPH_END -->

- GitHub 上自己新建的对外文本用英文书写：commit subject/body、PR 标题与正文、Issue、comment、Release 正文与 Release Notes。产品名、代码标识、路径、命令与原始引用除外。他人写的 Issue、PR 或 comment，无论对方用什么语言，回复沿用对方的语言；历史中已有的非英文 commit 保持原样。

- 本 Package 的唯一发布机制是 OCI：Framework projection 声明的 `publication_ref` 与 `latest-stable`。不要创建 GitHub Release 页面或附件，也不要新增 ZIP、wheel 等平行发布脚本；annotated tag 只用于绑定源码，版本说明写在仓库文档与 Git 历史里。共享规则由 Framework 的 `docs/delivery/artifact-package-lifecycle-boundary.md` 持有。
