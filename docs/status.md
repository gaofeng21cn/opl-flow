# OPL Flow Active Truth

Owner: `gaofeng`
Purpose: `active_truth_and_migration_status`
State: `contract_partially_migrated_framework_runtime_transitional`
Machine boundary: 本文只记录当前与目标的差距。目标架构由
[Composition Architecture](./capability-governance.md) 统一定义；当前机器行为由
contracts、source、tests、platform inventory 和 fresh readback 定义。

## Target SSOT

OPL Flow 的目标边界已经收敛：

- Flow 是可选、默认进入 App Official Profile 的
  `OPL Package(kind=workflow_profile)`，不是任何产品的 readiness 前置。
- Package、carrier、executor 三层分离，publication 是独立轴；GHCR 只存储并提供
  official bytes，不是本机 carrier。
- Codex Plugin Manager 和 Codex CLI 是当前唯一正式 carrier/executor 路径；
  Git/local 中性 proof 只防公共合同被 Codex 私有字段锁死。
- required dependency 默认只检查 identity presence/callability，不使用
  version/ABI/lock/payload/receipt/digest/provenance 组合门禁。
- Flow owner 独立向 per-Package GHCR 发布并推进自己的 `latest-stable`。
- shared manifest 只服务 Full/offline/integration-test/QA 快照。
- App 不解析 Flow companion Skill/Tool/Plugin/MCP 清单，只消费实际平台状态的通用投影。
- executor 切换不重装 Package，也不丢 Profile、用户偏好或已有任务。
- user Profile 写入保留 target SHA stale-write、backup 和 atomic replace 这一个窄安全协议。

## Current Transitional Truth

Flow machine contract 已部分迁移，但 Framework/runtime 和真实 carrier lifecycle
仍在兼容期。以下 current implementation 不能被目标文档覆盖或假装已经删除：

| Surface | Current fact | Target gap |
| --- | --- | --- |
| `contracts/workflow-policy.json` v3 | 已删除普通 capability 的 exact version、install-source、lifecycle-owner 和 fixed Standard/Full convergence；仍固定 provides/requires/recommends、source 与 migration policy。 | 收敛为 Package-owned intent；普通依赖只检查 identity；App 不解析 companion list。 |
| Framework `opl packages` | 当前正常命令仍负责 resolver、install/update、lock/payload、receipt/rollback 和 profile migration。 | Base 只下载/校验/handoff OCI bytes；carrier 执行本机 lifecycle；Framework 动态聚合 presence/callability 与 generic projection。 |
| Codex carrier/executor | Codex Plugin Manager 和 Codex CLI 是唯一正式生产路径；Repository developer tooling 也能投影 Plugin/Skills。 | Plugin readback 不能单独证明完整 Package；最小 Git/local proof 只验证公共合同中性，不形成第二产品。 |
| App Standard/Full | 当前文档和 contracts 仍可能各自携带 payload/closure 或固定清单语义。 | 同一 Official Profile；Full 只增加 offline seed；卸载后不后台装回。 |
| Publication | GHCR/shared manifest 的旧 release orchestration 仍可能参与普通 selection。 | Owner per-Package GHCR `latest-stable` 只定义 official publication；shared manifest 退出普通更新，本机 truth 由 carrier readback 定义。 |

现行可执行 route 仍是：

```bash
opl packages install opl-flow
opl packages update opl-flow
```

这些命令成功只证明当前 compatibility implementation 的结果；不能证明目标
manager 已删除或 executor-neutral composition 已实现。

## Migration Order

1. 在已迁移的 Flow contract v3 上增加最小 descriptor/carrier dual-read；新
   consumer 只依赖 identity、presence、callability 和 generic action。
2. per-Package GHCR `latest-stable` 成为普通 Flow publication source；Base 只做
   OCI byte acquisition，carrier 执行 lifecycle；shared manifest 降级为
   Full/offline/test/QA snapshot。
3. App Official Profile 在 Standard/Full 只用于 first install 和 explicit Restore；
   App 删除 companion policy reader。
4. 闭合唯一正式 Codex production path，并用最小 Git/local adapter proof 验证公共
   合同中性；不建设第二 executor 产品。
5. 所有 retained consumer 切换后停止旧 writer，再删除 resolver、lock、payload、
   receipt、provenance gates 和固定 registry；禁止长期双写。

Profile personalization 可独立先保留 stale-write、backup、atomic apply。它保护
user-owned file，不授权保留通用 Package transaction engine。

## Terminal Proof

迁移完成至少需要以下 fresh terminal evidence：

- owner 的 Flow GHCR `latest-stable` 独立推进，Base/App/其他 Package/shared
  manifest 不变；
- configured carrier 独立 install/update/remove，并以 fresh local readback 定义
  installed truth；
- clean install 仅以 identity presence/callability 补齐 required capability；
- Standard/Full 安装同一 Profile，用户卸载 Flow 后重启和 maintenance 不装回；
- App 没有读取 Flow companion list，Settings 状态仍与 platform readback 一致；
- 完整 Flow Package 在正式 Codex carrier/executor 路径可发现和调用；
- Git/local 中性 proof 通过 generic identity/status/action，不要求 Codex plugin 私有
  字段，也不暴露第二 executor 产品；
- 并发修改 Profile 时 stale-write fail closed；正常写入有 backup 和 atomic readback；
- 旧 manager writer/reader 无 active caller 且已物理删除。

Flow 发布资格分成两个层级。普通版本由 `scripts/qualify_install.py --plan` 选择
`routine-release`：只在一个参考平台验证 fresh 与 upgrade，同时绑定同一 owner commit
和 GHCR digest。upgrade 基线必须是 candidate 晋升前 fresh 回读到的公开
`latest-stable`，不能按版本号猜测所谓 N-1。

六格 macOS/Linux/Windows-WSL fresh+upgrade matrix 属于一次性的或变化触发的
`system-certification`，不是每个 candidate 的门禁。首次正式体系认证、carrier、
Package payload contract、Profile mutation、executor discovery、支持平台或安全边界
变化、真实安装事故，以及 owner 明确发起的周期复认证才触发它。system certification
还要求 Core 在 Linear/Fleet 缺席时 current，并由至少一个新 Codex session 实际调用
已安装 Skill。0.1.29 承担当前体系首次认证；后续未触发上述边界变化的普通内容版本
只走 routine release。

0.1.30 源码候选增加三个核心 Skill、来源感知迁移、capability-aware Profile 路由和
`$opl-flow start` onboarding contract，属于 Package payload、Profile 和 executor
discovery 边界变化，因此不能继承 0.1.29 的安装资格。若后续进入正式 publication，
必须以 0.1.30 自身不可变字节重新完成对应 system certification；当前源码、测试、
Dashboard live receipt 或 canonical main 都不等于 Release，也不授权在本任务中发布。

这两种资格都只绑定当前 candidate 的取证，不形成跨 Package 版本锁或 shared release
cohort。Windows App mapped-home 属于独立 consumer successor，不计入 Windows/WSL
carrier receipt。

Docs、schema、unit tests、dry-run、candidate、GHCR push 或 shared snapshot 都不是单独
终态证明。

## Repository Verification

```bash
scripts/verify.sh full
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
git diff --check
```

这些检查只证明 Flow repo 文档、已部分迁移的 contract 和 Plugin source 自洽，
不提升安装、发布、App、Full 或 Framework/runtime migration 状态。
