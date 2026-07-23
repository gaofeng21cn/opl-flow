# OPL Flow Active Truth

Owner: `gaofeng`
Purpose: `active_truth_plan`
State: `active_plan`
Machine boundary: Human-readable current-state and next-round planning owner. Package,
profile, install, and discovery truth remains in the plugin manifest, workflow policy,
profile sources, tests, Framework package readback, and fresh Codex discovery output.

## Ideal-State Reference

- `README.md` owns the public product and package boundary.
- `skills/opl-flow/SKILL.md` owns the operator route and currentness-layer model; `skills/coordinate-concurrent-tasks/SKILL.md` owns bounded multi-task coordination and the user-approval archive boundary.
- `contracts/workflow-policy.json` owns the open `(kind, id)` capability graph; `docs/capability-governance.md` explains the Flow/Framework/App authority split.
- `.codex-plugin/plugin.json`, `contracts/workflow-policy.json`, `profile/`,
  `templates/`, and tests own executable repository behavior.
- The target is a minimal model-native Codex preference profile distributed through
  the generic OPL Framework package lifecycle, with no second installer, updater,
  readiness checker, or App-specific policy owner.

This document is the single Active Truth owner for current state, open gaps, and the
next-round Agent prompt. It does not duplicate the durable product explanation in
`README.md` or the positioning detail in `docs/compatibility.md`.

## Current State Summary

| Area | Durable current fact | Authority / readback |
| --- | --- | --- |
| Owner source | The plugin manifest and workflow policy carry one package identity and version; the profile manifest renders one model-native preference module into `templates/AGENTS.md`. | `.codex-plugin/plugin.json`, `contracts/workflow-policy.json`, `profile/manifest.json`, `profile/modules/01-user-preferences.md`, and `scripts/profile_compose.py` |
| Retired workflow surfaces | The workflow policy retires legacy role prompts, the repository-local marketplace identity, and the former process-skill defaults through Framework-owned migration with backup and rollback. No Codex Ops Kit payload, dependency, or active verification lane remains in this repository. | `contracts/workflow-policy.json#retires` and `#migration_policy`; repo source and tests guard against resurrection. |
| Package lifecycle | OPL Framework is the sole normal install, update, optimize, rollback, and currentness owner. The repository installer is development-only and does not establish package currentness. | `opl packages list --json` and `opl packages status --package-id opl-flow --json` must be read live. |
| Effective discovery | Owner source/tag, Framework catalog, installed lock/payload, and Codex discovery are four independent currentness layers. This document does not freeze their versions, refs, digests, or ready state. | Fresh remote tag/ref readback, Framework package JSON, and `codex plugin list --json` from the target process. |
| Authority boundary | OPL Flow owns the minimal preference profile, its two bounded workflow skills, and the managed capability graph. Framework owns lifecycle execution and App owns GUI/release projections. The coordination skill does not own App, Framework, release, machine, project, domain readiness, or actual thread archival. | `README.md`, `docs/capability-governance.md`, `skills/opl-flow/SKILL.md`, and `skills/coordinate-concurrent-tasks/SKILL.md` |

## Current-State vs Ideal-State Gaps

No confirmed repository functional or structural gap is open in the current source
snapshot. Package selection, installed projection, and fresh discovery are live
currentness questions, not durable closed rows. A future source release or target
machine audit must read all four currentness layers again and preserve any mismatch
as an owner-routed blocker rather than updating this document with another frozen
closeout packet.

## Next-Round Agent Prompt

Goal: audit the next evidence-backed OPL Flow source or currentness gap without
creating a second lifecycle owner or freezing one machine's proof into active docs.

- Write scope: `.codex-plugin/`, `contracts/`, `profile/`, `templates/`, `skills/`,
  tests, scripts, README, and this status owner only when fresh evidence requires it.
- Non-goals: do not add a package installer/updater, readiness checker, Git lane,
  release auditor, private overlay, machine inventory, SSH orchestration, or App,
  Framework, project, release, and domain truth.
- Live truth inputs: exact owner ref/tag, plugin manifest, workflow policy, profile
  source and rendered bytes, repo tests, Framework package catalog/status JSON, and
  Codex discovery output from the target process.
- Required actions: check branch/remote/dirty/worktrees and owner write sets; classify
  source, catalog, installed, and discovery currentness separately; select only a
  narrow owner-backed gap; route package lifecycle changes through `opl packages`;
  keep missing evidence or mismatches fail-closed.
- Verification commands: use the commands below, narrowed to the changed authority
  surface and expanded to full verification before release.
- Completion gate: verified source bytes are on remote `main`; any required package
  or discovery effect has its own fresh readback; no ready/current claim is inferred
  from docs, tests, a clean queue, or a pushed commit.
- Foldback target: durable behavior goes to its manifest/policy/source owner and
  `README.md`; only current gaps and the next legal entry remain in this document;
  one-run refs, digests, receipts, and closeout detail stay in receipts, history, or
  Git history.

## Verification Commands

```bash
# OPL Flow checkout
scripts/verify.sh full
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py" .
python3 /Users/gaofeng/workspace/opl-doc/scripts/opl_doc_doctor.py doctor . --format json
git diff --check

# Framework checkout, only when package catalog or lifecycle is in scope
bun test tests/src/cli/cases/package-distribution-cases/manifest.test.ts
bun test tests/src/cli/cases/package-distribution-cases/archive-and-first-party.test.ts
bun test tests/src/cli/cases/packages-cases/guards-and-identities.test.ts
node scripts/package-release-discipline.mjs
git diff --check

# Installed and discovery readback, only for the target installation/process
opl packages list --json
opl packages status --package-id opl-flow --json
opl update check --json
codex plugin list --json
```

## Completion / Foldback Gate

- Changed source and rendered profile bytes agree with their machine owners and tests.
- When package/install/discovery currentness is in scope, owner ref, Framework catalog,
  installed lock/payload, and target-process discovery are each read back independently.
- Any remaining blocker names its owner, evidence, legal re-entry route, and stop
  condition.
- Changed repositories are verified on final absorbed `main`; task worktrees and
  temporary branches are cleaned only after remote readback.

## Coverage And Carry-Forward

- Current owners covered: product/package boundary, profile source/rendering, capability
  graph, plugin/skill carrier, open composition, repository verification,
  Framework lifecycle route, App projection boundary, and target-process discovery route.
- Retired surface provenance belongs in `docs/history/**`, policy retirement rows, and
  Git history; it does not return to this Active Truth owner as a current proof table.
- No additional stale or retirement candidate is established by the current source
  snapshot. Reopen only from fresh owner/source/caller/readback evidence.
