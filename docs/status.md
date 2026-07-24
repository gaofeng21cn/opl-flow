# OPL Flow Active Truth

Owner: `gaofeng`
Purpose: `active_truth_and_migration_status`
State: `target_documented_implementation_transitional`
Machine boundary: 本文只记录当前与目标的差距。目标架构由
[Composition Architecture](./capability-governance.md) 统一定义；当前机器行为由
contracts、source、tests、platform inventory 和 fresh readback 定义。

## Target SSOT

OPL Flow 的目标边界已经收敛：

- Flow 是可选、默认进入 App Official Profile 的
  `OPL Package(kind=workflow_profile)`，不是任何产品的 readiness 前置。
- Package、carrier、executor identity 分离；Codex Plugin Manager 和 Codex CLI
  分别只是当前首个 carrier adapter 和 executor。
- required dependency 默认只检查 identity presence/callability，不使用
  version/ABI/lock/payload/receipt/digest/provenance 组合门禁。
- Flow owner 独立向 per-Package GHCR 发布并推进自己的 `latest-stable`。
- shared manifest 只服务 Full/offline/integration-test/QA 快照。
- App 不解析 Flow companion Skill/Tool/Plugin/MCP 清单，只消费实际平台状态的通用投影。
- executor 切换不重装 Package，也不丢 Profile、用户偏好或已有任务。
- user Profile 写入保留 target SHA stale-write、backup 和 atomic replace 这一个窄安全协议。

## Current Transitional Truth

本轮只修改人类可读文档。以下 current implementation 仍存在，不能被目标文档
覆盖或假装已经删除：

| Surface | Current fact | Target gap |
| --- | --- | --- |
| `contracts/workflow-policy.json` | 固定提供、required、recommended、source/provenance、migration 和 retirement metadata。 | 迁移为 Package-owned intent；App 不解析 companion list；普通依赖只检查 identity。 |
| Framework `opl packages` | 当前正常命令仍负责 resolver、install/update/optimize、lock/payload、receipt/rollback 和 profile migration。 | 收敛为 native carrier adapter、dynamic discovery、presence/callability 和 generic projection。 |
| Codex Plugin carrier | Repository developer tooling 与正常安装都能投影 Plugin/Skills。 | Plugin readback 不能单独证明完整 Package；需非 Codex/中性 adapter proof。 |
| App Standard/Full | 当前文档和 contracts 仍可能各自携带 payload/closure 或固定清单语义。 | 同一 Official Profile；Full 只增加 offline seed；卸载后不后台装回。 |
| Publication | GHCR/shared manifest 的旧 release orchestration 仍可能参与普通 selection。 | Owner per-Package `latest-stable` 为普通发布源；shared manifest 退出普通更新。 |

现行可执行 route 仍是：

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

这些命令成功只证明当前 compatibility implementation 的结果；不能证明目标
manager 已删除或 executor-neutral composition 已实现。

## Migration Order

1. Framework 和 Flow machine owners 增加最小 descriptor/native adapter dual-read；
   新 consumer 只依赖 identity、presence、callability 和 generic action。
2. per-Package GHCR `latest-stable` 成为普通 Flow source；shared manifest 降级为
   Full/offline/test/QA snapshot。
3. App Official Profile 在 Standard/Full 只用于 first install 和 explicit Restore；
   App 删除 companion policy reader。
4. 用 Codex Plugin Manager 和一个非 Codex/中性 adapter 证明 carrier/executor 解耦。
5. 所有 retained consumer 切换后停止旧 writer，再删除 resolver、lock、payload、
   receipt、provenance gates 和固定 registry；禁止长期双写。

Profile personalization 可独立先保留 stale-write、backup、atomic apply。它保护
user-owned file，不授权保留通用 Package transaction engine。

## Terminal Proof

迁移完成至少需要以下 fresh terminal evidence：

- owner 的 Flow `latest-stable` 独立更新，Base/App/其他 Package/shared manifest 不变；
- clean install 仅以 identity presence/callability 补齐 required capability；
- Standard/Full 安装同一 Profile，用户卸载 Flow 后重启和 maintenance 不装回；
- App 没有读取 Flow companion list，Settings 状态仍与 platform readback 一致；
- 完整 Flow Package 在 Codex carrier 与一个非 Codex/中性 adapter 可发现和调用；
- executor switch 前后 Profile、偏好和已有任务一致，只有 route readiness 改变；
- 并发修改 Profile 时 stale-write fail closed；正常写入有 backup 和 atomic readback；
- 旧 manager writer/reader 无 active caller 且已物理删除。

Docs、schema、unit tests、dry-run、candidate、GHCR push 或 shared snapshot 都不是单独
终态证明。

## Verification For This Docs Tranche

```bash
scripts/verify.sh full
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
git diff --check
```

这些检查只证明 Flow repo 文档、现有 contract 和 Plugin source 自洽，不提升
安装、发布、App、Full 或 target migration 状态。
