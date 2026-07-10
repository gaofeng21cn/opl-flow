---
name: codex-ops-kit
description: "Deterministic, fail-closed evidence for high-risk Git lane lifecycle events and public GitHub release/install claims. Use before starting, resuming, delegating, absorbing, merging, deleting, or closing a worktree/subagent branch lane, or when verifying that published release URLs and install commands match live GitHub release assets. Do not use for ordinary edits, generic subagent coordination, retrospection/session audits, broad scans, cache freshness, runtime currentness, artifact QA, or phase tracking."
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
