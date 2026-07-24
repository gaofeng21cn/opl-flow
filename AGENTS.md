OPL Flow 是可选的、默认进入 App Official Profile 的 OPL Package；它不构成
OPL Base、OPL App、Standard、Full、其他 Package 或普通 Codex 的 readiness 前置。

- Package、carrier、executor 必须分层。`opl-flow` 是稳定 Package identity；
  Codex Plugin Manager 只是当前首个 carrier adapter，Codex CLI 只是当前首个
  executor。切换 executor 不得重装 Package，或丢失用户 Profile、偏好和已存在任务。
- Package 与 capability 依赖默认只检查稳定 identity 是否 present/callable。不得把
  SemVer、ABI、lock、payload、receipt、digest、provenance 或 shared release cohort
  加回普通组合与 readiness 门禁；breaking interface 使用新 identity 或 owner adapter。
- OPL Flow 可以声明 Profile 与 capability intent；OPL App 不解析 Flow 的 companion
  Skill/Tool/Plugin/MCP 清单，只消费 Framework 对实际平台状态的通用投影。
- First-party OPL Flow bytes 由 Package owner 独立发布到 per-Package GHCR
  `latest-stable`。shared manifest 只服务 Full/offline/integration-test/QA 快照，
  不是普通安装、更新或 currentness 权威。
- 修改用户 `~/.codex/AGENTS.md` 必须保留 target SHA stale-write 检查、修改前备份和
  原子替换；这是 user-owned personalization 的窄安全不变量，不得扩张成通用 Package
  lock、payload、receipt 或 transaction engine。
- 当前 contracts/source/tests 仍可能实现旧 Framework lifecycle。文档必须把
  `current transitional implementation` 与 `target architecture` 分开；只有真实
  platform、install、update、restart 和 executor readback 才能证明迁移完成。

<!-- CODEGRAPH_START -->
## CodeGraph

- 本仓库使用本地 `.codegraph/` 索引；该目录不得纳入 Git。
- 定义、调用、影响范围和代码路径等结构检索优先使用 CodeGraph；字面文本检索使用 `rg`。
- 索引缺失或过期时运行 `codegraph init .` 或 `codegraph sync .`。
<!-- CODEGRAPH_END -->
