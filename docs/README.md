# OPL Flow Documentation

This index owns navigation and document maintenance. Contracts, source,
tests, component owners, and fresh readback establish executable behavior;
documentation explains those authorities.

## Reading Map

| Document | Single responsibility |
| --- | --- |
| [README](../README.md) / [中文](../README.zh-CN.md) | Paired product introduction and entry points |
| [Workflow architecture](reusable-workflow-architecture.md) | Flow, Ledger, private Instance, and external owner boundaries |
| [Capability governance](capability-governance.md) | Profile and capability policy composition through Framework and App |
| [Executor compatibility](compatibility.md) | Supported executor scope and neutral-contract boundary |
| [New machine setup](new-machine-codex-setup.md) | Install, initialize, update, and verify a machine |
| [Fleet architecture](opl-fleet-architecture.md) | Distributed execution and continuity contracts, including explicit design gaps |
| [Fleet observation](fleet-agent-cockpit-architecture.md) | Agent, Gateway, Cockpit, and provider protocol boundaries |
| [Browser routing](browser-tool-routing.md) | Select an operation tool from session and interaction requirements |

Operator procedures live in the relevant router references:

- [Flow actions](../skills/opl-flow/SKILL.md), including
  [Ledger onboarding](../skills/opl-flow/references/ledger-start.md),
  [Supervisor episodes](../skills/opl-flow/references/ledger-supervisor.md),
  [Fleet operations](../skills/opl-flow/references/fleet/guide.md), and
  [Package release](../skills/opl-flow/references/package-release.md).
- [Software development](../skills/software-development/SKILL.md), including
  the reusable [documentation governance method](../skills/software-development/references/docs/governance.md).
- [Task coordination](../skills/manage-codex-tasks/SKILL.md), including
  [owner migration](../skills/manage-codex-tasks/references/migrate-owner.md).

Router references own their methods, not consumer repository facts.
Profile text is authored in `profile/modules/01-user-preferences.md` and
projected into `templates/AGENTS.md`; edit the source and matching projection
together. `THIRD_PARTY_NOTICES.md` owns upstream provenance and license notices.

## Maintenance

For each document change, identify its reader question and existing subject
owner. Update that owner in place; other documents link to it rather than copy
its procedure, current inventory, or status. Keep the README translations
equivalent.

When source, contracts, commands, or ownership change, reconcile the affected
claims in the same change. Clearly distinguish implemented behavior from an
unimplemented decision; remove completed phase lists and execution logs after
their durable constraints have reached the current owner.

Use Git history for superseded material. Keep a separate archived record only
when unique rationale or a no-resurrection boundary still helps future
decisions. It must identify its successor and must not appear as a current
runbook. Retiring a document includes repairing inbound links and executable
examples; deleting a module also retires its documentation and obsolete tests
after real consumers have moved.

New documents need a distinct durable subject. Reuse this index and existing
history rather than adding a parallel status ledger, coverage manifest, or
mandatory metadata template. Check links, assets, examples, and affected source
contracts; judge meaning from evidence, never keyword or heading tests.
