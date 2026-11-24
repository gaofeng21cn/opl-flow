---
trigger: always_on
---
# Local agy-fast Overrides (OPL Flow Baseline)

These overrides refine `rules/AGENTS.md` based on real AntiGravity session telemetry:

1. **`run_checks` discipline (avoid 8.8 KB truncation & single-command overhead)**:
   - Default to `outputMode: "compact"` for build/typecheck/lint/test checks. Only pass `outputMode: "full"` when you specifically need stdout of passing commands **and** the output is bounded (under 8 KB).
   - For a **single** command (or any command whose full output is likely >8 KB), use native `run_command` directly instead of wrapping 1 command in `run_checks`. Reserve `run_checks` for **>=2 independent concurrent commands**.
2. **`apply_edits` batching & mismatch prevention**:
   - Prefer **<=5 files per `apply_edits` call** (and always pass `bestEffort: true` when editing >=3 files) so large batches stay reliable and partial progress is preserved.
   - Read the exact target line range via `read_file` immediately before editing unfamiliar or recently modified regions to avoid stale-context target mismatches.
3. **Swarm Worker `--cli` copy-paste brief (mandatory syntax)**:
   - When spawning Swarm workers for coding/audit tasks (`swarm add`), include exact `--cli` flags in the brief (note: `search` uses `--text`/`--regex`/`--glob`/`--git` or `--pattern`, and `check` defaults to `--compact`):
     ```text
     Batch via agy-fast CLI (`F="node ~/.gemini/config/plugins/agy-fast/dist/mcp-server.mjs --cli"`):
     - Search: `$F search --text "foo" --path src --git "status --short"` (use `--regex` for regex, `--glob` for glob)
     - Outline: `$F outline src/a.ts src/b.ts`
     - Edit: `$F edit --best-effort --verify "npm run typecheck" --stdin <<'EOF'` with `{"edits":[...]}`
     - Checks: `$F check --compact "cmd1" "cmd2"`
     ```
