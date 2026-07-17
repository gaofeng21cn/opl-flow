# GPT-5.6 Workflow Baseline And Assessment

Owner: `gaofeng`
Purpose: `gpt56_workflow_baseline_provenance`
State: `historical_provenance`
Machine boundary: Frozen human-readable baseline and decision provenance. Current
OPL Flow behavior remains in `README.md`, `contracts/workflow-policy.json`, the
plugin manifest, profile and Skill sources, tests, and fresh repo-native
verification output.
Date: 2026-07-12
Scope: local Codex workflow profile, design/development workflow skills, OPL Flow, and OPL App Superpowers packaging.

## Frozen Baseline

The pre-change state is recoverable from:

- OPL Flow Git baseline: commit `a9d1f8a` and bundle `/Users/gaofeng/.codex/backups/opl-flow-gpt56-baseline-20260712T074518/opl-flow-main.bundle`.
- Local workflow profile archive: `/Users/gaofeng/.codex/backups/opl-flow-gpt56-baseline-20260712T074518/local-workflow-profile.tar.gz`.
- Archive SHA-256: `0ad02422ce61c7938d21ae9a2e49fc6a94379c7a9ca349bc97372522eae8a308`.
- Bundle SHA-256: `42cb7441fb124e015da546e405dc7f73a036fc0f4d9c547053f557164e5a11c1`.
- Ponytail 4.8.4 payload archive: `/Users/gaofeng/.codex/backups/opl-flow-gpt56-baseline-20260712T074518/ponytail-4.8.4-plugin.tar.gz`, SHA-256 `6f0d1d9cc5fb5c1ab18bdee729a07bca8ff0ddb59ba82513c555b822fee23e0c`.
- OPL App baseline: `41659008e9ebf115f7f48707469342c7a8175728`.
- OPL Framework baseline: `5701930041fb5d2c4505006ebaafccb21e52301b`.

Before the final package and multi-machine migration, a second restorable snapshot was frozen at `/Users/gaofeng/.codex/backups/opl-flow-gpt56-final-20260714T145843`. It contains the then-current Codex config/profile, OPL package receipts, relevant plugin payloads, the installed machine-sync skill, and Git bundles for OPL Flow and its private source. The bundle SHA-256 values are `aa5e236c422d9a4641d3e8abe47db30e52c08be3728a157cfc41d639736a1755` for OPL Flow and `7cf9fd946fd091df4106e153113bbb7e4a7d28a2947f331ec9452876172413c0` for the private skill source.

Restore the repository with the recorded commit or bundle. Restore local profile files only after stopping Codex and reviewing archive paths; the archive intentionally contains workflow text/configuration, not credentials.

## Acceptance Boundary

- Keep user language/style preferences, ownership boundaries, protection of user changes, and claim-appropriate evidence.
- Keep deterministic Git/release audits and official marker blocks.
- Remove default methodology bootstraps, role/stage switching, broad automatic skill triggers, startup coding personas, and duplicate readiness concepts.
- OPL App must stop packaging or auto-installing Superpowers. A later explicit user decision supersedes the original preserve-only boundary: when the user actively installs, updates, or optimizes OPL Flow, declared conflicts are backed up and removed from active discovery/configuration unless the user supplies a keep override.

## Detailed Assessment

