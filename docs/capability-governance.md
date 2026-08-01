# OPL Flow Composition Architecture

Owner: `opl-flow`
Purpose: `flow_package_composition_ssot`
State: `active_contract_partially_migrated_runtime_transitional`
Machine boundary: 本文是 OPL Flow 仓的组合架构 SSOT。Flow machine contract
已经开始迁移，但 Framework/runtime、carrier 安装与 fresh readback 仍处于兼容期。
本文不把部分合同迁移提升为安装或发布终态；当前行为仍以 contracts、source、
tests、平台 inventory 和 fresh readback 为准。

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

产品定位是“Codex 体验基线 + 工作协同控制层”。Flow 不只拥有总账和并发语义，
也拥有精简 Profile、模型建议、推荐能力意图、渐进主入口和通用 Fleet Skill；但
安装生效、App Auto、UI 持久化和平台 readback 仍由各自 owner 负责。

Package 是唯一安装单元。Skill、Tool、Plugin、MCP、profile 和 model recommendation
是 Package 暴露的 capability，不获得第二套 App 清单或独立 OPL lifecycle。

## Three Layers And One Publication Axis

```text
Package     = executor-neutral identity, capabilities and dependency intent
Publication = owner source/tag and official GHCR bytes/current alias
Carrier     = local install/list/update/remove and fresh installed readback
Executor    = discovery and execution route for installed capabilities
```

`opl-flow` 是稳定 Package identity。GHCR 是 publication store/source，不是
carrier。Codex Plugin Manager 是当前 carrier adapter，不是 Package identity 或生态
authority；Codex CLI 是当前唯一正式生产 executor，不是 descriptor 格式。

当前只维护一条 Codex production path。Git/local 中性 adapter 仅用于证明 OPL 公共
Package、status 和 action 合同不依赖 Codex plugin id、marketplace、home/path 或
manifest shape；它不是第二条正式 carrier，也不建设 Claude/Hermes 产品。

未来增加或切换 executor 时只重新检查该 route 的 callability，不得重装 Flow，也
不得丢失 `~/.codex/AGENTS.md`、`~/.codex/TASTE.md`、用户偏好、已存在任务或
其他 Package/capability 状态。若某 carrier 持有唯一物理 bytes 且被移除，fresh
platform readback 必须报告 physical unavailable，不能由 App metadata 伪造 installed。

## Authority Map

| Owner | Owns | Must not own |
| --- | --- | --- |
| OPL Flow | Package identity、最小 Profile source、model recommendation、experience-baseline 与 specialized intent、六动作主路由、冲突/迁移意图。 | App Auto/UI/persistence、平台 installed truth、其他 Package、中央版本求解。 |
| Package owner / publication | 独立 source/tag、per-Package GHCR official bytes 和自己的 `latest-stable`。 | 本机 install/update/remove、installed truth、shared family currentness。 |
| Carrier platform | 自己承载的 install/list/update/remove、physical bytes、platform currentness 和恢复。 | OPL identity、业务状态、其他 carrier truth。 |
| Executor adapter | 把已安装 capability 暴露给一个 executor，并 fresh 检查 callability。 | Package 安装、用户 Profile ownership、其他 executor route。 |
| OPL Base / Framework | 薄 OCI 下载/校验/bytes handoff、动态 installed discovery、presence/callability、generic status/actions 和 executor-route 聚合。 | 本机 lifecycle owner、第二套 resolver、installed lock、payload、receipt、LKG、materializer、固定 Flow companion 清单。 |
| OPL App | 一个 Official Profile、首次安装/显式 Restore、统一 Settings 状态和用户偏好。 | 解析 Flow companion Skill/Tool/Plugin/MCP 清单、Package 版本选择或 lifecycle 镜像。 |
| Full / release tooling | 某次 Full/offline/integration-test/QA 构建实际选择 bytes 的精确快照。 | 普通安装、更新、composition 或 `latest-stable`。 |

## Three Status Planes And Presence-Only Composition

Capability identity 使用 `(kind, id)`；Package dependency 使用稳定 Package 或
capability identity。Policy v4 将结果分成三个平面：

- `package_operational` 只由 Flow 本体和 `requires` 的 presence/callability 决定；
- `experience_baseline` 是默认体验下限，缺失时输出 `degraded`、failure IDs 和
  owner-supported repair command，但 `package_operational` 仍为 true；
- `specialized_capabilities` 只观察 `compatible_optional` discovery，缺失是正常状态，
  不触发 managed install 或 repair。

