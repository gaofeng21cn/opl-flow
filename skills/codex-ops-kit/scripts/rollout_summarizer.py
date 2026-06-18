#!/usr/bin/env python3
"""Create compact Codex rollout summaries for RHO prefiltering."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any


CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def safe_tail(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit // 2] + "\n...[snip]...\n" + value[-limit // 2 :]


def summarize_file(path: Path) -> dict[str, Any] | None:
    meta: dict[str, Any] | None = None
    user_messages: list[str] = []
    assistant_messages: list[str] = []
    commands: list[str] = []
    failures: list[str] = []
    event_counts: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for idx, line in enumerate(lines[:6000]):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = item.get("type")
        event_counts[typ] = event_counts.get(typ, 0) + 1
        payload = item.get("payload") or {}
        if idx == 0 and typ == "session_meta":
            meta = payload
        if typ == "event_msg":
            ptype = payload.get("type")
            msg = str(payload.get("message") or payload.get("last_agent_message") or "")
            if ptype == "user_message" and msg and not msg.startswith("# AGENTS.md instructions"):
                user_messages.append(safe_tail(msg, 1200))
            elif ptype in {"agent_message", "task_complete"} and msg:
                assistant_messages.append(safe_tail(msg, 1600))
        elif typ == "response_item":
            ptype = payload.get("type")
            if ptype == "function_call":
                name = str(payload.get("name") or "")
                raw_args = payload.get("arguments")
                cmd = ""
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                    if isinstance(args, dict):
                        cmd = str(args.get("cmd") or args.get("command") or "")
                if cmd:
                    commands.append(safe_tail(cmd, 400))
                elif name:
                    commands.append(name)
            elif ptype == "function_call_output":
                output = str(payload.get("output") or "")
                if re.search(r"\b(exit code|error|failed|traceback|exception|permission denied)\b", output, re.I):
                    failures.append(safe_tail(output, 800))
    if not meta:
        return None
    st = path.stat()
    return {
        "type": "codex_rollout_summary",
        "source_file": str(path),
        "cwd": meta.get("cwd"),
        "timestamp": meta.get("timestamp") or meta.get("id"),
        "size_kb": st.st_size // 1024,
        "mtime": st.st_mtime,
        "user_messages": user_messages[-4:],
        "assistant_messages": assistant_messages[-3:],
        "commands_sample": commands[-12:],
        "failure_signals": failures[-6:],
        "event_counts": event_counts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--since-days", type=int, default=30)
    parser.add_argument("--max-sessions", type=int, default=24)
    parser.add_argument("--max-rollout-kb", type=int, default=0, help="0 means no cap.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser().resolve()
    sessions_root = CODEX_HOME / "sessions"
    cutoff = time.time() - args.since_days * 24 * 3600 if args.since_days > 0 else None
    rows: list[tuple[int, float, Path]] = []
    for path in sessions_root.rglob("rollout-*.jsonl"):
        try:
            st = path.stat()
            if cutoff is not None and st.st_mtime < cutoff:
                continue
            if st.st_size < 5 * 1024:
                continue
            if args.max_rollout_kb and st.st_size // 1024 > args.max_rollout_kb:
                continue
            with path.open(encoding="utf-8", errors="replace") as handle:
                first = json.loads(handle.readline())
            if first.get("type") != "session_meta":
                continue
            cwd = str((first.get("payload") or {}).get("cwd") or "")
            project_s = str(project)
            if cwd != project_s and not cwd.startswith(project_s + os.sep):
                continue
            rows.append((st.st_size, st.st_mtime, path))
        except Exception:
            continue
    rows.sort(key=lambda item: (-item[0], -item[1]))
    summaries = [s for _, _, path in rows[: args.max_sessions] if (s := summarize_file(path))]
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"project": str(project), "summaries": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"project": str(project), "output": str(out), "summaries": len(summaries)}, ensure_ascii=False, indent=2))
    return 0 if summaries else 1


if __name__ == "__main__":
    raise SystemExit(main())
