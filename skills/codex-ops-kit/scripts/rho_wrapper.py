#!/usr/bin/env python3
"""Budgeted wrapper for wbopan/retro-harness Codex RHO runs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
STATE_DIR = CODEX_HOME / "state" / "codex-ops-kit"
DEFAULT_HEARTBEAT_SECONDS = 60
DEFAULT_STALLED_ARTIFACT_SECONDS = 900


@dataclass(frozen=True)
class Budget:
    max_sessions: int
    k: int
    n: int
    probes: int
    concurrency: int
    max_rollout_kb: int | None


BUDGETS = {
    "micro": Budget(max_sessions=2, k=1, n=1, probes=0, concurrency=1, max_rollout_kb=1024),
    "tiny": Budget(max_sessions=8, k=3, n=1, probes=1, concurrency=1, max_rollout_kb=1536),
    "small": Budget(max_sessions=16, k=4, n=2, probes=1, concurrency=2, max_rollout_kb=3072),
    "medium": Budget(max_sessions=24, k=6, n=2, probes=2, concurrency=3, max_rollout_kb=6144),
    "full": Budget(max_sessions=36, k=8, n=2, probes=4, concurrency=4, max_rollout_kb=None),
}


def find_retro_script(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env_path = os.environ.get("RHO_RETRO_SCRIPT")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    cwd = Path.cwd()
    candidates.extend(
        [
            cwd / "work" / "retro-harness" / "codex" / "retrospection.py",
            STATE_DIR / "retro-harness" / "codex" / "retrospection.py",
            Path.home() / "workspace" / "retro-harness" / "codex" / "retrospection.py",
            Path.home() / "Documents" / "Codex" / "2026-06-13" / "wbopan-retro-harness-https-github-com" / "work" / "retro-harness" / "codex" / "retrospection.py",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit("cannot find retro-harness codex/retrospection.py; pass --retro or set RHO_RETRO_SCRIPT")


def session_meta(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
        data = json.loads(first)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if data.get("type") != "session_meta":
        return None
    return data.get("payload", {})


def select_sessions(project: Path, budget: Budget, max_rollout_kb: int | None, since_days: int | None) -> list[dict[str, Any]]:
    sessions_root = CODEX_HOME / "sessions"
    if not sessions_root.is_dir():
        return []
    project_s = str(project.resolve())
    now = time.time()
    cutoff = None if since_days is None or since_days <= 0 else now - since_days * 24 * 3600
    selected: list[dict[str, Any]] = []
    size_cap = max_rollout_kb if max_rollout_kb is not None else budget.max_rollout_kb
    for path in sessions_root.rglob("rollout-*.jsonl"):
        try:
            st = path.stat()
        except OSError:
            continue
        if cutoff is not None and st.st_mtime < cutoff:
            continue
        size_kb = st.st_size // 1024
        if size_kb < 5 or now - st.st_mtime < 600:
            continue
        if size_cap is not None and size_kb > size_cap:
            continue
        meta = session_meta(path)
        if not meta:
            continue
        cwd = str(meta.get("cwd", ""))
        if cwd != project_s and not cwd.startswith(project_s + os.sep):
            continue
        selected.append({"file": str(path), "sizeKb": size_kb, "mtime": st.st_mtime, "cwd": cwd})
    selected.sort(key=lambda item: (-int(item["sizeKb"]), -float(item["mtime"])))
    return selected[: budget.max_sessions]


def build_overlay(selected: list[dict[str, Any]], run_root: Path) -> Path:
    overlay = run_root / "codex_home"
    sessions = overlay / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    real_sessions = CODEX_HOME / "sessions"
    for item in selected:
        src = Path(item["file"])
        try:
            rel = src.relative_to(real_sessions)
        except ValueError:
            rel = Path(src.name)
        dest = sessions / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(src)
    return overlay


def patch_retrospection(retro: Path, run_root: Path) -> Path:
    text = retro.read_text(encoding="utf-8")
    needle = 'codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))'
    replacement = 'codex_home = Path(os.environ.get("RHO_SESSION_HOME", os.environ.get("CODEX_HOME", Path.home() / ".codex")))'
    if needle not in text:
        raise SystemExit("unsupported retrospection.py: cannot patch codex_home lookup for session overlay")
    patched = run_root / "retrospection.session-overlay.py"
    patched.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
    return patched


def command_for(args: argparse.Namespace, script: Path, project: Path, budget: Budget) -> list[str]:
    cmd = [
        sys.executable,
        str(script),
        "--project",
        str(project),
        "--max-sessions",
        str(budget.max_sessions),
        "--k",
        str(budget.k),
        "--n",
        str(budget.n),
        "--probes",
        str(budget.probes),
        "--concurrency",
        str(budget.concurrency),
    ]
    if args.reasoning_effort:
        cmd.extend(["--reasoning-effort", args.reasoning_effort])
    if args.model:
        cmd.extend(["--model", args.model])
    if not args.allow_apply:
        cmd.append("--no-apply")
    for extra in args.rho_arg or []:
        cmd.extend(["--codex-arg", extra])
    return cmd


def retrospection_run_root(project: Path, start_ts: str) -> Path:
    return CODEX_HOME / "retrospection-runs" / f"{start_ts}-{project.name}"


def child_process_count(pid: int) -> int | None:
    try:
        proc = subprocess.run(["pgrep", "-P", str(pid)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        return None
    if proc.returncode not in {0, 1}:
        return None
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def newest_artifact(root: Path) -> dict[str, Any] | None:
    if not root.exists():
        return None
    newest: tuple[float, Path] | None = None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest[0]:
            newest = (mtime, path)
    if newest is None:
        return None
    mtime, path = newest
    return {
        "path": str(path),
        "seconds_since_update": round(max(0.0, time.time() - mtime), 1),
        "mtime": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
    }


def write_heartbeat(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def run_with_heartbeat(
    cmd: list[str],
    env: dict[str, str],
    run_root: Path,
    rho_root: Path,
    interval: int,
    stalled_artifact_seconds: int,
) -> int:
    heartbeat_path = run_root / "heartbeat.jsonl"
    start = time.time()
    proc = subprocess.Popen(cmd, env=env)
    try:
        while True:
            try:
                return_code = proc.wait(timeout=max(1, interval))
            except subprocess.TimeoutExpired:
                elapsed = round(time.time() - start, 1)
                artifact = newest_artifact(rho_root)
                stalled_seconds = artifact.get("seconds_since_update") if artifact else None
                item = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "heartbeat",
                    "pid": proc.pid,
                    "elapsed_seconds": elapsed,
                    "child_process_count": child_process_count(proc.pid),
                    "rho_run_root": str(rho_root),
                    "newest_artifact": artifact,
                    "stalled_artifact_seconds": stalled_seconds,
                    "stalled_artifact": bool(stalled_seconds is not None and stalled_seconds >= stalled_artifact_seconds),
                }
                write_heartbeat(heartbeat_path, item)
                print(json.dumps(item, ensure_ascii=False, sort_keys=True), flush=True)
                continue
            item = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "completed",
                "pid": proc.pid,
                "elapsed_seconds": round(time.time() - start, 1),
                "exit_code": return_code,
                "rho_run_root": str(rho_root),
                "newest_artifact": newest_artifact(rho_root),
            }
            write_heartbeat(heartbeat_path, item)
            print(json.dumps(item, ensure_ascii=False, sort_keys=True), flush=True)
            return return_code
    except KeyboardInterrupt:
        item = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "interrupted",
            "pid": proc.pid,
            "elapsed_seconds": round(time.time() - start, 1),
            "rho_run_root": str(rho_root),
            "newest_artifact": newest_artifact(rho_root),
        }
        write_heartbeat(heartbeat_path, item)
        proc.terminate()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--budget", choices=sorted(BUDGETS), default="tiny")
    parser.add_argument("--max-sessions", type=int, help="Override the selected budget's max session count.")
    parser.add_argument("--k", type=int, help="Override the selected budget's coreset size.")
    parser.add_argument("--n", type=int, help="Override the selected budget's candidate count.")
    parser.add_argument("--probes", type=int, help="Override the selected budget's probe count.")
    parser.add_argument("--concurrency", type=int, help="Override the selected budget's Codex concurrency.")
    parser.add_argument("--max-rollout-kb", type=int, help="Override the budget rollout size cap. Use 0 for no cap.")
    parser.add_argument("--since-days", type=int, default=30, help="Only mine sessions modified within this many days. Use 0 for no date cap.")
    parser.add_argument("--retro", help="Path to wbopan/retro-harness/codex/retrospection.py.")
    parser.add_argument("--run", action="store_true", help="Execute RHO. Without this flag, only print the selected sessions and command.")
    parser.add_argument("--allow-apply", action="store_true", help="Allow RHO to apply the winning candidate. Default is --no-apply.")
    parser.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--model")
    parser.add_argument("--rho-arg", action="append", help="Extra --codex-arg value passed to retrospection.py.")
    parser.add_argument("--heartbeat-seconds", type=int, default=DEFAULT_HEARTBEAT_SECONDS, help="Emit and record progress heartbeats while RHO is running.")
    parser.add_argument("--stalled-artifact-seconds", type=int, default=DEFAULT_STALLED_ARTIFACT_SECONDS, help="Mark heartbeats when the newest RHO artifact has not changed for this many seconds.")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"--project {project} is not a directory")
    base = BUDGETS[args.budget]
    budget = Budget(
        max_sessions=args.max_sessions if args.max_sessions is not None else base.max_sessions,
        k=args.k if args.k is not None else base.k,
        n=args.n if args.n is not None else base.n,
        probes=args.probes if args.probes is not None else base.probes,
        concurrency=args.concurrency if args.concurrency is not None else base.concurrency,
        max_rollout_kb=base.max_rollout_kb,
    )
    max_rollout_kb = None if args.max_rollout_kb == 0 else args.max_rollout_kb
    selected = select_sessions(project, budget, max_rollout_kb, args.since_days)
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = STATE_DIR / "rho-wrapper-runs" / (run_ts + "-" + project.name)
    run_root.mkdir(parents=True, exist_ok=True)
    retro = find_retro_script(args.retro)
    overlay = build_overlay(selected, run_root)
    patched = patch_retrospection(retro, run_root)
    cmd = command_for(args, patched, project, budget)
    report = {
        "project": str(project),
        "budget": args.budget,
        "budget_detail": {
            "max_sessions": budget.max_sessions,
            "k": budget.k,
            "n": budget.n,
            "probes": budget.probes,
            "concurrency": budget.concurrency,
            "max_rollout_kb": max_rollout_kb if max_rollout_kb is not None else budget.max_rollout_kb,
        },
        "retro_script": str(retro),
        "session_overlay": str(overlay),
        "selected_sessions": selected,
        "since_days": args.since_days,
        "selected_count": len(selected),
        "command": cmd,
        "no_apply": not args.allow_apply,
        "run_root": str(run_root),
        "expected_rho_run_root": str(retrospection_run_root(project, run_ts)),
        "heartbeat_path": str(run_root / "heartbeat.jsonl"),
        "heartbeat_seconds": args.heartbeat_seconds,
        "stalled_artifact_seconds": args.stalled_artifact_seconds,
        "summary_first_hint": (
            "For cross-project or large-history runs, generate compact summaries with "
            "rollout_summarizer.py before running raw RHO."
        ),
    }
    (run_root / "wrapper-plan.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not selected:
        return 1
    if not args.run:
        return 0
    env = os.environ.copy()
    env["RHO_SESSION_HOME"] = str(overlay)
    return run_with_heartbeat(
        cmd,
        env,
        run_root,
        retrospection_run_root(project, run_ts),
        max(1, args.heartbeat_seconds),
        max(1, args.stalled_artifact_seconds),
    )


if __name__ == "__main__":
    raise SystemExit(main())
