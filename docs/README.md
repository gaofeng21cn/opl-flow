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
| [Compatibility and positioning](./compatibility.md) | OPL Flow model-native boundary and optional specialist skills | Human-readable positioning; not OPL App/runtime/domain readiness |
| [New machine Codex setup](./new-machine-codex-setup.md) | Bootstrap runbook for installing the Codex workflow profile | Human-readable runbook; real install truth comes from installer and verification output |

## History

[History and provenance](./history/README.md) contains dated baselines, completed
audits, and implemented designs. These records explain prior decisions but do not
define current package, installation, discovery, or readiness truth.

## Growth Rule

Keep current docs in `docs/` while the repo remains this small. Use
`docs/history/` for completed or superseded provenance. Add no further taxonomy
until at least two durable documents share another stable lifecycle role and
owner.
