# Codex Ops Kit Project Profiles

Profiles adapt the global kit to project-owned truth surfaces. They should not duplicate project truth.

## Minimal Profile

```json
{
  "ledger": "",
  "truth_surfaces": [
    "docs/status.md",
    "contracts/current-status.json"
  ],
  "current_truth_checks": [
    {
      "name": "repo status",
      "command": "git status --short"
    }
  ],
  "notes": "Leave ledger empty to use the user-level default."
}
```

## MAS/OPL Style

For repos with runtime status, attempt ledgers, owner receipts, controller decisions, generated read models, or typed blockers:

- Put those paths or commands in `truth_surfaces` and `current_truth_checks`.
- Set `ledger` only to an existing machine-readable project ledger that already represents active lane or attempt state.
- Do not add `docs/active/lane-ledger.jsonl` just because the global kit can read one.
- Keep readiness claims tied to fresh runtime or owner evidence, not recorded docs.

## OPL Family Closeout

Use this profile when asked to close out OPL-family root checkouts, absorb eligible worktrees, clean stale lanes, or prove multi-repo currentness across `one-person-lab`, `med-autoscience`, `med-autogrant`, `redcube-ai`, `opl-meta-agent`, `opl-bookforge`, and `one-person-lab-app`.

Fresh evidence order:

1. Freeze each repo with `git fetch --all --prune`, `git status --short --branch`, `git rev-parse HEAD origin/main`, `git worktree list --porcelain`, and `python3 scripts/codex_ops_gate.py status --repo <repo>`.
2. For every non-root worktree, run `python3 scripts/worktree_absorption_audit.py --repo <repo> --target-ref main <worktree>`.
3. Apply the user's recent-write cutoff before deleting a worktree. `exact-merged` or `content-equivalent` proves absorption only; it does not by itself prove the worktree is old enough to remove.
4. Treat dirty files as lane candidates, not global blockers. Continue on disjoint write sets; stop only for same-write-set conflict, unclear semantic owner, insufficient verification, or non-fast-forward source-of-truth ambiguity.
5. For MAS/OPL runtime or readiness claims, also read the project-owned currentness surfaces and keep `ready_claim_authorized`, `release_ready`, `production_ready`, owner receipt, typed blocker, and provider-running proof separate.

Closeout evidence must name root commit equality with `origin/main`, remaining worktrees, unresolved gate lanes, skipped or protected write sets, and the focused repo-native validation that covered each absorbed lane.

## Ordinary Repo Style

For repos without a native workflow ledger:

- Leave `ledger` empty.
- Let `~/.codex/state/codex-ops-kit/ledgers/` hold Codex workflow baton entries.
- Keep project files untouched until there is a durable repo-specific reason to add a profile.

## RHO First-Pass Style

For multi-project Codex improvement:

- Generate compact summaries before asking RHO to digest raw session files.
- Keep the first pass at `micro` or summary-only scale.
- Run deeper `tiny` or `small` RHO only on projects whose summaries show recurring high-cost failure modes.
- Keep `--no-apply` until a human has classified the winner as global rule, user-level skill/tool, project profile, project fact, or reject.
