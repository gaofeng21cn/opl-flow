# Workflow Profile And Readback Slim Design

## Goal

Keep the user's bearer-token provider configuration, Ponytail default `lite`,
and intentional `agents.max_threads=100`. Adapt OPL Flow to GPT-5.6 by removing
duplicated runtime ceremony, delegating bounded independent work proactively,
and making readiness reflect the one profile Codex actually needs at runtime.

## Profile Boundary

- `AGENTS.md` is the only runtime profile.
- `TASTE.md` remains a human-maintained authoring source whose stable digest is
  compiled into AGENTS; sessions and subagents do not read it by default.
- Planner, Executor, Debugger, and Verifier prompts are explicit compatibility
  entrypoints, not a default runtime chain.
- Commentary is event-driven rather than clock-driven.
- Completion evidence must be fresh and appropriate to the claim. Executable or
  live evidence is mandatory for behavior, runtime, release, and currentness
  claims, not for every documentation or decision deliverable.

## Authority Boundary

- Executor may inspect Git state but must not absorb unrelated changes, commit,
  or push unless the task explicitly authorizes that outcome.
- A real owner, semantic, permission, or authority decision remains a valid
  gate.
- AGENTS selects risk-appropriate evidence without a separate prose-router skill.
- `verification-before-completion` runs only for root terminal claims and high-risk runtime/release/owner claims.
- `codex-ops-kit` owns Git lane lifecycle and GitHub release evidence.
- `evidence-bound-closeout` owns generated artifacts, source binding, route
  authority, and public-surface drift, not Git lane lifecycle.

## Capability Adapters

- Ponytail remains enabled with default `lite`.
- Its automatic Codex rules are a 5-10 line delta injected once at root startup;
  resume, compact, and subagent hooks do not repeat it.
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
- Profile receipts and semantic-merge gates bind only `AGENTS.md`. TASTE and the
  four compatibility prompts remain installable and diagnosable but non-blocking.
- Profile verification uses a receipt to distinguish current, local overlay,
  unapproved local drift, and source drift. A local overlay is ready only when
  an explicit semantic-merge apply records the exact source and target hashes.
- Existing-profile installation is non-terminal until a reviewed packet output
  is applied through `--apply-merge-packet`; pending merge returns nonzero.
- Merge packets bind both the candidate source hashes and the existing target
  hashes. Apply fails closed if either side changes after packet creation.
- The bundled `codex-ops-kit` mechanical guardrail is included in install drift checks.

## Local Migration

- Update the repo-native modules and rendered templates first.
- Preserve the workstation's newer RTK rules in the source module.
- Sync the resulting AGENTS, optional support surfaces, bundled guardrails, and plugin payload to
  the local Codex surfaces.
- Remove the redundant `goals=true` pin; preserve the intentional
  `agents.max_threads=100`, `agents.max_depth=1`, and all unrelated live configuration.

## Verification

1. Focused unit tests cover marketplace identity, plugin installed/enabled
   readback, strict readiness, profile receipts, and both guardrail trees.
2. `python3 scripts/profile_compose.py check` verifies the rendered profile.
3. `python3 scripts/verify.py` verifies the full repository contract.
4. A real local install is followed by `codex plugin list --available --json`
   and `check_companion_skills.py --strict` readback.
5. A fresh root task forward-tests the thin profile; Ponytail review remains
   explicit rather than a mandatory closeout pass.
