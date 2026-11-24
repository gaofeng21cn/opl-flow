---
name: swarm-code-worker-brief
description: >-
  Use before spawning Antigravity Swarm workers (`swarm add`) for parallel coding,
  refactoring, or multi-module audits to prevent serial edit_file storms, output.txt
  spills, and missing agy-fast CLI syntax.
---

# Swarm Code Worker Brief Template

Antigravity does **not** mount MCP servers, `user_rules`, or `SessionStart` snapshots into Swarm workers. Without explicit CLI instructions, workers fall back to slow serial `edit_file` splits and verbose `run_command` calls that spill to `output.txt`.

## Workspace & Isolation Rules

- **Concurrent writers/builders**: always pass `workspace: "share"` (or `"branch"` for full isolation) and assign disjoint file/directory ownership per worker.
- **Pure readers/verifiers**: keep default `workspace: "inherit"`.
- **Landing before kill**: merge or verify each worker's changes **before** calling `swarm kill` (killing permanently deletes a `share`/`branch` workspace).

## Mandatory Brief Block (Copy into `swarm add` `brief`)

Include the following block verbatim alongside the worker's owned files and acceptance criteria:

```text
## Tooling & Hygiene Rules (Swarm Worker — No MCP Mounted)
- Small/known ranges: use parallel `read_file(StartLine, EndLine)` (<=200 lines per range). Avoid blind full-file reads (>300 lines).
- Batch search, outlines, multi-file edits, and concurrent checks via `agy-fast --cli` in `run_command` (keeps output <=8.8 KB, zero output.txt spills):
  Set `F="node ~/.gemini/config/plugins/agy-fast/dist/mcp-server.mjs --cli"`
  - Search (use `--text`/`--regex`/`--glob`/`--git`):
    `$F search --text "symbol" --path src --git "status --short"`
  - Outline (>300-line files before reading):
    `$F outline src/a.ts src/b.ts`
  - Slice small ranges + outlines:
    `$F slice src/a.ts:1-60,120-160 --outline src/b.ts`
  - Multi-hunk / multi-file atomic edit (+ optional verify):
    `$F edit --best-effort --verify "npm run typecheck" --stdin <<'EOF'`
    `{"edits":[{"path":"src/a.ts","hunks":[{"target":"old","replacement":"new"}]}]}`
    `EOF`
  - Concurrent checks (default compact; use `--full` only for bounded stdout):
    `$F check --compact "cmd1" "cmd2"`
- Keep <=10s shell commands synchronous (`WaitMsBeforeAsync: 5000-10000`).
- Report back concisely: modified files, verification command results, and any blockers (no raw file dumps).
```

## Validation

- Confirm every worker brief specifies: (1) owned paths, (2) the `--cli` block above, and (3) concrete done criteria & verification command.
