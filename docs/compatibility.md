# OPL Flow Compatibility And Positioning

Owner: `gaofeng`
Purpose: `flow_positioning`
State: `active_source_contract`
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
| `skills/develop-and-deliver` | 多步骤软件实现、验证、fresh-main 吸收与真实交付。 | 领域 truth、发布授权或独立 Package lifecycle。 |
| `skills/github-ssot-patrol` | 基于 fresh SSOT 巡检 GitHub CI、open PR 和 open issue，并确定性收口。 | GitHub mutation 授权、产品 truth 或自动合并。 |
| `skills/opl-doc` | 以 live repo truth 治理开发文档语义、唯一 owner 和 stale surface。 | Consumer repo truth、固定文档布局或第二套工作总账。 |
| `skills/task-mode-gate` | 约束真实发布、部署、迁移、公共或破坏性 mutation。 | 普通开发方法论或只读任务门禁。 |
| `skills/recover-codex-tasks` | 基于本机任务数据库和证据恢复中断工作。 | 伪造任务状态、外部 authority 或自动归档。 |
| 11 个 bundled specialist Skills | 提供代码审查、pre-push、文档站、文档结构、决策记录、prose、显式双语翻译、authoring leakage、简化、stacked PR 和浏览器 GIF 能力；`gh-stack` 与成对的 `ffmpeg`/`ffprobe` 由 Framework baseline 安装管理。 | 第二套开发方法论、DeepSeek Harness Agent Notes/归档 ledger，或每个任务预加载全部方法。 |
| Ponytail | Retired conflict: hooks 和 broad main persona 不属于最小 Flow Profile。 | 独立显式安装的 audit/review capability。 |
| OPL App | 可选 GUI；一个 Official Profile 和统一状态展示。 | Flow policy parser、companion list、Package lifecycle 或 installed mirror。 |
| OPL Base / Framework | 编译 Flow policy，生成 generic materialization/status/build-lock projection，调用 owner adapter，并完成 fresh readback。 | 决定默认能力语义、维护第二份静态 catalog 或让 App profile 反向定义 Flow。 |

## Installed Surfaces

Flow Package 可以暴露：

- `~/.codex/AGENTS.md` minimal runtime Profile；
- `~/.codex/TASTE.md` non-runtime authoring source；
- `skills/opl-flow`；
- `skills/codex-app-owner-migration`；
- `skills/coordinate-concurrent-tasks`；
- `skills/develop-and-deliver`；
- `skills/github-ssot-patrol`；
- `skills/opl-doc`；
- `skills/task-mode-gate`；
- `skills/recover-codex-tasks`；
- `skills/opl-fleet`；
- `skills/dsh-archive-agent-notes`；
- `skills/dsh-code-review`；
- `skills/dsh-doc-site-sync`；
- `skills/dsh-doc-standards`；
- `skills/dsh-find-simplifications`；
- `skills/dsh-merging-stacked-prs`；
- `skills/dsh-pre-push-checks`；
- `skills/dsh-prose-standard`；
- `skills/dsh-translate-docs`；
- `skills/dsh-trim-cot-leakage`；
- `skills/record-browser-gif`；
- model recommendation 和其他 stable capability identities。

这些 capability 不是独立 OPL install objects。App 不解析
`contracts/workflow-policy.json`。Framework 编译 Flow 的默认/可选意图，carrier
执行物理安装，Framework 再从 owner adapter 与 carrier platform 回读实际 identity、
readiness 和 callability。App 只消费这个 projection。

## Install And Update Boundary

当前 compatibility commands 保持：

```bash
opl packages install opl-flow
opl packages update opl-flow
```

Codex Plugin Manager 与 Codex CLI 是当前正式 carrier/executor。安装、更新、
Profile materialization、publication channel 和 installed-currentness 的唯一组合边界
见 [capability-governance.md](./capability-governance.md)；操作步骤见
[new-machine-codex-setup.md](./new-machine-codex-setup.md)。本文不维护第二份 lifecycle
叙事。

## Standard And Full

OPL App Standard 和 Full 使用同一 Official Profile。Flow 是可替换的默认 root：

- Standard 可在线安装；
- Full 只携带 Flow policy 中 `offline_bundle=full` 的 seed；
- 缺失只影响 Flow；
- 用户卸载后 maintenance 不得装回；
- explicit Restore 才重新 ensure；
- credentials 和 unknown third-party MCP state 永不打包或覆盖。

Standard 的 recommended Skills 来自 Framework 编译的 installed Flow strategy。
Full 由同一 strategy 生成 `opl_flow_capability_build_lock.v1`，App 只按 lock 物化并
拒绝 unknown/missing/duplicate/drifted/unselected payload。App source manifest 只提供
选中 adapter 的 resolution hint。

安装、更新或 repair 只部署能力，不执行 `$opl-flow start`，也不创建 Dashboard、
Bead、Linear registration 或 Automation。

## Verification Boundary

Repository source check：

```bash
scripts/verify.sh
```

它验证仓库 source contracts，不执行安装，也不证明 per-Package GHCR、完整 Package、
Standard/Full、另一 executor 或本机 ordinary currentness。

Target currentness 分为 owner publication、carrier installed truth、executor
callability、experience readiness 和 Full/QA snapshot。任一层都不能替代其他层。
Framework build lock 是 Full artifact evidence，不能提升为 ordinary composition gate。
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
