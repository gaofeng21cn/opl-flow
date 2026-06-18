# Bounded Forensics

Use this playbook before wide home/workspace scans, cleanup planning, large JSONL inspection, Codex rollout analysis, or session-history audit.

## Root Budget

Take a bounded root budget before scanning broadly:

```bash
python3 scripts/bounded_root_scan.py /path/to/root --max-depth 3 --top 20
```

Default excludes cover high-noise historical and build surfaces such as `sessions`, `archived_sessions`, `shell_snapshots`, `.git`, `node_modules`, `dist`, and `build`.

## JSONL And Session Streams

Use streamers for large rollout or session files:

```bash
python3 scripts/jsonl_forensics.py /path/to/rollouts --glob 'rollout*.jsonl' --max-files 100 --max-lines 200000
python3 scripts/codex_session_audit.py ~/.codex/sessions --group day --format tsv
```

If a deep audit is stopped early, answer from already cached bounded evidence and mark the remaining gap.