普通解析不比较 SemVer、ABI、exact digest、lock、payload、receipt、provenance 或
family cohort。

解析顺序保持最小：

1. 从实际 carrier/platform fresh inventory 发现 identity。
2. 检查 required identity 是否 present，并对选定 route 检查 callability。
3. required 缺失时调用该 identity 的 carrier ensure；仍失败只使直接 dependent unavailable。
4. baseline 缺失时提供 repair，optional 缺失时只报告 absent。
5. unrelated Package、App、Base 和其他 executor route 继续工作。

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

GHCR 是官方 publication store/source，不是 carrier，也不定义本机 installed truth。
Base 只在 Codex Plugin Manager 无法直接消费 OCI 时保留薄 OCI 下载、校验与 bytes
handoff；配置的 carrier 负责 install/update/remove 和 fresh installed readback。
Plugin/config/cache 交给 Codex，Flow Package runtime adapter 声明非 Plugin
Profile surfaces 的应用方式，carrier 仍须把完整 Package 一并安装和 readback。

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

## Codex-First Delivery

当前正式生产链保持一条：

```text
owner publication in GHCR
  -> Base thin OCI byte acquisition
  -> Codex carrier adapter
  -> Codex CLI executor
```

这条主路径优先复用 Codex 的 Plugin/config/cache 能力，降低当下开发和维护成本。
OPL 只拥有未来迁移必须稳定的 Package/capability identity、Profile、用户偏好、
task references 及 generic status/actions。Git/local 中性 proof 只验证这些公共字段
可脱离 Codex 私有形状工作；不并行实现第二套 GUI、carrier 产品或 executor。

## User Profile Safety

用户 Profile 是这套简化中唯一保留的窄自定义写入安全协议：

1. 读取目标 `~/.codex/AGENTS.md` 并记录 original SHA。
2. 修改前备份原文件。
3. 只删除已知 marker block；未标记偏好交给语义合并或用户 review。
4. Apply 前再次比较 target SHA；变化即 stale-write fail closed。
5. 校验候选后用同目录原子替换，失败保持原文件。

当前实现可能生成 merge packet 和 rollback receipt，但 Framework 已不再暴露
Profile apply 命令；reviewed bytes 只由 owner-controlled Profile workflow 写回。
目标只保护上述用户文件结果，不把 packet、receipt 或 transaction state 扩张成所有
Package 的组合依赖。

## App And Workflow Boundaries

App 只消费 Framework 的 generic installed/callable projection，可以分组、展示和调用
owner-projected actions。App 不解析 Flow 的 `requires`、`experience_baseline` 或
`compatible_optional`，不保存第二份 Skill/Plugin/Tool/MCP/model inventory，也不从
Codex plugin list 推断完整 Package installed state。

`opl_flow_context` 只是已安装 Flow 的状态元数据，不是 base prompt。只有 Framework
fresh projection 证明 `opl-flow` 已安装时才能注入；Flow 缺席时字段必须完全省略。

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

截至 2026-08-01，`contracts/workflow-policy.json` v4 已删除普通 capability 的
exact version、install-source、lifecycle-owner、fixed Standard/Full convergence
等组合要求，并将旧 `recommends` 明确拆为 `experience_baseline`，同时通过
`compatible_optional` 表达 specialized capabilities。它仍固定声明 source/source_path、
Codex model policy 和 migration policy。
Framework Package lifecycle/runtime 仍包含 resolver、lock/payload、receipt、
rollback 和 provenance compatibility fields。

因此当前命令仍走 compatibility lifecycle，不能从 contract v4 或本文推断 target
已落地。删除旧 reader/writer 前至少需要 fresh terminal proof：

- per-Package GHCR `latest-stable` 独立提供 bytes，shared manifest 不参与普通选择；
- configured carrier 独立执行 install/update/remove，并从本机 fresh read back；
- required identity 仅凭 presence/callability 成功，缺失只局部影响 dependent；
- Standard/Full 使用同一 Official Profile，Flow 卸载后不会被后台装回；
- App 不解析 Flow companion 清单且仍能完整展示状态；
- 正式 Codex carrier/executor 路径完成安装、发现和调用；
- 最小 Git/local 中性 adapter proof 证明公共合同没有 Codex 私有必填字段，且不形成
  第二 executor 产品；
- Profile stale-write、backup、atomic apply 在并发修改和失败场景均有 fresh readback。

Docs、schema、unit tests、dry-run 或候选分支都不是这些终态证明。
