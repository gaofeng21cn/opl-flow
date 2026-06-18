#!/usr/bin/env python3
"""Read-only Codex ops closeout gate for multi-lane repository work."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
DEFAULT_STATE_DIR = CODEX_HOME / "state" / "codex-ops-kit"
CLOSED_EVENTS = {"closed", "complete", "completed", "cleaned", "abandoned-with-owner"}


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args])


def git_text(repo: Path, args: list[str]) -> str:
    proc = git(repo, args)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def repo_root(path: Path) -> Path:
    proc = git(path, ["rev-parse", "--show-toplevel"])
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return path.resolve()


def repo_key(repo: Path) -> str:
    raw = str(repo.resolve())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def default_ledger(repo: Path) -> Path:
    return DEFAULT_STATE_DIR / "ledgers" / f"{repo.name}-{repo_key(repo)}.jsonl"


def short_status(path: Path) -> list[str]:
    proc = git(path, ["status", "--short"])
    if proc.returncode != 0:
        return [f"git status failed: {proc.stderr.strip()}"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def worktrees(repo: Path) -> list[dict[str, Any]]:
    proc = git(repo, ["worktree", "list", "--porcelain"])
    if proc.returncode != 0:
        return [{"error": proc.stderr.strip()}]
    result: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            if current:
                result.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line[len("worktree ") :]
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch ") :]
        elif line == "detached":
            current["detached"] = True
        elif line == "bare":
            current["bare"] = True
        else:
            current.setdefault("flags", []).append(line)
    if current:
        result.append(current)
    for item in result:
        path = item.get("path")
        if path and Path(path).is_dir() and not item.get("bare"):
            item["status"] = short_status(Path(path))
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid JSON: {exc}"}


def profile_paths(repo: Path) -> list[Path]:
    return [
        repo / ".codex-ops-profile.json",
        repo / ".codex" / "ops-profile.json",
        repo / "contracts" / "codex-ops-profile.json",
    ]


def load_profile(repo: Path, explicit: str | None) -> tuple[Path | None, dict[str, Any]]:
    candidates = [Path(explicit).expanduser()] if explicit else profile_paths(repo)
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else repo / candidate
        if path.is_file():
            return path.resolve(), read_json(path)
    return None, {}


def resolve_ledger(repo: Path, profile: dict[str, Any], explicit: str | None) -> Path:
    if explicit:
        ledger = Path(explicit).expanduser()
    else:
        ledger_value = profile.get("ledger")
        ledger = Path(str(ledger_value)).expanduser() if ledger_value else default_ledger(repo)
    return ledger if ledger.is_absolute() else repo / ledger


def read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            entries.append({"ledger_parse_error": str(exc), "line": index, "raw": line})
            continue
        item.setdefault("_line", index)
        entries.append(item)
    return entries


def latest_by_lane(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in entries:
        lane = str(item.get("lane_id") or item.get("lane") or "UNSPECIFIED")
        latest[lane] = item
    return latest


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "done", "clean", "merged"}


def is_closed(item: dict[str, Any]) -> bool:
    event = str(item.get("event") or item.get("state") or "").lower()
    if event in CLOSED_EVENTS:
        return True
    if truthy(item.get("merged_main")) and truthy(item.get("cleaned_worktree_branch")):
        return True
    if str(item.get("next_owner") or "").lower() in {"none", "closed"} and not item.get("blocker"):
        return True
    return False


def parse_kv(values: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--field expects key=value, got: {value}")
        key, raw = value.split("=", 1)
        try:
            data[key.strip()] = json.loads(raw.strip())
        except json.JSONDecodeError:
            data[key.strip()] = raw.strip()
    return data


def append_entry(args: argparse.Namespace) -> int:
    repo = repo_root(Path(args.repo).expanduser())
    _, profile = load_profile(repo, args.profile)
    ledger = resolve_ledger(repo, profile, args.ledger)
    entry: dict[str, Any] = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "lane_id": args.lane,
        "event": args.event,
        "repo": str(repo),
        "current_branch": git_text(repo, ["branch", "--show-current"]) or "DETACHED",
        "head_sha": git_text(repo, ["rev-parse", "HEAD"]) or "UNKNOWN",
        "dirty_status": short_status(repo),
    }
    optional = {
        "worktree": args.worktree,
        "write_domain": args.write_domain,
        "allowed_write_set": args.allowed_write_set,
        "forbidden_write_set": args.forbidden_write_set,
        "source_of_truth": args.source_of_truth,
        "owner_status": args.owner_status,
        "blocker": args.blocker,
        "admission": args.admission,
        "validation_command": args.validation_command,
        "validation_exit_code": args.validation_exit_code,
        "semantic_decision": args.semantic_decision,
        "commit": args.commit,
        "merged_main": args.merged_main,
        "cleaned_worktree_branch": args.cleaned_worktree_branch,
        "next_owner": args.next_owner,
    }
    entry.update({key: value for key, value in optional.items() if value is not None})
    entry.update(parse_kv(args.field or []))
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"appended": str(ledger), "entry": entry}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def run_check(repo: Path, raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        name = raw
        command = raw
    elif isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("command") or "unnamed")
        command = raw.get("command")
    else:
        return {"error": "invalid check entry", "entry": raw}
    if not command:
        return {"name": name, "error": "missing command"}
    proc = subprocess.run(
        str(command),
        shell=True,
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "name": name,
        "command": str(command),
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def status_report(args: argparse.Namespace) -> int:
    repo = repo_root(Path(args.repo).expanduser())
    profile_path, profile = load_profile(repo, args.profile)
    ledger = resolve_ledger(repo, profile, args.ledger)
    entries = read_ledger(ledger)
    latest = latest_by_lane(entries)
    unresolved = {lane: item for lane, item in latest.items() if not is_closed(item)}
    wt = worktrees(repo)
    dirty_wt = [item for item in wt if item.get("status")]
    current_truth_checks = []
    if args.run_profile_checks:
        for check in profile.get("current_truth_checks", []) or []:
            current_truth_checks.append(run_check(repo, check))
    report = {
        "repo": str(repo),
        "profile": str(profile_path) if profile_path else None,
        "profile_error": profile.get("_error"),
        "ledger": str(ledger),
        "ledger_exists": ledger.exists(),
        "current_branch": git_text(repo, ["branch", "--show-current"]) or "DETACHED",
        "head_sha": git_text(repo, ["rev-parse", "HEAD"]) or "UNKNOWN",
        "origin_url": git_text(repo, ["remote", "get-url", "origin"]),
        "ledger_entries": len(entries),
        "unresolved_lanes": unresolved,
        "dirty_or_staged_worktrees": dirty_wt,
        "worktree_count": len(wt),
        "project_truth_surfaces": profile.get("truth_surfaces", []),
        "current_truth_checks": current_truth_checks,
        "decisions": {
            "may_write": not unresolved and not dirty_wt and not profile.get("_error"),
            "owner_needed": bool(unresolved),
            "cleanup_needed": bool(dirty_wt),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    failed_checks = [check for check in current_truth_checks if check.get("exit_code") not in (0, None)]
    if args.strict and (unresolved or dirty_wt or failed_checks or profile.get("_error")):
        return 2
    return 0


def profile_template(_args: argparse.Namespace) -> int:
    template = {
        "ledger": "",
        "truth_surfaces": [
            "docs/status.md",
            "contracts/example-current-status.json",
        ],
        "current_truth_checks": [
            {
                "name": "repo status",
                "command": "git status --short",
            }
        ],
        "notes": "Leave ledger empty to use the user-level default under ~/.codex/state/codex-ops-kit/ledgers.",
    }
    print(json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append", help="Append one lane baton entry.")
    append.add_argument("--repo", default=".")
    append.add_argument("--profile")
    append.add_argument("--ledger")
    append.add_argument("--lane", required=True)
    append.add_argument("--event", required=True)
    append.add_argument("--worktree")
    append.add_argument("--write-domain")
    append.add_argument("--allowed-write-set")
    append.add_argument("--forbidden-write-set")
    append.add_argument("--source-of-truth")
    append.add_argument("--owner-status")
    append.add_argument("--blocker")
    append.add_argument("--admission")
    append.add_argument("--validation-command")
    append.add_argument("--validation-exit-code", type=int)
    append.add_argument("--semantic-decision")
    append.add_argument("--commit")
    append.add_argument("--merged-main")
    append.add_argument("--cleaned-worktree-branch")
    append.add_argument("--next-owner")
    append.add_argument("--field", action="append")
    append.set_defaults(func=append_entry)

    status = sub.add_parser("status", help="Read-only closeout report.")
    status.add_argument("--repo", default=".")
    status.add_argument("--profile")
    status.add_argument("--ledger")
    status.add_argument("--strict", action="store_true")
    status.add_argument("--run-profile-checks", action="store_true")
    status.set_defaults(func=status_report)

    template = sub.add_parser("profile-template", help="Print a project adapter profile template.")
    template.set_defaults(func=profile_template)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
