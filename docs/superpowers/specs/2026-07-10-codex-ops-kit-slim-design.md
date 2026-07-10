# Codex Ops Kit Slim Design

## Goal

Keep `codex-ops-kit` as a narrow compatibility entry for high-risk Git lane and
release evidence. Remove general reasoning policy, project truth, retrospection,
session forensics, cache freshness, artifact QA, and phase tracking from the
skill.

## Ownership

- `AGENTS.md`, `TASTE.md`, and role prompts own general collaboration,
  root-cause, authority, and completion behavior.
- Codex owns subagent orchestration, goals, worktree handoff, permissions, and
  lifecycle hooks.
- `codex-ops-kit` owns only deterministic Git lane and GitHub release readback.
- `evidence-bound-closeout` owns generated artifact fingerprints and public
  surface evidence when installed.
- `codex-self-evolution` owns its RHO, session audit, summary, and phase journal
  tools. RHO remains permanently no-apply.

## Retained Contract

1. `codex_ops_gate.py` reports repository and worktree facts. Invalid Git
   repositories and explicitly required clean/current worktrees fail closed.
   Unrelated dirty worktrees remain visible but do not become a global write
   prohibition.
2. `worktree_absorption_audit.py` classifies a clean lane as exact merged,
   tree-equivalent, patch-equivalent, ahead-not-absorbed, or owner review. Patch
   equivalence must compare the lane commit set with the target. A lane that
   contains merge commits may be accepted automatically only when it is exact
   merged or tree-equivalent; otherwise merge-resolution equivalence requires
   owner review because `git cherry` does not prove it.
3. `release_url_audit.py` binds public GitHub release URLs and optional install
   commands to the canonical remote. Missing or failed GitHub release readback
   fails closed.

## Removed Surfaces

- Global baton/default ledgers and project profiles.
- Change manifests, bounded root scans, generic JSONL forensics, cache freshness,
  binary package probing, artifact finalization, and phase ledgers.
- RHO and session-history triggers from `codex-ops-kit`.
- Mission supervision, heartbeat, medical owner-consumption, root-cause, and
  generic subagent policy duplicated by the OPL Flow profile.

Historical state under `~/.codex/state/codex-ops-kit/` is not deleted. The new
skill simply stops creating or treating it as current lane authority.

## Verification

- Focused CLI contract tests use temporary real Git repositories and worktrees.
- `python3 scripts/verify.py` remains the OPL Flow repository gate.
- A temporary install must contain only the retained skill files.
- The installed user skill must match the absorbed repo-native source and contain
  no `__pycache__` artifacts.
