---
name: software-development
description: "Use for non-trivial software work: implementation and delivery, code review, architecture or simplification, developer documentation, prototypes, CI or pull-request maintenance, production reliability, release and deployment, or explicitly requested Grok Build delegation. Excludes tiny edits, ordinary explanations, OPL Flow product operations, and Codex task management."
---

# Software Development

Route non-trivial software work to one focused guide. Keep ordinary reasoning,
small edits, and repository-local decisions model-native. Repository
instructions, contracts, source, callers, tests, and runtime readback remain
authoritative.

## Cross-router handoff

This router owns implementation, review, architecture, and delivery decisions.
The execution carrier is replaceable: a Worker may run in the current task or
through OPL Fleet while the Ledger objective and current owner remain stable.

- Use `$opl-flow fleet` when the slice needs fresh node admission, workspace
  continuity, protected capacity, or cross-machine continuation.
- Use `$manage-codex-tasks` when the work needs native task coordination,
  recovery, integration, or execution-owner migration.
- Return the checkpoint, result, or blocker to the current Ledger owner before
  starting another slice. Do not create a second task record to represent a
  retry or a machine change.

## Choose One Mode

Load only the reference named by the selected mode and any explicitly required
sub-guide.

| Mode | Use when | Load |
| --- | --- | --- |
| `delivery` | Implement, refactor, validate, or deliver a software change. | `references/delivery/guide.md` |
| `grok-build` | The user explicitly requests Grok Build implementation or recovery of an existing Grok session. | `references/grok-build/guide.md` |
| `review` | Review a PR, branch, commit range, or worktree without editing by default. | `references/review.md` |
| `architecture` | Map, improve, simplify, or pressure-test a codebase or design. | `references/architecture/guide.md` |
| `systems` | Distributed-data correctness or production failure semantics materially affect the change. | One file under `references/systems/` |
| `docs` | Govern developer documentation, decision records, sites, prose, or a bilingual pair. | `references/docs/governance.md`, then one focused docs reference |
| `github` | Patrol GitHub state or land an official pull-request stack. | One guide under `references/github/` |
| `prototype` | Build a disposable logic or UI experiment to answer a concrete question. | `references/prototype/guide.md` |
| `browser-evidence` | Record and verify a real browser interaction artifact. | `references/browser-evidence/guide.md` |

Within `delivery`, load `legacy-change.md`, `pre-push.md`, or
`production-change.md` only when that exact boundary is present. Within
`architecture`, load only the requested map, improvement, simplification,
grilling, or named lens reference.

## Boundaries

- Use `$manage-codex-tasks` when the work requires multiple Codex tasks,
  worktree integration, task recovery, or execution-owner transfer.
- Use `$opl-flow` for OPL Flow Profile, Package, Ledger, or Fleet operations.
- Use platform or domain Skills for their actual implementation domain; this
  router owns the development path, not every technology manual.
- Use `impeccable` for interface design, UX critique, accessibility review, or
  visual refinement when that work benefits the task. Preserve the product's
  existing design authority; use the platform/browser tools for rendered and
  interaction evidence.
- A release, deployment, migration, public write, or destructive mutation loads
  `references/delivery/production-change.md` before the first real mutation.
- Do not load neighboring guides pre-emptively or turn this router into a
  planner/executor role system.

## Finish

Verify in proportion to the changed behavior and report the real requested
terminal surface. A plan, test pass, local commit, task branch, or queued action
is evidence only for its own layer.

## Worker exchange

For a delegated or resumed slice, use the shared handoff and result contracts
in `contracts/worker-handoff.schema.json` and `contracts/worker-result.schema.json`
at the Package root. Validate them with `scripts/opl_workflow.py worker handoff`
or `worker result`. Pass the handoff to the native executor; managed Fleet
acquire/execute accepts `--handoff-json @file` and binds the same attempt.
Return evidence to the current Ledger owner for acceptance. Capacity receipts,
Worker completion, and worktree custody cannot change the objective's owner or
terminal status by themselves. Simple current-session work needs no extra file.
