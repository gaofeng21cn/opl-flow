---
name: third-party-audit-triage
description: >-
  Use when evaluating third-party, Codex, or external code audit and review reports,
  verifying every finding against live code and runtime before selectively fixing
  confirmed high-value issues with regression readback.
---

# Third-Party Audit Triage & Verification Workflow

Treat external/Codex audit reports as **hypotheses, never truth**. Verify against live code, contracts, and fresh test/CLI outputs before accepting or rejecting any item.

## Steps

1. **Verify every claim against live truth**:
   - Check `git status --short` / worktree isolation first so dirty trees are not mixed up.
   - Use one `batch_search` call (up to 20 queries across symbols, paths, git history) + `quick_outline` on >300-line files + parallel ranged `read_file` + fresh CLI/test readback.
   - Truth precedence: **live source + contracts + tests + fresh runtime readback** override prose docs or external review claims.

2. **Deliver a Verdict Table**:
   - Summarize all audit items in a compact table before editing:
     `| Finding | Verdict (Confirmed / Partial / False Positive / Out-of-Scope) | Exact File:Line Evidence | Risk & Net Value | Planned Action |`
   - Explicitly refute false positives or over-engineered suggestions with exact `file:line` evidence.

3. **Fix only confirmed high/medium-value issues at canonical owner**:
   - Apply fixes at the authoritative owner module/contract rather than adding parallel compatibility shims.
   - Batch edits via `apply_edits(bestEffort: true)` in groups of `<=5` files; read exact target lines immediately before editing.
   - Never apply speculative cosmetic churn or out-of-scope refactors.

4. **Minimal focused regression verification & readback**:
   - Run targeted tests/checks via `run_checks(outputMode: "compact")` (or single `run_command`).
   - Verify `git status --short` and `git diff --stat`; explicitly report both fixed items and rejected/deferred items with evidence.
