# OPL Flow Composition Architecture

Owner: `opl-flow`
Purpose: `flow_package_composition_ssot`
State: `target_planned_with_transitional_machine_contract`
Machine boundary: 本文是 OPL Flow 仓的组合架构 SSOT。它定义目标边界和迁移
门禁，不证明当前 `contracts/workflow-policy.json`、Framework、App、carrier、
安装或发布已经完成迁移。当前机器行为仍以 contracts、source、tests、平台
inventory 和 fresh readback 为准。

## Top-Level Model

```text
OPL Base        ~= R
OPL App         ~= RStudio / replaceable GUI and deployment carrier
OPL Package     ~= R Package
OPL Flow        = OPL Package(kind=workflow_profile)
```

OPL Flow 是可选 Package，也是 App Official Profile 的默认 root 之一。默认安装是
产品便利性，不是生态依赖：缺少 Flow 不得阻断 Base、App、Standard、Full、普通
Codex、其他 Package 或 domain readiness。

Package 是唯一安装单元。Skill、Tool、Plugin、MCP、profile 和 model recommendation
是 Package 暴露的 capability，不获得第二套 App 清单或独立 OPL lifecycle。

## Three Independent Identities

```text
Package  = executor-neutral identity, capabilities and dependency intent
Carrier  = GHCR/Git/Codex Plugin Manager/OS or local platform that carries bytes
Executor = Codex CLI/Claude Code/Hermes Agent/future execution route
```

`opl-flow` 是稳定 Package identity。Codex Plugin Manager 是当前首个 carrier
adapter，不是 Package identity、installed truth 或生态 authority；Codex CLI 是
当前首个 executor，不是 descriptor 格式。

切换 executor 只重新检查该 executor route 的 callability。它不得重装 Flow，也不得
丢失 `~/.codex/AGENTS.md`、`~/.codex/TASTE.md`、用户偏好、已存在任务或其他
Package/capability 状态。若某 carrier 持有唯一物理 bytes 且被移除，fresh platform
readback 必须报告 physical unavailable，不能由 App metadata 伪造 installed。

## Authority Map

| Owner | Owns | Must not own |
| --- | --- | --- |
| OPL Flow | Package identity、最小 Profile source、capability intent、冲突/迁移意图、model recommendation。 | App/Standard/Full readiness、平台 installed truth、其他 Package、中央版本求解。 |
| Package owner | 独立 source/tag、per-Package GHCR bytes 和自己的 `latest-stable`。 | shared family currentness、App/Base/其他 Package 发布节奏。 |
| Carrier platform | 自己承载的 install/list/update/remove、physical bytes、platform currentness 和恢复。 | OPL identity、业务状态、其他 carrier truth。 |
| Executor adapter | 把已安装 capability 暴露给一个 executor，并 fresh 检查 callability。 | Package 安装、用户 Profile ownership、其他 executor route。 |
| OPL Base / Framework | 薄 OCI/native adapters、动态 installed discovery、presence/callability、generic status/actions 和 executor-route 聚合。 | 第二套 resolver、installed lock、payload、receipt、LKG、materializer、固定 Flow companion 清单。 |
| OPL App | 一个 Official Profile、首次安装/显式 Restore、统一 Settings 状态和用户偏好。 | 解析 Flow companion Skill/Tool/Plugin/MCP 清单、Package 版本选择或 lifecycle 镜像。 |
| Full / release tooling | 某次 Full/offline/integration-test/QA 构建实际选择 bytes 的精确快照。 | 普通安装、更新、composition 或 `latest-stable`。 |

## Presence-Only Composition

Capability identity 使用 `(kind, id)`；Package dependency 使用稳定 Package 或
capability identity。`requires` 表示“存在且可调用”，`recommends` 表示默认便利
组合。普通解析不比较 SemVer、ABI、exact digest、lock、payload、receipt、
provenance 或 family cohort。

解析顺序保持最小：

1. 从实际 carrier/platform fresh inventory 发现 identity。
2. 检查 required identity 是否 present，并对选定 route 检查 callability。
3. 缺失时调用该 identity 的 carrier ensure；仍失败只使直接 dependent unavailable。
4. unrelated Package、App、Base 和其他 executor route 继续工作。

稳定 identity 只做向后兼容扩展。Breaking interface 发布新 identity，或由 owner
保留兼容 adapter；不为此建立中央 version/ABI solver。

