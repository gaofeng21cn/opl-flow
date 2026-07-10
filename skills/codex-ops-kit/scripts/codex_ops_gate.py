#!/usr/bin/env python3
"""Report Git worktree facts and fail closed for explicitly required state."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args])


def git_text(repo: Path, args: list[str]) -> str:
    result = git(repo, args)
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve_repo(path: Path) -> tuple[Path, str | None]:
    candidate = path.expanduser().resolve()
    result = git(candidate, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0 or not result.stdout.strip():
        return candidate, result.stderr.strip() or "not a Git repository"
    return Path(result.stdout.strip()).resolve(), None


def is_ancestor(repo: Path, left: str, right: str) -> bool | None:
    if not left or not right:
        return None
    result = git(repo, ["merge-base", "--is-ancestor", left, right])
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def target_relation(repo: Path, head: str, target: str) -> str:
    if head == target:
        return "at-target"
    head_in_target = is_ancestor(repo, head, target)
    target_in_head = is_ancestor(repo, target, head)
    if head_in_target is True:
        return "behind"
    if target_in_head is True:
        return "ahead"
    if head_in_target is False and target_in_head is False:
        return "diverged"
    return "unknown"


def short_status(path: Path) -> tuple[list[str], str | None]:
    result = git(path, ["status", "--short"])
    if result.returncode != 0:
        return [], result.stderr.strip() or "git status failed"
    return [line for line in result.stdout.splitlines() if line.strip()], None


def list_worktrees(repo: Path, target_sha: str | None) -> tuple[list[dict[str, Any]], str | None]:
    result = git(repo, ["worktree", "list", "--porcelain"])
    if result.returncode != 0:
        return [], result.stderr.strip() or "git worktree list failed"

    raw_items: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            if current:
                raw_items.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ")
        elif line.startswith("HEAD "):
            current["head_sha"] = line.removeprefix("HEAD ")
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch refs/heads/")
        elif line == "detached":
            current["detached"] = True
        elif line == "bare":
            current["bare"] = True
    if current:
        raw_items.append(current)

    items: list[dict[str, Any]] = []
    for item in raw_items:
        path = Path(str(item.get("path") or "")).resolve()
        if item.get("bare"):
            dirty, status_error = [], None
        elif not path.is_dir():
            dirty, status_error = [], "worktree path does not exist"
        else:
            dirty, status_error = short_status(path)
        normalized = {
            **item,
            "path": str(path),
            "dirty_status": dirty,
            "status_error": status_error,
        }
        if target_sha:
            normalized["target_relation"] = target_relation(repo, str(item.get("head_sha") or ""), target_sha)
        items.append(normalized)
    return items, None


def required_failures(
    worktrees: list[dict[str, Any]],
    required_paths: list[str],
    predicate: str,
) -> list[dict[str, Any]]:
    by_path = {str(Path(str(item["path"])).resolve()): item for item in worktrees}
    failures: list[dict[str, Any]] = []
    for raw_path in required_paths:
        path = str(Path(raw_path).expanduser().resolve())
        item = by_path.get(path)
        if item is None:
            failures.append({"path": path, "reason": "not-listed"})
        elif item.get("status_error"):
            failures.append(item)
        elif predicate == "clean" and (item["dirty_status"] or item["status_error"]):
            failures.append(item)
        elif predicate == "current" and item.get("target_relation") != "at-target":
            failures.append(item)
    return failures


def status_report(args: argparse.Namespace) -> int:
    repo, repo_error = resolve_repo(Path(args.repo))
    errors = [repo_error] if repo_error else []
    target_sha: str | None = None
    worktrees: list[dict[str, Any]] = []

    if not repo_error:
        if args.target_ref:
            target_sha = git_text(repo, ["rev-parse", "--verify", args.target_ref]) or None
            if target_sha is None:
                errors.append(f"target ref cannot be resolved: {args.target_ref}")
        worktrees, worktree_error = list_worktrees(repo, target_sha)
        if worktree_error:
            errors.append(worktree_error)

    current_failures = required_failures(worktrees, args.require_current_worktree, "current")
    clean_failures = required_failures(worktrees, args.require_clean_worktree, "clean")
    ok = not errors and not current_failures and not clean_failures
    report = {
        "ok": ok,
        "repo": str(repo),
        "current_branch": git_text(repo, ["branch", "--show-current"]) if not repo_error else None,
        "head_sha": git_text(repo, ["rev-parse", "HEAD"]) if not repo_error else None,
        "origin_url": git_text(repo, ["remote", "get-url", "origin"]) if not repo_error else None,
        "target_ref": args.target_ref,
        "target_sha": target_sha,
        "worktrees": worktrees,
        "required_current_worktree_failures": current_failures,
        "required_clean_worktree_failures": clean_failures,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="Report repository and worktree facts.")
    status.add_argument("--repo", default=".")
    status.add_argument("--target-ref")
    status.add_argument("--require-current-worktree", action="append", default=[])
    status.add_argument("--require-clean-worktree", action="append", default=[])
    status.set_defaults(func=status_report)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
