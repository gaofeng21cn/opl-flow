#!/usr/bin/env python3
"""Run or append phase-ledger entries for long ops chains."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def append_entry(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def parse_field(values: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values or []:
        if "=" not in value:
            raise SystemExit(f"--field expects key=value, got: {value}")
        key, raw = value.split("=", 1)
        try:
            result[key] = json.loads(raw)
        except json.JSONDecodeError:
            result[key] = raw
    return result


def append_command(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger).expanduser()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase,
        "status": args.status,
        "command": args.command,
        "exit_code": args.exit_code,
        "evidence": args.evidence,
        "codex_home": str(codex_home()),
    }
    entry.update(parse_field(args.field))
    append_entry(ledger, {key: value for key, value in entry.items() if value is not None})
    print(json.dumps({"ledger": str(ledger), "entry": entry}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def run_command(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger).expanduser()
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home())
    start = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(args.command, shell=True, cwd=args.cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    duration = round(time.time() - start, 3)
    status = "completed" if proc.returncode == 0 else "failed"
    if args.status:
        status = args.status
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "started_at": started_at,
        "phase": args.phase,
        "status": status,
        "command": args.command,
        "command_shell_quoted": shlex.quote(args.command),
        "cwd": str(Path(args.cwd).expanduser().resolve()) if args.cwd else None,
        "exit_code": proc.returncode,
        "duration_seconds": duration,
        "stdout_tail": proc.stdout[-args.tail_chars :],
        "stderr_tail": proc.stderr[-args.tail_chars :],
        "codex_home": str(codex_home()),
    }
    entry.update(parse_field(args.field))
    append_entry(ledger, {key: value for key, value in entry.items() if value is not None})
    print(json.dumps({"ledger": str(ledger), "entry": entry}, ensure_ascii=False, indent=2, sort_keys=True))
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command_name", required=True)

    append = sub.add_parser("append", help="Append a manual phase entry.")
    append.add_argument("--ledger", required=True)
    append.add_argument("--phase", required=True)
    append.add_argument("--status", required=True)
    append.add_argument("--command")
    append.add_argument("--exit-code", type=int)
    append.add_argument("--evidence")
    append.add_argument("--field", action="append")
    append.set_defaults(func=append_command)

    run = sub.add_parser("run", help="Run a command and append timing/evidence.")
    run.add_argument("--ledger", required=True)
    run.add_argument("--phase", required=True)
    run.add_argument("--command", required=True)
    run.add_argument("--cwd")
    run.add_argument("--status")
    run.add_argument("--tail-chars", type=int, default=4000)
    run.add_argument("--field", action="append")
    run.set_defaults(func=run_command)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
