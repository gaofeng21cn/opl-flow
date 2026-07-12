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
| [Skill frontmatter trigger audit](./audits/2026-07-12-skill-frontmatter-trigger-audit.md) | Local skill overlap and mis-trigger assessment | Baseline and implementation record |

## Growth Rule

Keep new docs in `docs/` while the repo remains this small. Add subdirectories
only when there are at least two durable documents with the same lifecycle role
and a stable owner.
