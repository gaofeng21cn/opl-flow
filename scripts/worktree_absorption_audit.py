#!/usr/bin/env python3
"""Classify whether one Git worktree has been absorbed by a target ref."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


SCHEMA = "opl_flow_worktree_absorption_audit.v1"
AUTOMATIC_CLASSIFICATIONS = {"exact_merged", "tree_equivalent", "patch_equivalent"}


class AuditError(RuntimeError):
    """Raised when the requested Git identity cannot be inspected safely."""


def run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise AuditError(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return result


def git_path(cwd: Path, value: str) -> Path:
    raw = run_git(cwd, "rev-parse", value).stdout.strip()
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (cwd / path).resolve()


def classify_commits(
    repo_root: Path,
    lane_commit: str,
    target: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify one locally verifiable commit against a target ref."""
    canonical_root = Path(
        run_git(repo_root, "rev-parse", "--show-toplevel").stdout.strip()
    ).resolve()
    target_head = run_git(
        canonical_root,
        "rev-parse",
        "--verify",
        f"{target}^{{commit}}",
    ).stdout.strip()
    lane_head = run_git(
        canonical_root,
        "rev-parse",
        "--verify",
        f"{lane_commit}^{{commit}}",
    ).stdout.strip()
    result: dict[str, Any] = payload if payload is not None else {
        "schema": SCHEMA,
        "ok": True,
        "repo_root": str(canonical_root),
        "worktree": None,
        "target": target,
        "lane_branch": None,
        "dirty": False,
        "dirty_entries": [],
    }
    result.update(
        target_head=target_head,
        lane_head=lane_head,
        merge_base=None,
        lane_commit_count=0,
        merge_commit_count=0,
        equivalent_commit_count=0,
        unabsorbed_commit_count=0,
        classification="owner_review",
        cleanup_allowed=False,
        issues=[],
    )

    contained = run_git(
        canonical_root,
        "merge-base",
        "--is-ancestor",
        lane_head,
        target_head,
        check=False,
    )
    if contained.returncode == 0:
        result["classification"] = "exact_merged"
        result["cleanup_allowed"] = True
        return result
    if contained.returncode not in (0, 1):
        raise AuditError(contained.stderr.strip() or "unable to compare target and lane ancestry")

    target_tree = run_git(canonical_root, "rev-parse", f"{target_head}^{{tree}}").stdout.strip()
    lane_tree = run_git(canonical_root, "rev-parse", f"{lane_head}^{{tree}}").stdout.strip()
    if target_tree == lane_tree:
        result["classification"] = "tree_equivalent"
        result["cleanup_allowed"] = True
        return result

    merge_base_result = run_git(
        canonical_root,
        "merge-base",
        target_head,
        lane_head,
        check=False,
    )
    if merge_base_result.returncode != 0 or not merge_base_result.stdout.strip():
        result["issues"].append("target and lane have no provable merge base")
        return result
    merge_base = merge_base_result.stdout.strip()
    result["merge_base"] = merge_base

    commit_rows = [
        line.split()
        for line in run_git(
            canonical_root,
            "rev-list",
            "--parents",
            f"{merge_base}..{lane_head}",
        ).stdout.splitlines()
        if line
    ]
    result["lane_commit_count"] = len(commit_rows)
    result["merge_commit_count"] = sum(len(row) > 2 for row in commit_rows)

    cherry_rows = [
        line
        for line in run_git(canonical_root, "cherry", target_head, lane_head).stdout.splitlines()
        if line
    ]
    result["equivalent_commit_count"] = sum(line.startswith("-") for line in cherry_rows)
    result["unabsorbed_commit_count"] = sum(line.startswith("+") for line in cherry_rows)

    if result["merge_commit_count"]:
        result["issues"].append(
            "lane contains merge commits; patch equivalence cannot prove merge-resolution equivalence"
        )
        return result
    if cherry_rows and result["unabsorbed_commit_count"] == 0:
        result["classification"] = "patch_equivalent"
        result["cleanup_allowed"] = True
        return result

    result["classification"] = "ahead_not_absorbed"
    result["issues"].append("lane contains commits not absorbed by the target")
    return result


def audit(repo_root: Path, worktree: Path, target: str) -> dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    worktree = worktree.expanduser().resolve()
    if not repo_root.is_dir():
        raise AuditError(f"repo root is not a directory: {repo_root}")
    if not worktree.is_dir():
        raise AuditError(f"worktree is not a directory: {worktree}")

    canonical_root = Path(run_git(repo_root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    lane_root = Path(run_git(worktree, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if lane_root != worktree:
        raise AuditError(f"worktree must be its Git top level: {worktree}")
    if git_path(canonical_root, "--git-common-dir") != git_path(lane_root, "--git-common-dir"):
        raise AuditError("repo root and worktree do not belong to the same Git repository")

    lane_head = run_git(lane_root, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    branch_result = run_git(lane_root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = branch_result.stdout.strip() or None
    dirty_entries = [
        line
        for line in run_git(lane_root, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
        if line
    ]

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": True,
        "repo_root": str(canonical_root),
        "worktree": str(lane_root),
        "target": target,
        "lane_branch": branch,
        "dirty": bool(dirty_entries),
        "dirty_entries": dirty_entries,
    }

    if dirty_entries:
        target_head = run_git(
            canonical_root,
            "rev-parse",
            "--verify",
            f"{target}^{{commit}}",
        ).stdout.strip()
        payload.update(
            target_head=target_head,
            lane_head=lane_head,
            merge_base=None,
            lane_commit_count=0,
            merge_commit_count=0,
            equivalent_commit_count=0,
            unabsorbed_commit_count=0,
            classification="owner_review",
            cleanup_allowed=False,
            issues=[],
        )
        payload["issues"].append("lane worktree is dirty")
        return payload
    return classify_commits(canonical_root, lane_head, target, payload=payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only classification of a Git worktree against a target ref"
    )
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--target", default="origin/main")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = audit(args.repo_root, args.worktree, args.target)
    except AuditError as exc:
        payload = {
            "schema": SCHEMA,
            "ok": False,
            "classification": "owner_review",
            "cleanup_allowed": False,
            "issues": [str(exc)],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
