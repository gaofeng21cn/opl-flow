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
| Owner source | `source_ahead_of_release` | `git log v0.1.22..main`; `profile/modules/01-user-preferences.md`; `templates/AGENTS.md`; `templates/TASTE.md`; `tests/test_profile_compose.py` | Current `main` adds parallel-progress and isolated-worktree preferences after the latest release. Repository source and tests do not prove publication or installation. |
| Owner release | `0.1.22` | tag `v0.1.22` at `0e6be1220cddeed791e8e09b0170024d95e06f9f`; `.codex-plugin/plugin.json`; `contracts/workflow-policy.json` | No later OPL Flow release currently carries the post-`0.1.22` profile source. |
| Framework catalog | `selected_0.1.22` | `opl packages list --json`; Framework `contracts/opl-framework/packages/opl-flow.json` and `contracts/opl-framework/bundled-full-runtime-package-catalog.json` | The catalog still selects owner source commit `0e6be122...`; it cannot be updated before a new owner release is fixed. |
| Installed projection | `installed_0.1.22` | `opl packages status --package-id opl-flow --json` | The installed lock reports `0.1.22`, managed policy `current`, and profile migration `semantic_merge_applied`. Those results apply only to the released `0.1.22` payload; `reload_required=true` also means active discovery needs a fresh process after the next update. |
| Fresh Codex discovery | `discovered_0.1.22` | A fresh `codex plugin list --json` process reports enabled `opl-flow@opl-agent-opl-flow-local` version `0.1.22`. | This proves active discovery of the released `0.1.22` payload in that fresh process only; it does not project the unreleased owner-source delta into the installed plugin. |

No additional OPL Flow profile, contract, or documentation behavior gap is selected
from the current portfolio audit. The remaining work is the release/currentness chain
below. Repository verification, catalog selection, installed package readback, and
fresh Codex discovery remain separate evidence layers.

## Current-State vs Ideal-State Gaps

### Functional / Structural Gaps

| Gap | Ideal state | Current state | Required change | Owner surface |
| --- | --- | --- | --- | --- |
| `post-0.1.22-owner-release` | The selected OPL Flow release contains the current minimal profile source. | `main` contains an unreleased profile-policy delta while both version surfaces and the latest tag remain `0.1.22`. | Cut the next OPL Flow release from current owner source, update both version surfaces together, run the full repository gate, and read back the pushed tag and source bytes. | `opl-flow` |
| `framework-catalog-currentness` | Framework stable catalog and payload manifests select the new immutable owner release. | Framework selects `0.1.22` and owner commit `0e6be122...`. | After the owner release exists, update the Framework package manifest, payload manifest, catalog, release cohort inputs, hashes, and release-set evidence through Framework-owned tooling. | `one-person-lab` |

### Test / Evidence Gaps

| Gap | Existing state | Missing evidence | Required verification | Foldback target |
| --- | --- | --- | --- | --- |
| `installed-currentness` | Released `0.1.22` is installed and its managed policy readback is current. | No installed lock or payload readback can yet prove the unreleased source. | Run the ordinary Framework package update after catalog publication, then re-read package list, lock, payload digest, managed-Skill validation, resolved entrypoint authority, and profile migration. | This document |
| `post-release-fresh-codex-discovery` | A fresh process discovers enabled OPL Flow `0.1.22`. | Discovery of the future owner release after the package update and required restart. | After catalog publication and package update, restart Codex when requested and require the fresh discovery version to equal the new installed lock. | This document |

## Next-Round Agent Prompt

Objective:

- Publish the current post-`0.1.22` OPL Flow profile source through its owner release,
  propagate that immutable release through the OPL Framework stable package catalog,
  update this machine through the ordinary package transaction, and close installed
  currentness plus fresh Codex discovery without creating a second lifecycle owner.

Write scope:

- OPL Flow: `.codex-plugin/plugin.json`, `contracts/workflow-policy.json`, and only
  release metadata or tests required by the repository's release convention.
- OPL Framework: `contracts/opl-framework/packages/opl-flow.json`, the new immutable
  `contracts/opl-framework/packages/payloads/opl-flow-<version>.json`, bundled catalog,
  release cohort/manifest inputs, and directly affected package-distribution tests.