A lock records a resolution for a concrete artifact in the transitional
implementation. It is never an input to target Flow composition.同理，payload、
receipt 和 provenance 可以作为某次发布、诊断或历史证据存在，但不能成为
dependency、installation 或 readiness 门禁。

## Publication And Distribution

First-party Flow 的完整官方 Package bytes 继续由 owner 独立发布：

```text
Flow owner source/tag
  -> ghcr.io/<owner>/one-person-lab-packages/opl-flow:<immutable-tag>
  -> ghcr.io/<owner>/one-person-lab-packages/opl-flow:latest-stable
```

GHCR 是官方发布存储，不定义本机 installed truth。Base 只在 Codex Plugin Manager
无法直接消费 OCI 时保留薄 OCI 下载 adapter；Plugin/config/cache 交给 Codex，
Flow Package 中非 Plugin 的完整 runtime/profile surfaces 仍须一并安装和 readback。

`one-person-lab-manifest:latest-stable` 退出普通 Flow 更新权威。shared manifest/
Release Set 只用于 Full、offline、integration test 和 release QA 的精确输入快照，
不得阻断 Flow owner 独立推进 `latest-stable`。

App Standard 和 Full 使用同一个 App Official Profile。Flow 可以是其默认 root，但：

- Profile 只在 first install 或用户显式 Restore official combination 时应用；
- Full 只增加 offline seed；
- 用户卸载 Flow 后，startup、daily maintenance 和 App update 不得静默装回；
- App 不读取 `contracts/workflow-policy.json` 来维护 companion list。

OPL Flow never bundles API keys, OAuth state, credentials, account data, or
unknown third-party MCP configuration.

## User Profile Safety

用户 Profile 是这套简化中唯一保留的窄自定义写入安全协议：

1. 读取目标 `~/.codex/AGENTS.md` 并记录 original SHA。
2. 修改前备份原文件。
3. 只删除已知 marker block；未标记偏好交给语义合并或用户 review。
4. Apply 前再次比较 target SHA；变化即 stale-write fail closed。
5. 校验候选后用同目录原子替换，失败保持原文件。

当前实现可能用 merge packet、rollback receipt 和
`opl packages profile-apply opl-flow --packet <path>` 承载该流程。目标只保护上述
用户文件结果，不把 packet、receipt 或 transaction state 扩张成所有 Package 的
组合依赖。

## App And Workflow Boundaries

App 只消费 Framework 的 generic installed/callable projection，可以分组、展示和调用
owner-projected actions。App 不解析 Flow 的 `requires`/`recommends`，不保存第二份
Skill/Plugin/Tool/MCP/model inventory，也不从 Codex plugin list 推断完整 Package
installed state。

Model precedence remains:

```text
explicit user selection
> installed Flow recommendation
> fresh executor default
> App fallback when Flow is unavailable
```

OPL Flow 可以定义 `ACTIVE`、`SAFE_TO_ARCHIVE` 等协作语义；实际 archive 仍需
fresh user acceptance。Flow 不拥有 project、release、runtime、domain 或 task truth。

## Current Transitional Gap

截至 2026-07-24，`contracts/workflow-policy.json`、Framework Package lifecycle 和
相关 tests 仍包含固定 capability source/provenance、resolver、lock/payload、receipt、
rollback 和 migration semantics。本轮只重组人类可读文档；没有修改这些机器合同或
生产代码。

因此当前命令仍走 compatibility lifecycle，不能从本文推断 target 已落地。删除旧
reader/writer 前至少需要 fresh terminal proof：

- per-Package GHCR `latest-stable` 可独立安装和更新，shared manifest 不参与普通选择；
- required identity 仅凭 presence/callability 成功，缺失只局部影响 dependent；
- Standard/Full 使用同一 Official Profile，Flow 卸载后不会被后台装回；
- App 不解析 Flow companion 清单且仍能完整展示状态；
- Codex Plugin Manager 与至少一个非 Codex/中性 adapter 证明 identity 解耦；
- executor 切换不重装 Flow，也不丢 Profile 或用户偏好；
- Profile stale-write、backup、atomic apply 在并发修改和失败场景均有 fresh readback。

Docs、schema、unit tests、dry-run 或候选分支都不是这些终态证明。
