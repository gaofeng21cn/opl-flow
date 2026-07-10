#!/usr/bin/env python3
"""Classify whether clean worktree changes are represented by a target ref."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


SAFE_CLASSIFICATIONS = {"exact-merged", "tree-equivalent", "patch-equivalent"}


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


def repo_root(path: Path) -> tuple[Path, str | None]:
    candidate = path.expanduser().resolve()
    result = git(candidate, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0 or not result.stdout.strip():
        return candidate, result.stderr.strip() or "not a Git repository"
    return Path(result.stdout.strip()).resolve(), None


def registered_worktrees(repo: Path) -> tuple[set[Path], str | None]:
    result = git(repo, ["worktree", "list", "--porcelain"])
    if result.returncode != 0:
        return set(), result.stderr.strip() or "git worktree list failed"
    roots = {
        Path(line.removeprefix("worktree ")).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    }
    return roots, None


def is_ancestor(repo: Path, left: str, right: str) -> bool | None:
    result = git(repo, ["merge-base", "--is-ancestor", left, right])
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def short_status(repo: Path) -> tuple[list[str], str | None]:
    result = git(repo, ["status", "--short"])
    if result.returncode != 0:
        return [], result.stderr.strip() or "git status failed"
    return [line for line in result.stdout.splitlines() if line.strip()], None


def tree(repo: Path, ref: str) -> str:
    return git_text(repo, ["rev-parse", f"{ref}^{{tree}}"])


def cherry(repo: Path, target: str, head: str, base: str) -> tuple[list[str], str | None]:
    result = git(repo, ["cherry", target, head, base])
    if result.returncode != 0:
        return [], result.stderr.strip() or "git cherry failed"
    return [line for line in result.stdout.splitlines() if line.strip()], None


def audit_one(
    main_repo: Path,
    worktree: Path,
    base_ref: str | None,
    target_ref: str,
    registered_roots: set[Path],
) -> dict[str, Any]:
    requested_root = worktree.expanduser().resolve()
    item: dict[str, Any] = {"worktree": str(requested_root), "target_ref": target_ref}
    if not requested_root.exists():
        item.update(classification="deleted-without-evidence", errors=["worktree does not exist"])
        return item

    worktree_root, worktree_error = repo_root(requested_root)
    errors = [worktree_error] if worktree_error else []
    if requested_root not in registered_roots:
        errors.append("path is not a registered worktree root")
    target_sha = git_text(main_repo, ["rev-parse", "--verify", target_ref])
    head_sha = git_text(worktree_root, ["rev-parse", "HEAD"]) if not worktree_error else ""
    dirty, status_error = short_status(worktree_root) if not worktree_error else ([], None)
    if status_error:
        errors.append(status_error)
    if not target_sha:
        errors.append(f"target ref cannot be resolved: {target_ref}")
    base_sha = git_text(main_repo, ["rev-parse", "--verify", base_ref]) if base_ref else ""
    if not base_sha and head_sha and target_sha:
        base_sha = git_text(main_repo, ["merge-base", target_sha, head_sha])
    if not base_sha:
        errors.append(f"base ref cannot be resolved: {base_ref or 'merge-base'}")

    lane_count_text = git_text(main_repo, ["rev-list", "--count", f"{base_sha}..{head_sha}"]) if base_sha and head_sha else ""
    lane_commit_count = int(lane_count_text) if lane_count_text.isdigit() else None
    merge_count_text = git_text(main_repo, ["rev-list", "--count", "--merges", f"{base_sha}..{head_sha}"]) if base_sha and head_sha else ""
    lane_merge_commit_count = int(merge_count_text) if merge_count_text.isdigit() else None
    cherry_lines, cherry_error = cherry(main_repo, target_sha, head_sha, base_sha) if all((target_sha, head_sha, base_sha)) else ([], None)
    if cherry_error:
        errors.append(cherry_error)
    unabsorbed = [line for line in cherry_lines if line.startswith("+")]

    item.update(
        repo_root=str(worktree_root),
        branch=git_text(worktree_root, ["branch", "--show-current"]) or "DETACHED",
        head_sha=head_sha or None,
        target_sha=target_sha or None,
        base_ref=base_ref,
        base_sha=base_sha or None,
        dirty_status=dirty,
        lane_commit_count=lane_commit_count,
        lane_merge_commit_count=lane_merge_commit_count,
        cherry=cherry_lines,
        unabsorbed_patches=unabsorbed,
        errors=errors,
    )

    if errors:
        classification = "needs-owner-review"
    elif dirty:
        classification = "still-dirty"
    elif is_ancestor(main_repo, head_sha, target_sha) is True:
        classification = "exact-merged"
    elif tree(main_repo, head_sha) == tree(main_repo, target_sha):
        classification = "tree-equivalent"
    elif lane_merge_commit_count:
        classification = "needs-owner-review"
    elif lane_commit_count and not unabsorbed:
        classification = "patch-equivalent"
    elif is_ancestor(main_repo, target_sha, head_sha) is True:
        classification = "ahead-not-absorbed"
    else:
        classification = "needs-owner-review"
    item["classification"] = classification
    return item


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base-ref")
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("worktrees", nargs="+")
    args = parser.parse_args(argv)

    repo, repo_error = repo_root(Path(args.repo))
    if repo_error:
        report = {"repo": str(repo), "results": [], "errors": [repo_error], "ok": False}
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    registered_roots, registered_error = registered_worktrees(repo)
    if registered_error:
        report = {"repo": str(repo), "results": [], "errors": [registered_error], "ok": False}
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    results = [audit_one(repo, Path(path), args.base_ref, args.target_ref, registered_roots) for path in args.worktrees]
    ok = all(item["classification"] in SAFE_CLASSIFICATIONS for item in results)
    print(json.dumps({"repo": str(repo), "results": results, "errors": [], "ok": ok}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