- `docs/status.md` only for final current-state and gap foldback.
- Local installed state only through `opl packages update opl-flow` and the required
  fresh-process discovery readback after that transaction.

Non-goals:

- Do not add an App-specific OPL Flow updater, dependency list, profile store, or
  readiness checker.
- Do not use `scripts/install_local_plugin.py` as package or installed-currentness
  authority, and do not directly overwrite the user's `~/.codex/AGENTS.md`.
- Do not infer active discovery from cache bytes, source tests, a tag, catalog output,
  or installed lock alone.
- Do not claim App, Framework runtime, domain, release-set, owner acceptance, or
  production readiness from this package closeout.

Live truth inputs:

- OPL Flow `AGENTS.md`, `README.md`, `docs/README.md`, this document, and
  `docs/compatibility.md`.
- OPL Flow manifest, workflow policy, profile/templates, Skill, tests, current tags,
  `main`, and `origin/main`.
- Framework package manifest, payload manifest, bundled catalog, release cohort,
  release-set tooling, package-distribution tests, `main`, and `origin/main`.
- `opl packages list --json`, `opl packages status --package-id opl-flow --json`, and
  a fresh `codex plugin list --json` process.

Required actions:

1. Recheck both repositories' canonical `main`, remote relation, worktrees, and owner
   write sets; stop on overlapping release or package-catalog writes.
2. Choose the next version from the live tag set, update the two OPL Flow version
   surfaces together, run full OPL Flow verification, then commit, tag, push, and read
   back the exact owner release commit and raw release bytes.
3. Generate or update the Framework package and payload manifests from that immutable
   owner release; do not reconstruct payload identity from a local cache or checkout.
4. Run the Framework package-distribution and release-set gates, absorb and push the
   Framework change, then read back the stable catalog's selected version, owner commit,
   manifest digest, and payload digest.
5. Run `opl packages update opl-flow`, inspect the resulting lock and physical payload,
   and restart Codex when the transaction reports reload required.
6. Start a fresh Codex process after the package transaction and verify that the
   discovered OPL Flow plugin version equals the installed package lock.
7. Rewrite this document to remove closed gaps, retain any typed blocker, and leave the
   next prompt naming only remaining work.

Verification commands:

```bash
# OPL Flow checkout
scripts/verify.sh full
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
opl-doc-doctor doctor . --format json
git diff --check

# OPL Framework checkout
bun test tests/src/cli/cases/package-distribution-cases/manifest.test.ts
bun test tests/src/cli/cases/package-distribution-cases/archive-and-first-party.test.ts
bun test tests/src/cli/cases/packages-cases/guards-and-identities.test.ts
node scripts/package-release-discipline.mjs
git diff --check

# Installed and discovery readback
opl packages list --json
opl packages status --package-id opl-flow --json
codex plugin list --json
```

Completion / foldback gate:

- OPL Flow release tag, remote commit, manifest versions, and raw release bytes agree.
- Framework stable catalog, immutable payload manifest, owner commit, and digests agree.
- Installed package lock and materialized payload select that same release; managed
  policy and entrypoint authority are current.
- A fresh Codex process discovers that same OPL Flow version.
- Closed rows are removed from this document and any remaining blocker names its owner,
  evidence, legal re-entry route, and stop condition.
- Both repositories are verified on their final absorbed `main`; task worktrees and
  temporary branches are cleaned only after absorption/currentness readback.

## Coverage And Carry-Forward

- Reviewed: `README.md` and every tracked `docs/**/*.md` file, including all history
  records, plus the profile, manifest, workflow policy, relevant tests, Framework
  package catalog, installed package readback, and fresh discovery command.
- Edited in this tranche: this document, `docs/README.md`, and
  `docs/new-machine-codex-setup.md`.
- Archived, tombstoned, or deleted: none. Existing `docs/history/` records already have
  a provenance-only role and do not compete with current truth.
- Unreviewed README/docs files in this repository: none.
- Unresolved stale/retire candidates: none selected.
- Next write scope: the release/currentness sequence in the prompt above.
