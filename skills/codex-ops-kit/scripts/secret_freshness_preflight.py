#!/usr/bin/env python3
"""Secret-safe capability and cache freshness preflight."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def run_probe(command: str | None, cwd: str | None, timeout: int) -> dict[str, Any] | None:
    if not command:
        return None
    try:
        proc = subprocess.run(command, shell=True, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "exit_code": None,
            "timed_out": True,
            "timeout_seconds": timeout,
            "stdout_redacted": True,
            "stderr_tail": "",
        }
    return {
        "command": command,
        "exit_code": proc.returncode,
        "stdout_redacted": bool(proc.stdout),
        "stderr_tail": proc.stderr[-1000:],
    }


def cache_status(paths: list[str], max_age_seconds: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now = time.time()
    for raw in paths:
        path = Path(raw).expanduser()
        exists = path.exists()
        mtime = path.stat().st_mtime if exists else None
        age = round(now - mtime, 1) if mtime else None
        rows.append(
            {
                "path": str(path),
                "exists": exists,
                "mtime": mtime,
                "age_seconds": age,
                "fresh": bool(age is not None and (max_age_seconds is None or age <= max_age_seconds)),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", action="append", default=[], help="Environment variable that must be set; value is never printed.")
    parser.add_argument("--cache", action="append", default=[], help="Cache file or directory path to stat.")
    parser.add_argument("--max-age-seconds", type=int)
    parser.add_argument("--realtime-probe", help="Secret-safe command that proves realtime capability without printing secrets.")
    parser.add_argument("--cwd")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--source-boundary", action="append", default=[])
    args = parser.parse_args(argv)
    env_rows = [{"name": name, "present": bool(os.environ.get(name))} for name in args.env]
    caches = cache_status(args.cache, args.max_age_seconds)
    probe = run_probe(args.realtime_probe, args.cwd, args.timeout)
    realtime_ok = probe is not None and probe.get("exit_code") == 0
    cache_fresh = bool(caches) and all(item["fresh"] for item in caches)
    if realtime_ok:
        classification = "realtime"
    elif cache_fresh:
        classification = "cache"
    else:
        classification = "blocked"
    report = {
        "classification": classification,
        "env": env_rows,
        "cache": caches,
        "realtime_probe": probe,
        "source_boundary": args.source_boundary,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if classification in {"realtime", "cache"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
