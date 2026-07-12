---
name: codex-ops-kit
description: "Run deterministic Git lane or public GitHub release audits with the bundled scripts. Use only when the user explicitly asks for codex-ops-kit, a lane lifecycle audit, an absorption audit, or a public release URL/asset/install-command audit."
---

# Codex Ops Kit

Use this skill only where deterministic Git or GitHub readback is safer than prose reasoning.

## Boundary

- Keep general workflow, authority, root-cause, verification, and completion policy in the active profile and repo instructions.
- Keep project facts in repo-native contracts, runtime/readback surfaces, owner receipts, and existing ledgers.
- Do not create a global baton, project profile, cache-freshness classifier, or second source of truth.
- Treat historical `~/.codex/state/codex-ops-kit/` files as history, not current lane authority.
- Route generated-artifact and public-surface evidence binding to `evidence-bound-closeout` when available.

## Route

| Event | Read | Run first |
| --- | --- | --- |
| Git worktree/subagent branch start, resume, delegation, absorption, merge, delete, or closeout | `references/lane-closeout.md` | `scripts/codex_ops_gate.py status --repo . --target-ref <target>` |
| Public GitHub release URL, asset, or install-command claim | `references/release-currentness.md` | `scripts/release_url_audit.py --repo .` |

Resolve `scripts/...` relative to this skill directory. Read only the selected reference, treat a nonzero tool result as blocked, and do not generalize its evidence beyond the exact Git or GitHub surface checked.
