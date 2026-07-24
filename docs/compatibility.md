# OPL Flow Compatibility And Positioning

Owner: `gaofeng`
Purpose: `flow_positioning`
State: `active_target_with_transitional_route`
Machine boundary: 本文是人类可读定位。组合架构由
[capability-governance.md](./capability-governance.md) 统一定义；实际安装和可调用性
由当前 machine contracts、平台 inventory 与 fresh readback 定义。

OPL Flow 是 model-native preference Profile，不是开发方法论、runtime、package
manager 或 domain authority。它可以作为一个 OPL Package 被任意兼容 App/carrier
安装，也可以完全缺席而不阻断 Base、App、Full 或其他 Packages。

当前实施是 Codex-first：Codex carrier + Codex CLI 是唯一正式生产路径。OPL 保留
executor-neutral 的 Package identity、Profile、偏好和公共 status/actions；不会为
长期可迁移性而并行维护 Claude/Hermes 产品。

## Positioning Matrix

| System | What Flow keeps | What Flow does not own |
| --- | --- | --- |
| Codex `AGENTS.md` / skills | 简短的持久偏好与按需 Skill。 | Project facts、source、tests、runtime 或 domain truth。 |
| Future executor | 只在未来确有产品选择时增加 adapter，并复用同一 Flow identity、Profile 和偏好。 | 当前并行建设的 Claude/Hermes 产品、第二份 Package 或中央 executor matrix。 |
| GHCR publication | Flow owner 的官方 Package bytes 和 `latest-stable` source。 | 本机 carrier、install/update/remove 或 installed truth。 |
| Codex Plugin Manager | 当前正式 Plugin/config/cache carrier adapter。 | Flow identity、完整 Package authority、其他 carrier 或生态 currentness。 |
| Git/local neutral proof | 验证公共 Package/status/action 合同不需要 Codex 私有字段。 | 第二个正式 carrier、第二 executor 产品或 ordinary currentness。 |
| `skills/coordinate-concurrent-tasks` | 有界协调现有 owner、fresh-main integration 和 archive-readiness review。 | Git/release/package mutation authority 或自动 archive。 |
| Specialist skills | 由自己的 explicit/narrow trigger 按需加载。 | Flow-managed 固定 companion readiness 清单。 |
| Ponytail | Retired conflict: hooks 和 broad main persona 不属于最小 Flow Profile。 | 独立显式安装的 audit/review capability。 |
| OPL App | 可选 GUI；一个 Official Profile 和统一状态展示。 | Flow policy parser、companion list、Package lifecycle 或 installed mirror。 |
| OPL Base / Framework | 动态 discovery、presence/callability、thin adapters 和 generic projection。 | Flow-specific catalog 或 OPL-owned version/lock/payload/receipt manager。 |

## Installed Surfaces

Flow Package 可以暴露：

- `~/.codex/AGENTS.md` minimal runtime Profile；
- `~/.codex/TASTE.md` non-runtime authoring source；
- `skills/opl-flow`；
- `skills/coordinate-concurrent-tasks`；
- model recommendation 和其他 stable capability identities。

这些 capability 不是独立 OPL install objects。App 不解析
`contracts/workflow-policy.json` 来安装 companion Skills；Framework 从 carrier
platform 发现实际 installed identities，并对 required edge 只检查
presence/callability。

## Install And Update Boundary

当前 compatibility commands 保持：

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

目标普通 publication source 是 Flow owner 的 per-Package GHCR `latest-stable`。
GHCR 不执行本机 lifecycle。shared `one-person-lab-manifest:latest-stable` 只用于
Full/offline/integration-test/QA snapshot，不决定 ordinary currentness。

Base 可以下载、校验并 hand off OCI bytes；配置的 carrier 执行
install/update/remove，并以 fresh local readback 定义 installed truth。Codex
Plugin Manager 是当前正式 carrier，Codex CLI 是当前正式 executor。

Required/recommended identity 不要求 SemVer/ABI、lock、payload、receipt、digest 或
provenance match。精确 metadata 可以服务一个具体 build/release artifact 或迁移诊断，
但不参与 composition/readiness。

Script merge policy保留一条独立不变量：target SHA stale-write check、backup、candidate
validation 和 atomic apply。当前实现可能记录 rollback receipt；该 receipt 只说明
Profile mutation 的 compatibility recovery，不是通用 Package dependency。

## Standard And Full

OPL App Standard 和 Full 使用同一 Official Profile。Flow 是可替换的默认 root：

- Standard 可在线安装；
- Full 可携带 offline seed；
- 缺失只影响 Flow；
- 用户卸载后 maintenance 不得装回；
- explicit Restore 才重新 ensure；
- credentials 和 unknown third-party MCP state 永不打包或覆盖。

App carrier 更新后，当前实现可能调用 generic Framework reconciliation；目标只更新
platform 仍报告 installed 的 Packages，不把 Official Profile 变成持续 desired-state
loop。

## Verification Boundary

Repository developer check：

```bash
python3 scripts/install_local_plugin.py --verify-only
```

它验证本地 Codex Plugin/cache payload，不证明 per-Package GHCR、完整 Package、
Standard/Full、另一 executor 或本机 ordinary currentness。

Target currentness 分为 owner publication、carrier installed truth、executor
callability 和 Full/QA snapshot。任一层都不能替代其他层。Framework transitional
lock/payload fields 可读取用于兼容诊断，但不能提升为 target composition gate。
Git/local 中性 proof 只验证公共边界可替换，不替代 Codex production readback。

OPL Flow 可以将 task 标为 `SAFE_TO_ARCHIVE`，但实际 archive 仍需要 fresh user
acceptance。

## Canonical External References

- Codex customization: https://developers.openai.com/codex/concepts/customization
- Current workflow policy: `contracts/workflow-policy.json`
- Target composition SSOT: `docs/capability-governance.md`
- Claude Code skills: https://docs.anthropic.com/en/docs/claude-code/skills
- Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- GitHub Agentic Workflows: https://github.github.com/gh-aw/