| Surface | Baseline behavior | Interference | Decision |
| --- | --- | --- | --- |
| User `AGENTS.md` | 113 lines plus CodeGraph marker; task tiers, default subagents, completion and root-cause templates | High: always loaded and frames ordinary work before task reasoning | Simplify to model-native default; retain only durable boundaries |
| Direct/Inline/Durable tiers | Every task classified into a workflow tier | Medium: GPT-5.6 can choose the necessary depth directly | Remove taxonomy |
| Planner/executor/debugger/verifier prompts | Four install-managed compatibility prompts | Low runtime, medium maintenance: duplicate roles and merge/readback code | Remove from package, installer, manifest, tests, and local prompt directory |
| Default subagent policy | Proactive delegation for bounded work | High: coordination cost on tasks GPT-5.6 can solve directly | Make explicit/material-benefit only |
| Completion audit | Root terminal audit for target-state work | Low when narrow; high if applied to ordinary changes | Keep only for explicit full-target requests |
| Verification skill | Triggered for every changed-work terminal claim | High: duplicates ordinary focused checks | Narrow to explicit or high-risk runtime/release/owner claims |
| Systematic debugging | Repeated/flaky/cross-component/unclear failures only | Low | Keep narrow |
| TDD skill | Explicit TDD, durable contract, permission or irreversible writes | Low | Keep narrow |
| Superpowers bootstrap | Upstream `using-superpowers` disabled; no hooks; full/expanded skills not discovered | Low current runtime, unnecessary packaging/readback ownership | Keep user-owned optional install; remove OPL packaging and OPL Flow readiness coupling |
| Superpowers-lite | Explicit umbrella entry | Low, but body still routed verification too broadly | Keep explicit; narrow verification route |
| Ponytail plugin hook | Enabled plugin, root startup injection and per-prompt mode tracker | High: persistent coding persona | Disable/remove automatic plugin activation |
| Ponytail main skill | Advertised `ANY coding task` and `ACTIVE EVERY RESPONSE` | Critical: automatic full persona can load despite lite config | Remove from ordinary discovery; explicit audit/review only |
| Ponytail audit/review | One-shot over-engineering reports | Low when explicit | Retain only as explicit optional actions |
| `ui-ux-pro-max` | Broad UI task trigger and mandatory process language | High for ordinary UI implementation | Narrow to explicit design-system/complex UX work |
| `prototype` | Explicit throwaway prototype work | Low | Keep |
| `grill-with-docs` | Explicit plan challenge and documentation update | Low | Keep |
| `improve-codebase-architecture` | Explicit architecture-improvement request | Low | Keep |
| `zoom-out` | Explicit perspective command, model invocation disabled | None by default | Keep |
| DDIA/legacy/release-it book skills | Narrow domain triggers for distributed state, legacy seams, production failure semantics | Low | Keep |
| `codex-ops-kit` | Deterministic Git lane/public release evidence | Low reasoning interference; high safety value | Keep |
| `evidence-bound-closeout` | Exact-byte generated artifact binding | Low, narrow | Keep |
| RTK preference | Compact shell output | Medium tool coupling, not a methodology | Keep; native command remains allowed when fidelity matters |
| CodeGraph marker | Large global structural-search instruction block | Medium and globally visible | Preserve official marker; project-local scoping remains future tool-owner work |

## Target State

1. GPT-5.6 handles ordinary design, implementation, diagnosis, and verification directly.
2. No startup or per-prompt coding persona is active.
3. Specialist skills load only by explicit request or a genuinely narrow domain/high-risk trigger.
4. OPL Flow verification covers its profile and plugin payload only; optional utilities are not readiness signals.
5. OPL App Full contains no Superpowers payload and does not create or overwrite a Superpowers link during first configuration.

## Final Minimal-Profile Decision

After review, the retained user-level profile is narrower than the initial acceptance boundary above. Guardrails, ops/authority routing, completion ceremonies, debugging/TDD/verification routing, subagent policy, and Ponytail/Superpowers language were removed from the always-loaded profile. The remaining runtime content is limited to communication preferences, reading effective project context before edits, repo-local authority, RTK preference, and CodeGraph bootstrap.

The final rendered profile is a nine-line, 725-byte flat list with no Markdown section headings. Its source is one module; the previous one-rule-per-section module split was removed.

`codex-ops-kit` remains plugin-accessible for an explicit narrow audit, but it is no longer routed by the global `AGENTS.md` or treated as an OPL Flow readiness dependency. The follow-on skill audit narrowed broad browser, Office, extraction, and method-skill frontmatters at their canonical sources.

## CodeGraph Bootstrap Result

- Activity boundary: 45 Git checkouts under `~/workspace` and non-temporary `~/Documents` development locations.
- Excluded: archives, worktrees, migration backups, temporary directories, dependency trees, date-based Codex intake workspaces, and generated runtime/test-state checkouts.
- Result: 45/45 contain `.codegraph/`, 45/45 ignore it through Git, and 45/45 root `AGENTS.md` files contain exactly one concise CodeGraph marker block.
- Global ignore: `~/.gitignore_global` includes `.codegraph/`.
- The global profile contains only the bootstrap rule. Detailed CodeGraph tool routing stays repo-local.
