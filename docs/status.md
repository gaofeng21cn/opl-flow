# OPL Flow Active Truth

Owner: `gaofeng`
Purpose: `active_truth_plan`
State: `active_plan`
Machine boundary: Human-readable current-state and next-round planning owner. Package,
profile, install, and discovery truth remains in the plugin manifest, workflow policy,
profile sources, tests, Framework package readback, and fresh Codex discovery output.

## Ideal-State Reference

- `README.md` owns the public product and package boundary.
- `skills/opl-flow/SKILL.md` owns the operator route and currentness-layer model.
- `.codex-plugin/plugin.json`, `contracts/workflow-policy.json`, `profile/`,
  `templates/`, and tests own executable repository behavior.
- The target is a minimal model-native Codex preference profile distributed through
  the generic OPL Framework package lifecycle, with no second installer, updater,
  readiness checker, or App-specific policy owner.

This document is the single Active Truth owner for current state, open gaps, and the
next-round Agent prompt. It does not duplicate the durable product explanation in
`README.md` or the positioning detail in `docs/compatibility.md`.

## Current State Summary

| Area | Current state | Live evidence | Boundary |
| --- | --- | --- | --- |
| Owner source | `released_0.1.23` | tag `v0.1.23`; commit `a8cf79ee7b751ea9f6d704a703019955379a1b43`; AGENTS template SHA-256 `bf83abd15102e88175a0139506778db176bbec12af260c202a09d6783841508d` | The immutable owner release contains the parallel-worktree/SSOT profile and retires the former Codex Ops Kit payload, dependency, verification lane, and active documentation surface. |
| Framework catalog | `selected_0.1.23` | stable Release Set `26.7.18`; package manifest SHA-256 `549b676dcb36d58bb618a1534e2aa171b22b86a22043b15f698efba3c8ed3b18`; package artifact digest `sha256:f973b4b784817d926ca9d15210ed4d417f432d949898e8868aa3066f1e34e4c5` | Framework selects the immutable owner commit and remains the only normal install/update owner. |
| Installed projection | `current_0.1.23` | authority installation reports package lock `0.1.23`, matching profile and managed-policy hashes, and ten managed Skills with no failed dependency; two independent stable consumer readbacks report the same owner commit and artifact digest | Private machine inventory, SSH orchestration, and personal overlays are outside this public repository. A developer-checkout projection may deliberately expose `0.1.23-dev-*` while preserving the same owner commit. |
| Fresh Codex discovery | `discovered_0.1.23` | fresh stable consumer processes report enabled `opl-flow` version `0.1.23`; the authority developer process reports the matching `0.1.23-dev-*` projection | Discovery proves only the process and projection queried; it does not replace catalog or installed-lock evidence. |
| Framework runtime | `channel_current` | two independent consumer readbacks report Release Set `26.7.18`, Framework source commit `0d1f90b8646cbc66953fada15cead239372ac476`, source archive SHA-256 `75fdec03c75c5d71d83c3eb0eb8392b7f62c06d929dc0e50770ebf07ec5e3038`, `channel_artifact_current=true`, and no update available | This confirms the downstream package carrier is current; it does not make OPL Flow an App or Framework lifecycle owner. |

No additional OPL Flow profile, contract, catalog, install, or discovery gap is
selected from the current portfolio audit. Owner release, Framework catalog,
installed package readback, and fresh Codex discovery remain separate evidence
layers even though they currently agree.

## Current-State vs Ideal-State Gaps

None selected as of the `0.1.23` / Release Set `26.7.18` closeout.

Future owner releases must reopen catalog, installed-projection, and fresh-discovery
currentness as separate rows until each layer is proven again.

## Next-Round Agent Prompt

No active implementation or release task is carried forward.

For the next owner release:

1. Recheck the owner tag and commit, Framework catalog selection, installed lock,
   payload digest, profile/policy currentness, and fresh Codex discovery separately.
2. Use only `opl packages install|update|optimize opl-flow` for normal lifecycle work.
3. Keep private overlays, machine targets, credentials, caches, and SSH orchestration
   outside this public repository.
4. Reopen this document only for a typed gap backed by fresh evidence.

## Verification Commands

```bash
# OPL Flow checkout
scripts/verify.sh full
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py" .
opl-doc-doctor doctor . --format json
git diff --check

# Framework checkout
bun test tests/src/cli/cases/package-distribution-cases/manifest.test.ts
bun test tests/src/cli/cases/package-distribution-cases/archive-and-first-party.test.ts
bun test tests/src/cli/cases/packages-cases/guards-and-identities.test.ts
node scripts/package-release-discipline.mjs
git diff --check

# Installed and discovery readback
opl packages list --json
opl packages status --package-id opl-flow --json
opl update check --json
codex plugin list --json
```

## Completion / Foldback Gate

- OPL Flow release tag, remote commit, manifest versions, and raw release bytes agree.
- Framework stable catalog, immutable payload manifest, owner commit, and digests agree.
- Installed package lock and materialized payload select that same release; managed
  policy and entrypoint authority are current.
- A fresh Codex process discovers the expected stable or developer projection.
- Any remaining blocker names its owner, evidence, legal re-entry route, and stop
  condition.
- Both repositories are verified on final absorbed `main`; task worktrees and
  temporary branches are cleaned only after absorption/currentness readback.

## Coverage And Carry-Forward

- Reviewed: owner release, profile/template hash, Framework package and payload
  manifests, stable Release Set evidence, installed package readback, Framework
  channel currentness, and fresh Codex discovery.
- Edited in this tranche: this document only.
- Archived, tombstoned, or deleted: none.
- Unresolved stale/retire candidates: none selected.
- Next write scope: none until a fresh typed gap is observed.
