#!/usr/bin/env python3
"""Read-only audit before absorbing or deleting git worktrees."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


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


def status(repo: Path) -> list[str]:
    proc = git(repo, ["status", "--short"])
    if proc.returncode != 0:
        return [f"git status failed: {proc.stderr.strip()}"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def merge_base_ancestor(repo: Path, left: str, right: str) -> bool | None:
    if not left or not right:
        return None
    proc = git(repo, ["merge-base", "--is-ancestor", left, right])
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def patch_id(repo: Path, left: str, right: str) -> str | None:
    if not left or not right:
        return None
    diff = git(repo, ["diff", f"{left}...{right}"])
    if diff.returncode != 0 or not diff.stdout.strip():
        return ""
    proc = subprocess.run(["git", "patch-id", "--stable"], input=diff.stdout, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def audit_one(main_repo: Path, worktree: Path, base_ref: str, target_ref: str) -> dict[str, Any]:
    exists = worktree.exists()
    wt_root = repo_root(worktree) if exists else worktree.resolve()
    head = git_text(wt_root, ["rev-parse", "HEAD"]) if exists else ""
    branch = git_text(wt_root, ["branch", "--show-current"]) if exists else ""
    dirty = status(wt_root) if exists else []
    base_sha = git_text(main_repo, ["rev-parse", base_ref])
    target_sha = git_text(main_repo, ["rev-parse", target_ref])
    item: dict[str, Any] = {
        "worktree": str(worktree),
        "exists": exists,
        "repo_root": str(wt_root),
        "branch": branch or "DETACHED",
        "head_sha": head,
        "dirty_status": dirty,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "target_ref": target_ref,
        "target_sha": target_sha,
        "head_is_ancestor_of_target": merge_base_ancestor(main_repo, head, target_sha),
        "target_is_ancestor_of_head": merge_base_ancestor(main_repo, target_sha, head),
        "patch_id_vs_target": patch_id(main_repo, target_sha, head),
    }
    if not exists:
        item["classification"] = "deleted-without-evidence"
    elif dirty:
        item["classification"] = "still-dirty"
    elif item["head_is_ancestor_of_target"]:
        item["classification"] = "exact-merged"
    elif item["patch_id_vs_target"] == "":
        item["classification"] = "content-equivalent"
    elif item["target_is_ancestor_of_head"]:
        item["classification"] = "ahead-not-absorbed"
    else:
        item["classification"] = "needs-owner-review"
    return item


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base-ref", default="HEAD")
    parser.add_argument("--target-ref", default="HEAD")
    parser.add_argument("worktrees", nargs="+")
    args = parser.parse_args(argv)
    repo = repo_root(Path(args.repo).expanduser())
    results = [audit_one(repo, Path(path).expanduser(), args.base_ref, args.target_ref) for path in args.worktrees]
    report = {"repo": str(repo), "results": results}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    bad = [item for item in results if item["classification"] not in {"exact-merged", "content-equivalent"}]
    return 2 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
