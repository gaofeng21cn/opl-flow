# OPL Flow Docs

Owner: `gaofeng`
Purpose: `docs_index`
State: `active_index`
Machine boundary: Human-readable navigation. Current executable truth remains
in contracts, source, tests, actual platform inventory, and fresh readback.
Repository installer scripts prove only their developer/local-source path.

This support repo keeps a deliberately small docs surface. It does not need the
full OPL/MAS/MAG/RCA taxonomy unless durable material appears with a clear
owner, purpose, state, and machine boundary.

## Current Docs

| Doc | Role | Boundary |
| --- | --- | --- |
| [Composition architecture](./capability-governance.md) | Flow 仓唯一组合架构 SSOT：Package/carrier/executor、presence-only、GHCR、Official Profile 与 personalization safety | Target/planned；当前机器行为仍归 contracts/source/platform readback |
| [Active truth and migration status](./status.md) | 当前兼容实现、目标差距、迁移顺序和 terminal proof | Human-readable status；不证明安装、发布或 target 已落地 |
| [Compatibility and positioning](./compatibility.md) | Model-native、可选 Flow 与跨 executor 定位 | 不拥有 App/Base/Full/runtime/domain readiness |
| [New machine Codex setup](./new-machine-codex-setup.md) | 当前可执行安装 runbook 与目标边界 | 命令和 fresh platform/executor readback 才是本机事实 |

## Canonical Role Coverage

The repository deliberately maps canonical governance roles to existing owners instead
of creating parallel documents with duplicate prose.

| Canonical role | Owner in this repository | Why no additional document is needed |
| --- | --- | --- |
| Project positioning (`docs/project.md`) | Root `README.md`, especially `Public Role Boundary` | The repository has one small product/profile scope and no separate project portfolio. |
| Active status and plan (`docs/status.md`) | [Active truth and migration status](./status.md) | This is the single current-state, gap, migration-order, and terminal-proof owner. |
| Architecture boundary (`docs/architecture.md`) | [capability-governance.md](./capability-governance.md), with root `README.md` as public summary | One SSOT owns Package/carrier/executor and presence-only composition; other pages link to it. |
| Hard invariants (`docs/invariants.md`) | Root `AGENTS.md` for target anti-regression; `skills/opl-flow/SKILL.md` for operator route; contracts/source/tests for current behavior | Human-readable target rules cannot override transitional machine truth or prove migration. |
| Decisions (`docs/decisions.md`) | [Composition architecture](./capability-governance.md) for current target, [History and provenance](./history/README.md) plus Git history for superseded context | No duplicate active decision ledger is needed in this small repo. |

## History

[History and provenance](./history/README.md) contains dated baselines, completed
audits, and implemented designs. These records explain prior decisions but do not
define current package, installation, discovery, or readiness truth.

## Growth Rule

Keep current docs in `docs/` while the repo remains this small. Use
`docs/history/` for completed or superseded provenance. Add no further taxonomy
until at least two durable documents share another stable lifecycle role and
owner.
