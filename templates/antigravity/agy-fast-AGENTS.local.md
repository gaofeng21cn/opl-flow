---
trigger: always_on
---
# Local agy-fast Overrides (OPL Flow Baseline)

Local complements to `rules/AGENTS.md` (which covers `run_checks` and Swarm `--cli` in `v0.3.1+`):

1. **`apply_edits` batch sizing & fresh read**: Keep batches `<=5` files (`bestEffort: true` for `>=3` files); `read_file` exact target lines right before editing unfamiliar or recently modified regions.
2. **Shared state-file concurrency guard (`/teamwork` & multi-agent)**: Never let concurrent subagents `apply_edits` the same shared file (`BRIEFING.md`, `progress.md`) against stale snapshots—write per-module shards for a single owner to merge, or append via `write_file(Append: true)`.
3. **Bounded stdout for ad-hoc probe scripts**: Inline `python3 - <<'PY'`, `.venv/bin/python`, and shell loops must aggregate in-script or pipe to `| head -n 80` / `| tail -n 60` to prevent `output.txt` spills.
