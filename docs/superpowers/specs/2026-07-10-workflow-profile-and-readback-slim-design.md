# Workflow Profile And Readback Slim Design

## Goal

Keep the user's intentional local choices unchanged: bearer-token provider
configuration, Ponytail default `lite`, and unrestricted `agents.max_threads`.
Simplify OPL Flow by removing duplicated workflow ceremony, tightening authority
boundaries, and making plugin/profile readiness reflect Codex live readback.

## Profile Boundary

- `TASTE.md` remains the collaboration-principles source of truth.
- `AGENTS.md` owns durable routing and hard boundaries, not repeated procedures.
- Planner, Executor, Debugger, and Verifier are lenses used by one agent in the
  same task, not handoff states that stop delivery.
- Decision-lens prompts retain only their OPL-specific delta. Reusable algorithms stay in
  the corresponding skills.
- Completion evidence must be fresh and appropriate to the claim. Executable or
  live evidence is mandatory for behavior, runtime, release, and currentness
  claims, not for every documentation or decision deliverable.

## Authority Boundary

- Executor may inspect Git state but must not absorb unrelated changes, commit,
  or push unless the task explicitly authorizes that outcome.
- A real owner, semantic, permission, or authority decision remains a valid
  gate.
- `risk-based-development-flow` selects evidence type and budget.
- `verification-before-completion` runs and reads fresh completion evidence.
- `codex-ops-kit` owns Git lane lifecycle and GitHub release evidence.
- `evidence-bound-closeout` owns generated artifacts, source binding, route
  authority, and public-surface drift, not Git lane lifecycle.

## Capability Adapters

- Ponytail remains enabled with default `lite`.
- OPL Flow does not claim that task classification mechanically switches the
  Ponytail plugin mode. `ponytail-audit` handles broad candidate discovery and
  `ponytail-review` handles concrete diffs.
- Ponytail governs implementation complexity only and cannot weaken scope,
  evidence, authority, or completion requirements.
- Superpowers lite excludes upstream `brainstorming`; planning is loaded only
  for genuinely unclear requirements or material design choices.
- `using-git-worktrees` is routed only for explicit isolation or parallel-lane
  needs. It must not create commits, install dependencies, or run broad setup
  merely because an implementation plan exists.

## Installation And Readback

- The personal marketplace uses a unique name instead of colliding with
  `med-autoscience-local`.
- Installation is not complete after copying files. The installer must invoke
  Codex plugin installation and bind success to the exact plugin ID,
  marketplace, version, installed state, and enabled state.
- The repository marketplace manifest is the single source of truth; the
  installer validates and consumes it instead of regenerating a second copy.
- Same-version installation still refreshes the Codex cache, and verification
  compares the staged plugin with the actual cache payload.
- Source repositories and staged `~/plugins` copies are candidates, not runtime
  readiness evidence.
- Strict companion checks fail unless the profile and OPL Flow-native
  guardrails are runtime-discoverable.
- Profile verification uses a receipt to distinguish current, local overlay,
  and source drift instead of treating every byte difference as stale.
- Both bundled guardrails, `risk-based-development-flow` and `codex-ops-kit`,
  are included in install drift checks.

## Local Migration

- Update the repo-native modules and rendered templates first.
- Preserve the workstation's newer RTK rules in the source module.
- Sync the resulting AGENTS, prompts, bundled guardrails, and plugin payload to
  the local Codex surfaces.
- Remove only project-trust entries whose paths no longer exist. Keep all live
  entries and the user's `agents.max_threads` value.

## Verification

1. Focused unit tests cover marketplace identity, plugin installed/enabled
   readback, strict readiness, profile receipts, and both guardrail trees.
2. `python3 scripts/profile_compose.py check` verifies the rendered profile.
3. `python3 scripts/verify.py` verifies the full repository contract.
4. A real local install is followed by `codex plugin list --available --json`
   and `check_companion_skills.py --strict` readback.
5. The final diff receives an independent correctness review and a
   `ponytail-review` complexity pass.
