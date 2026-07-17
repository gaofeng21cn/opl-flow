# OPL Flow Docs

Owner: `gaofeng`
Purpose: `docs_index`
State: `active_index`
Machine boundary: Human-readable navigation. Executable truth remains in the
plugin manifest, installer scripts, bundled skills, tests, and repo-native
verification commands.

This support repo keeps a deliberately small docs surface. It does not need the
full OPL/MAS/MAG/RCA taxonomy unless durable material appears with a clear
owner, purpose, state, and machine boundary.

## Current Docs

| Doc | Role | Boundary |
| --- | --- | --- |
| [Active truth and current gaps](./status.md) | Single owner for current state, open gaps, next-round Agent prompt, and coverage carry-forward | Human-readable planning; release, install, and discovery truth comes from owner/package/readback surfaces |
| [Compatibility and positioning](./compatibility.md) | OPL Flow model-native boundary and optional specialist skills | Human-readable positioning; not OPL App/runtime/domain readiness |
| [New machine Codex setup](./new-machine-codex-setup.md) | Bootstrap runbook for installing the Codex workflow profile | Human-readable runbook; real install truth comes from installer and verification output |

## Canonical Role Coverage

The repository deliberately maps canonical governance roles to existing owners instead
of creating parallel documents with duplicate prose.

| Canonical role | Owner in this repository | Why no additional document is needed |
| --- | --- | --- |
| Project positioning (`docs/project.md`) | Root `README.md`, especially `Public Role Boundary` | The repository has one small product/profile scope and no separate project portfolio. |
| Active status and plan (`docs/status.md`) | [Active truth and current gaps](./status.md) | This is the single current-state, gap, next-prompt, and coverage owner. |
| Architecture boundary (`docs/architecture.md`) | Root `README.md` for the source/install flow; [compatibility.md](./compatibility.md) for the owner map; manifest, policy, profile source, and tests for executable truth | A second architecture narrative would repeat the existing source and ownership boundary. |
| Hard invariants (`docs/invariants.md`) | `skills/opl-flow/SKILL.md`, `contracts/workflow-policy.json`, and repository tests; [compatibility.md](./compatibility.md) is the human-readable pointer | Machine checks already own the package lifecycle, no-second-owner, and evidence-layer constraints. |
| Decisions (`docs/decisions.md`) | [History and provenance](./history/README.md) plus Git history | There is no unsettled cross-cutting decision that requires a separate active ledger. |

## History

[History and provenance](./history/README.md) contains dated baselines, completed
audits, and implemented designs. These records explain prior decisions but do not
define current package, installation, discovery, or readiness truth.

## Growth Rule

Keep current docs in `docs/` while the repo remains this small. Use
`docs/history/` for completed or superseded provenance. Add no further taxonomy
until at least two durable documents share another stable lifecycle role and
owner.
