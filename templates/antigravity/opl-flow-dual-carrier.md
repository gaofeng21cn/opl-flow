---
name: opl-flow-dual-carrier
description: >-
  Coordinate tasks across Codex, Google AntiGravity, and OPL DSH using one
  unified OPL Flow Beads/Dolt Ledger and zero-token auto router: inspect inbox
  and active local sessions, submit or bind tasks targeting codex, antigravity,
  or dsh, claim active slices to prevent dual-writer conflicts, and emit
  worker_callback receipts upon completion or checkpoint.
---

# OPL Flow Multi-Carrier Coordination (Codex + AntiGravity + OPL DSH)

OPL Flow runs **one unified zero-token background Router** (`opl-flow up`, defaulting to `--bridge auto`) over **one Beads/Dolt Ledger** across Codex, AntiGravity, and OPL DSH (such as `agy + Gemini` harness combinations). Keep one writer per attempt so carriers never modify the same write set concurrently.

## 1. Inspect Shared Queue, Active Sessions & Router Status

```bash
opl-flow ps
opl-flow sessions
opl-flow status --json
```

`opl-flow sessions` (and `opl-flow ps` / Decision Dashboard's `活跃对话` tab) discovers active local sessions across Codex, AntiGravity, and OPL DSH from local metadata without reading chat contents or consuming LLM tokens. Unbound free chats automatically enable workspace collision protection (`worktree_required_active_local_session`) without interrupting chats or auto-creating Beads.

## 2. Unified Background Router (`--bridge auto`)

```bash
# Recommended: single unified background router dynamically selecting Codex or AntiGravity per objective/event
opl-flow up

# Pin a single explicit control bridge only when overriding auto routing
opl-flow up --bridge antigravity
opl-flow up --bridge codex
```

Idle ticks invoke zero LLM turns regardless of bridge configuration.

## 3. Submit Tasks or Bind Active Sessions

```bash
# Route a slice to AntiGravity (`local-antigravity`)
opl-flow send "Implement UI polish and verify build" --executor antigravity --write-set decision-dashboard/app.js

# Route a slice to OPL DSH (`local-dsh`), optionally binding an active DSH session
opl-flow send "Cross-check component layout" --executor dsh --session dsh:<session-id>

# Route a slice to Codex (`local-codex`)
opl-flow send "Refactor ledger sync tests" --executor codex --write-set scripts/opl_ledger.py,tests/test_opl_ledger.py
```

## 4. Prevent Dual-Writer Collisions When Working Interactively

When picking up a registered Bead manually inside an interactive AntiGravity or DSH conversation:

1. **Claim an async launch envelope** inside the OPL Flow repository before editing so the Router and sibling carriers see the active owner and `write_set` lock:

```bash
python3 scripts/opl_fleet.py dispatch run \
  --adapter local-antigravity --mode envelope \
  --owner-task <bead-id> \
  --owner-thread "antigravity:${ANTIGRAVITY_CONVERSATION_ID}" \
  --handoff-json @handoff.json
```

2. **Work only within `handoff.write_set`** (or an isolated `git worktree` when another slice or active local chat overlaps).
3. **Return `opl_worker_result.v1` and emit `worker_callback`** when finished, checkpointed, or blocked:

```bash
python3 scripts/opl_fleet.py dispatch complete \
  --attempt-id <attempt-id> \
  --handoff-json @handoff.json \
  --result-json @result.json \
  --callback-state-dir ~/.local/state/opl-flow/events/<instance-hash>
```

For headless DSH worker slices, Fleet invokes `scripts/opl_dsh_bridge.py` (`--adapter local-dsh --use-dsh-bridge --dsh-combination <id>`). The Ledger owner always verifies canonical readback before accepting or closing a Bead.

## 5. Carrier Division of Labor & Stall Pullback

- **Explicit opt-in for interactive Codex**: AntiGravity handles tasks independently by default and invokes `codex-supervisor` only when explicitly requested by the user (or when a Ledger objective explicitly targets `--executor codex`).
- **Keep human-alignment, docs, and UI in AntiGravity**: Even when Codex is requested, keep intent clarification, design tradeoffs, docs/PRD/README/reports, UI visual design, interaction logic, and final user-facing acceptance inside AntiGravity; delegate only well-bounded implementation, refactoring, tests, local terminal operations, and deployments to Codex.
- **Actively supervise and pull back stalled tasks**: Monitor running `codex-supervisor` threads against expected milestones via `status`, `history`, and bounded `wait` windows (5–10 min heartbeats for normal coding, <=15–20 min for heavy builds/tests). When progress slows markedly or stalls, check `status`/`history` and issue one concise `steer` if recoverable; if still stuck, blocked on judgment/interaction, or faster to finish directly, `interrupt` immediately and pull the work back into AntiGravity rather than waiting passively.
