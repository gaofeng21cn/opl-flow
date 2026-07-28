#!/usr/bin/env python3
"""Register, checkpoint, inspect, and safely close task-owned Git worktrees."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import socket
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

try:
    from scripts import worktree_fleet_audit
except ModuleNotFoundError:
    import worktree_fleet_audit


SCHEMA = "opl_flow_worktree_ownership_ledger.v1"
DEFAULT_LEDGER = Path("~/.local/state/opl-flow/worktree-ownership-ledger.json")


class LifecycleError(RuntimeError):
    """Raised when a lifecycle mutation cannot be proven safe."""


git = worktree_fleet_audit.git


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def empty_ledger() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "machine": socket.gethostname().split(".", 1)[0],
        "recorded_at": now(),
        "entries": [],
    }


def read_ledger(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        return empty_ledger()
    worktree_fleet_audit.load_ledger(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"cannot read ownership ledger {path}: {exc}") from exc


def write_ledger(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["recorded_at"] = now()
    payload["entries"] = sorted(payload["entries"], key=lambda item: item["worktree"])
    data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@contextmanager
def ledger_lock(path: Path) -> Iterator[None]:
    lock_path = path.expanduser().resolve().with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def worktree_records(repo_root: Path) -> list[dict[str, str | bool]]:
    return worktree_fleet_audit.list_worktrees(repo_root.expanduser().resolve())


def resolve_repo(worktree: Path, repo_root: Path | None = None) -> tuple[Path, Path]:
    worktree = worktree.expanduser().resolve()
    top = Path(git(worktree, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != worktree:
        raise LifecycleError(f"worktree must be its Git top level: {worktree}")
    records = worktree_records(repo_root or worktree)
    registered = [Path(str(item["worktree"])).resolve() for item in records]
    if worktree not in registered:
        raise LifecycleError(f"worktree is not registered: {worktree}")
    canonical = registered[0]
    if worktree == canonical:
        raise LifecycleError("canonical checkout cannot be registered as a task worktree")
    return canonical, worktree


def normalize_write_set(values: list[str]) -> list[str]:
    normalized: set[str] = set()
    for value in values:
        path = PurePosixPath(value)
        if not value.strip() or path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
            raise LifecycleError(f"write-set paths must be repository-relative: {value}")
        normalized.add(str(path))
    if not normalized:
        raise LifecycleError("write-set must contain at least one path")
    return sorted(normalized)


def common_dir(worktree: Path) -> Path:
    raw = git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    return Path(raw).resolve()


def integration_overlaps(
    entries: list[dict[str, Any]],
    lane: Path,
    desired_paths: list[str],
) -> list[dict[str, Any]]:
    """Report overlapping active worksets without turning them into a lock."""
    overlaps: list[dict[str, Any]] = []
    lane_common_dir = common_dir(lane)
    for item in entries:
        other = Path(item["worktree"]).expanduser().resolve()
        if other == lane or item["status"] != "ACTIVE" or not other.exists():
            continue
        if common_dir(other) != lane_common_dir:
            continue
        paths = sorted(set(item["write_set"]) & set(desired_paths))
        if paths:
            overlaps.append(
                {
                    "worktree": str(other),
                    "thread_id": item["thread_id"],
                    "objective_id": item["objective_id"],
                    "owner": item["owner"],
                    "paths": paths,
                }
            )
    return sorted(overlaps, key=lambda item: (item["worktree"], item["owner"]))


def register(
    ledger_path: Path,
    *,
    repo_root: Path,
    worktree: Path,
    thread_id: str,
    objective_id: str,
    owner: str,
    execution_owner: str,
    next_action: str,
    write_set: list[str],
) -> dict[str, Any]:
    _, lane = resolve_repo(worktree, repo_root)
    desired_paths = normalize_write_set(write_set)
    identity = {
        "thread_id": thread_id,
        "objective_id": objective_id,
        "owner": owner,
        "execution_owner": execution_owner,
    }
    if any(not value.strip() for value in (*identity.values(), next_action)):
        raise LifecycleError("owner identity and next-action must be non-empty")

    with ledger_lock(ledger_path):
        payload = read_ledger(ledger_path)
        lane_key = str(lane)
        existing = next(
            (item for item in payload["entries"] if item["worktree"] == lane_key),
            None,
        )
        overlaps = integration_overlaps(payload["entries"], lane, desired_paths)
        if existing:
            if any(existing[key] != value for key, value in identity.items()):
                raise LifecycleError(f"worktree already belongs to another receipt: {lane}")
            existing.update(
                status="ACTIVE",
                next_action=next_action,
                write_set=desired_paths,
                integration_overlaps=overlaps,
            )
            entry = existing
        else:
            entry = {
                "worktree": lane_key,
                **identity,
                "status": "ACTIVE",
                "next_action": next_action,
                "write_set": desired_paths,
                "integration_overlaps": overlaps,
                "remote_recovery": None,
            }
            payload["entries"].append(entry)
        write_ledger(ledger_path, payload)
    return entry


def checkpoint(
    ledger_path: Path,
    *,
    worktree: Path,
    remote: str,
    next_action: str | None = None,
) -> dict[str, Any]:
    root, lane = resolve_repo(worktree)
    dirty = git(lane, "status", "--porcelain=v1", "--untracked-files=all").stdout.strip()
    if dirty:
        raise LifecycleError("checkpoint requires a clean worktree")
    branch = git(lane, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    if not branch:
        raise LifecycleError("checkpoint requires a named task branch")
    target_remote, _ = worktree_fleet_audit.split_remote_target(
        worktree_fleet_audit.upstream_target(root, None)
    )
    if remote != target_remote:
        raise LifecycleError(f"checkpoint remote must be canonical upstream {target_remote}")

    with ledger_lock(ledger_path):
        payload = read_ledger(ledger_path)
        entry = next(
            (item for item in payload["entries"] if item["worktree"] == str(lane)),
            None,
        )
        if not entry or entry["status"] != "ACTIVE":
            raise LifecycleError(f"ACTIVE receipt not found for {lane}")
        git(lane, "push", "--set-upstream", remote, f"HEAD:refs/heads/{branch}")
        commit = git(lane, "rev-parse", "HEAD^{commit}").stdout.strip()
        tree = git(lane, "rev-parse", "HEAD^{tree}").stdout.strip()
        wire = git(lane, "ls-remote", "--heads", remote, f"refs/heads/{branch}").stdout.strip()
        if not wire or wire.split()[0] != commit:
            raise LifecycleError("remote checkpoint readback does not match local HEAD")
        entry["remote_recovery"] = {"branch": branch, "commit": commit, "tree": tree}
        if next_action:
            entry["next_action"] = next_action
        write_ledger(ledger_path, payload)
    return entry["remote_recovery"]


def status(
    ledger_path: Path,
    *,
    repo_roots: list[Path] | None = None,
    check_remote: bool = True,
    holders: dict[str, list[dict[str, Any]]] | None = None,
    holder_scan_available: bool | None = None,
) -> dict[str, Any]:
    payload = read_ledger(ledger_path)
    receipts = {
        str(Path(item["worktree"]).expanduser().resolve()): item
        for item in payload["entries"]
    }
    roots = [path.expanduser().resolve() for path in repo_roots or []]
    if not roots:
        for worktree in receipts:
            path = Path(worktree)
            if path.exists():
                root, _ = resolve_repo(path)
                if root not in roots:
                    roots.append(root)
    if not roots:
        return {
            "schema": worktree_fleet_audit.SCHEMA,
            "ok": not receipts,
            "remote_checked": check_remote,
            "holder_scan_available": False,
            "stale_receipts": sorted(receipts),
            "repos": [],
        }
    return worktree_fleet_audit.audit_fleet(
        roots,
        receipts,
        check_remote=check_remote,
        holders=holders,
        holder_scan_available=holder_scan_available,
    )


def close(
    ledger_path: Path,
    *,
    worktree: Path,
    target: str | None = None,
    holders: dict[str, list[dict[str, Any]]] | None = None,
    holder_scan_available: bool | None = None,
) -> dict[str, Any]:
    root, lane = resolve_repo(worktree)
    with ledger_lock(ledger_path):
        payload = read_ledger(ledger_path)
        entry = next(
            (item for item in payload["entries"] if item["worktree"] == str(lane)),
            None,
        )
        if not entry or entry["status"] != "ACTIVE":
            raise LifecycleError(f"ACTIVE receipt not found for {lane}")
        repo_paths = {
            str(Path(item["worktree"]).resolve())
            for item in worktree_records(root)
        }
        receipts = {
            item["worktree"]: {**item, "status": "SAFE_TO_ARCHIVE"}
            for item in payload["entries"]
            if item["worktree"] in repo_paths
        }
        audit = worktree_fleet_audit.audit_fleet(
            [root],
            receipts,
            target_override=target,
            check_remote=True,
            holders=holders,
            holder_scan_available=holder_scan_available,
        )
        repo = audit["repos"][0]
        lane_result = next(
            item for item in repo["worktrees"] if item["worktree"] == str(lane)
        )
        currentness = repo["currentness"]
        if not currentness["wire_head"] or currentness["target_head"] != currentness["wire_head"]:
            raise LifecycleError("canonical target must be checked and match its wire")
        if lane_result["action"] != "cleanup_ready" or lane_result["blocking_issues"]:
            issues = lane_result["issues"] or [lane_result["action"]]
            raise LifecycleError("worktree is not cleanup-ready: " + "; ".join(issues))

        branch = lane_result["branch"]
        head = lane_result["head"]
        tree = git(lane, "rev-parse", "HEAD^{tree}").stdout.strip()
        target_remote, target_branch = worktree_fleet_audit.split_remote_target(repo["target"])
        if not branch or branch == target_branch:
            raise LifecycleError("refusing to close a detached or canonical branch")
        recovery = entry["remote_recovery"]
        if recovery and recovery != {"branch": branch, "commit": head, "tree": tree}:
            raise LifecycleError("remote recovery receipt does not match current worktree")
        remote_head = lane_result["remote_branch_head"]
        if remote_head and remote_head != head:
            raise LifecycleError("remote task branch does not match current worktree")

        if remote_head:
            git(
                root,
                "push",
                f"--force-with-lease=refs/heads/{branch}:{head}",
                target_remote,
                "--delete",
                branch,
            )
        git(root, "worktree", "remove", str(lane))
        git(root, "branch", "-D", branch)
        payload["entries"] = [
            item for item in payload["entries"] if item["worktree"] != str(lane)
        ]
        write_ledger(ledger_path, payload)
    return {
        "worktree": str(lane),
        "branch": branch,
        "classification": lane_result["classification"],
        "remote_branch_deleted": bool(remote_head),
        "closed": True,
    }


def git_admin_matches(repo_root: Path, lane: Path) -> list[str]:
    common = Path(
        git(
            repo_root,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
    ).resolve()
    admin_root = common / "worktrees"
    if not admin_root.is_dir():
        return []

    expected_gitdir = (lane / ".git").resolve()
    matches: list[str] = []
    for admin in admin_root.iterdir():
        if not admin.is_dir():
            continue
        gitdir = admin / "gitdir"
        points_to_lane = False
        if gitdir.is_file() and not gitdir.is_symlink():
            raw = gitdir.read_text(encoding="utf-8").strip()
            if raw:
                candidate = Path(raw).expanduser()
                if not candidate.is_absolute():
                    candidate = admin / candidate
                points_to_lane = candidate.resolve() == expected_gitdir
        if points_to_lane:
            matches.append(str(admin))
    return sorted(matches)


def git_lock_paths(repo_root: Path) -> list[str]:
    common = Path(
        git(
            repo_root,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
    ).resolve()
    return sorted(str(path) for path in common.rglob("*.lock") if path.exists())


def configured_remotes(repo_root: Path) -> list[str]:
    return sorted(
        remote
        for remote in git(repo_root, "remote").stdout.splitlines()
        if remote.strip()
    )


def close_stale(
    ledger_path: Path,
    *,
    repo_root: Path,
    worktree: Path,
    thread_id: str,
    objective_id: str,
    owner: str,
    branch: str,
    holders: dict[str, list[dict[str, Any]]] | None = None,
    holder_scan_available: bool | None = None,
) -> dict[str, Any]:
    """Remove one exact ACTIVE receipt after every task-owned Git surface is absent."""
    root = repo_root.expanduser().resolve()
    top = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != root:
        raise LifecycleError(f"repo root must be its Git top level: {root}")

    lane_input = Path(os.path.abspath(worktree.expanduser()))
    if os.path.lexists(lane_input):
        raise LifecycleError("stale close requires the worktree path to be absent")
    lane = lane_input.resolve()
    if lane == root:
        raise LifecycleError("canonical checkout cannot be stale-closed")
    if git(root, "check-ref-format", "--branch", branch, check=False).returncode != 0:
        raise LifecycleError(f"invalid task branch: {branch}")

    target = worktree_fleet_audit.upstream_target(root, None)
    target_remote, target_branch = worktree_fleet_audit.split_remote_target(target)
    if branch == target_branch:
        raise LifecycleError("refusing to stale-close the canonical branch")

    lane_key = str(lane)
    if holders is None:
        holders, detected = worktree_fleet_audit.scan_holders([lane])
        if holder_scan_available is None:
            holder_scan_available = detected
    if holder_scan_available is not True:
        raise LifecycleError("stale close requires an available holder scan")

    with ledger_lock(ledger_path):
        payload = read_ledger(ledger_path)
        matches = [item for item in payload["entries"] if item["worktree"] == lane_key]
        if len(matches) != 1 or matches[0]["status"] != "ACTIVE":
            raise LifecycleError(f"unique ACTIVE receipt not found for {lane}")
        entry = matches[0]
        expected_identity = {
            "thread_id": thread_id,
            "objective_id": objective_id,
            "owner": owner,
        }
        drift = [
            key
            for key, expected in expected_identity.items()
            if entry.get(key) != expected
        ]
        if drift:
            raise LifecycleError(
                "stale receipt identity does not match: " + ", ".join(sorted(drift))
            )

        recovery = entry.get("remote_recovery")
        if recovery is not None:
            if not isinstance(recovery, dict) or recovery.get("branch") != branch:
                raise LifecycleError("stale receipt recovery branch does not match")
        if os.path.lexists(lane_input) or os.path.lexists(lane / ".git"):
            raise LifecycleError("stale close requires the worktree path and .git file to be absent")

        registered = {
            str(Path(str(item["worktree"])).resolve())
            for item in worktree_records(root)
        }
        if lane_key in registered:
            raise LifecycleError("stale close requires the worktree registration to be absent")

        admin_matches = git_admin_matches(root, lane)
        if admin_matches:
            raise LifecycleError(
                "stale close requires the worktree gitdir administration to be absent: "
                + ", ".join(admin_matches)
            )

        local_ref = f"refs/heads/{branch}"
        local_ref_check = git(
            root,
            "show-ref",
            "--verify",
            "--quiet",
            local_ref,
            check=False,
        )
        if local_ref_check.returncode == 0:
            raise LifecycleError(f"stale close requires local task ref to be absent: {local_ref}")
        if local_ref_check.returncode != 1:
            raise LifecycleError(f"cannot verify local task ref absence: {local_ref}")
        for remote in configured_remotes(root):
            tracking_ref = f"refs/remotes/{remote}/{branch}"
            tracking_ref_check = git(
                root,
                "show-ref",
                "--verify",
                "--quiet",
                tracking_ref,
                check=False,
            )
            if tracking_ref_check.returncode == 0:
                raise LifecycleError(
                    f"stale close requires tracking task ref to be absent: {tracking_ref}"
                )
            if tracking_ref_check.returncode != 1:
                raise LifecycleError(
                    f"cannot verify tracking task ref absence: {tracking_ref}"
                )
            wire = git(
                root,
                "ls-remote",
                "--heads",
                remote,
                local_ref,
            ).stdout.strip()
            if wire:
                raise LifecycleError(
                    f"stale close requires wire task ref to be absent on {remote}: {local_ref}"
                )

        branch_config_check = git(
            root,
            "config",
            "--local",
            "--get-regexp",
            rf"^branch\.{re.escape(branch)}\.",
            check=False,
        )
        if branch_config_check.returncode not in (0, 1):
            raise LifecycleError("cannot verify task branch config absence")
        branch_config = branch_config_check.stdout.strip()
        if branch_config:
            raise LifecycleError("stale close requires task branch config to be absent")

        path_holders = holders.get(lane_key, [])
        if path_holders:
            raise LifecycleError(f"stale close requires holder0: {path_holders}")
        locks = git_lock_paths(root)
        if locks:
            raise LifecycleError("stale close requires Git locks0: " + ", ".join(locks))

        target_head = git(root, "rev-parse", f"{target}^{{commit}}").stdout.strip()
        target_wire = git(
            root,
            "ls-remote",
            "--heads",
            target_remote,
            f"refs/heads/{target_branch}",
        ).stdout.strip()
        if not target_wire or target_wire.split()[0] != target_head:
            raise LifecycleError("canonical target must be checked and match its wire")

        recovery_absorbed = recovery is None
        if recovery is not None:
            recovery_commit = recovery.get("commit")
            recovery_tree = recovery.get("tree")
            if not isinstance(recovery_commit, str) or not isinstance(recovery_tree, str):
                raise LifecycleError("stale receipt recovery commit and tree must be present")
            recorded_tree = git(
                root,
                "rev-parse",
                "--verify",
                f"{recovery_commit}^{{tree}}",
                check=False,
            )
            if recorded_tree.returncode != 0 or recorded_tree.stdout.strip() != recovery_tree:
                raise LifecycleError(
                    "stale receipt recovery commit/tree cannot be verified locally"
                )
            absorbed = git(
                root,
                "merge-base",
                "--is-ancestor",
                recovery_commit,
                target_head,
                check=False,
            )
            if absorbed.returncode != 0:
                raise LifecycleError(
                    "stale receipt recovery commit is not absorbed by the canonical target"
                )
            recovery_absorbed = True

        payload["entries"] = [
            item for item in payload["entries"] if item["worktree"] != lane_key
        ]
        write_ledger(ledger_path, payload)
        remaining = [
            item
            for item in read_ledger(ledger_path)["entries"]
            if item["worktree"] == lane_key
        ]
        if remaining:
            raise LifecycleError("stale lifecycle receipt remained after close")

    return {
        "schema": "opl_flow_worktree_stale_close_receipt.v1",
        "worktree": lane_key,
        "branch": branch,
        "thread_id": thread_id,
        "objective_id": objective_id,
        "owner": owner,
        "classification": "stale_receipt_only",
        "assertions": {
            "path_absent": True,
            "registration_absent": True,
            "gitdir_absent": True,
            "local_ref_absent": True,
            "tracking_ref_absent": True,
            "wire_ref_absent": True,
            "branch_config_absent": True,
            "holders_absent": True,
            "git_locks_absent": True,
            "canonical_target_matches_wire": True,
            "recovery_absence_or_absorption_proven": recovery_absorbed,
        },
        "remaining": remaining,
        "closed": True,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    commands = root.add_subparsers(dest="command", required=True)

    register_parser = commands.add_parser("register")
    register_parser.add_argument("--repo-root", required=True, type=Path)
    register_parser.add_argument("--worktree", required=True, type=Path)
    register_parser.add_argument("--thread-id", required=True)
    register_parser.add_argument("--objective-id", required=True)
    register_parser.add_argument("--owner", required=True)
    register_parser.add_argument("--execution-owner")
    register_parser.add_argument("--next-action", required=True)
    register_parser.add_argument("--write-set", action="append", required=True)

    checkpoint_parser = commands.add_parser("checkpoint")
    checkpoint_parser.add_argument("--worktree", required=True, type=Path)
    checkpoint_parser.add_argument("--remote", default="origin")
    checkpoint_parser.add_argument("--next-action")

    status_parser = commands.add_parser("status")
    status_parser.add_argument("--repo-root", action="append", type=Path)
    status_parser.add_argument("--offline", action="store_true")
    status_parser.add_argument("--skip-holder-scan", action="store_true")

    close_parser = commands.add_parser("close")
    close_parser.add_argument("--worktree", required=True, type=Path)
    close_parser.add_argument(
        "--target",
        help="Canonical remote tracking target used to prove task-worktree absorption.",
    )

    close_stale_parser = commands.add_parser("close-stale")
    close_stale_parser.add_argument("--repo-root", required=True, type=Path)
    close_stale_parser.add_argument("--worktree", required=True, type=Path)
    close_stale_parser.add_argument("--thread-id", required=True)
    close_stale_parser.add_argument("--objective-id", required=True)
    close_stale_parser.add_argument("--owner", required=True)
    close_stale_parser.add_argument("--branch", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    ledger_path = args.ledger.expanduser().resolve()
    try:
        if args.command == "register":
            result = register(
                ledger_path,
                repo_root=args.repo_root,
                worktree=args.worktree,
                thread_id=args.thread_id,
                objective_id=args.objective_id,
                owner=args.owner,
                execution_owner=args.execution_owner or args.owner,
                next_action=args.next_action,
                write_set=args.write_set,
            )
        elif args.command == "checkpoint":
            result = checkpoint(
                ledger_path,
                worktree=args.worktree,
                remote=args.remote,
                next_action=args.next_action,
            )
        elif args.command == "status":
            result = status(
                ledger_path,
                repo_roots=args.repo_root,
                check_remote=not args.offline,
                holders={} if args.skip_holder_scan else None,
                holder_scan_available=False if args.skip_holder_scan else None,
            )
        elif args.command == "close":
            result = close(ledger_path, worktree=args.worktree, target=args.target)
        else:
            result = close_stale(
                ledger_path,
                repo_root=args.repo_root,
                worktree=args.worktree,
                thread_id=args.thread_id,
                objective_id=args.objective_id,
                owner=args.owner,
                branch=args.branch,
            )
    except (LifecycleError, worktree_fleet_audit.FleetAuditError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
