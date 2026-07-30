#!/usr/bin/env python3
"""Register, checkpoint, inspect, and safely close task-owned Git worktrees."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import socket
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

try:
    from scripts import worktree_absorption_audit, worktree_fleet_audit
except ModuleNotFoundError:
    import worktree_absorption_audit
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
    prune_orphaned_integration_overlaps(payload)
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


def prune_orphaned_integration_overlaps(payload: dict[str, Any]) -> None:
    """Drop cached overlap evidence once the referenced ACTIVE receipt is gone."""
    active_worktrees = {
        item["worktree"]
        for item in payload["entries"]
        if item.get("status") == "ACTIVE"
    }
    for item in payload["entries"]:
        overlaps = item.get("integration_overlaps", [])
        if not isinstance(overlaps, list):
            overlaps = []
        item["integration_overlaps"] = [
            overlap
            for overlap in overlaps
            if isinstance(overlap, dict)
            and overlap.get("worktree") in active_worktrees
            and overlap.get("worktree") != item.get("worktree")
        ]


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
    root, lane = resolve_repo(worktree, repo_root)
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
                repo_root=str(root),
                status="ACTIVE",
                next_action=next_action,
                write_set=desired_paths,
                integration_overlaps=overlaps,
            )
            entry = existing
        else:
            entry = {
                "worktree": lane_key,
                "repo_root": str(root),
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


def transfer_owner(
    ledger_path: Path,
    *,
    repo_root: Path,
    worktree: Path,
    expected_thread_id: str,
    expected_objective_id: str,
    expected_owner: str,
    expected_execution_owner: str,
    new_thread_id: str,
    new_owner: str,
    new_execution_owner: str,
    next_action: str,
    reason: str,
) -> dict[str, Any]:
    """CAS-transfer one ACTIVE receipt without changing its source obligation."""
    _, lane = resolve_repo(worktree, repo_root)
    expected_identity = {
        "thread_id": expected_thread_id,
        "objective_id": expected_objective_id,
        "owner": expected_owner,
        "execution_owner": expected_execution_owner,
    }
    new_identity = {
        "thread_id": new_thread_id,
        "objective_id": expected_objective_id,
        "owner": new_owner,
        "execution_owner": new_execution_owner,
    }
    required = (*expected_identity.values(), *new_identity.values(), next_action, reason)
    if any(not value.strip() for value in required):
        raise LifecycleError("owner transfer identity, next-action, and reason must be non-empty")
    if expected_identity == new_identity:
        raise LifecycleError("owner transfer must change the receipt identity")

    with ledger_lock(ledger_path):
        payload = read_ledger(ledger_path)
        lane_key = str(lane)
        entry = next(
            (item for item in payload["entries"] if item["worktree"] == lane_key),
            None,
        )
        if not entry or entry["status"] != "ACTIVE":
            raise LifecycleError(f"ACTIVE receipt not found for {lane}")
        current_identity = {key: entry.get(key) for key in expected_identity}
        if current_identity != expected_identity:
            raise LifecycleError(f"owner transfer identity changed for {lane}")

        history = entry.setdefault("ownership_transfers", [])
        if not isinstance(history, list):
            raise LifecycleError(f"ownership transfer history is invalid for {lane}")
        transferred_at = now()
        history.append(
            {
                "recorded_at": transferred_at,
                "reason": reason.strip(),
                "from": {
                    **expected_identity,
                    "next_action": entry["next_action"],
                },
                "to": {
                    **new_identity,
                    "next_action": next_action,
                },
            }
        )
        entry.update(
            thread_id=new_thread_id,
            owner=new_owner,
            execution_owner=new_execution_owner,
            next_action=next_action,
        )

        for other in payload["entries"]:
            overlaps = other.get("integration_overlaps", [])
            if not isinstance(overlaps, list):
                continue
            for overlap in overlaps:
                if not isinstance(overlap, dict):
                    continue
                if overlap.get("worktree") != lane_key:
                    continue
                overlap.update(
                    thread_id=new_thread_id,
                    objective_id=expected_objective_id,
                    owner=new_owner,
                )
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


def receipt_repo_root(
    worktree: str,
    receipt: dict[str, Any],
) -> Path | None:
    declared = receipt.get("repo_root")
    declared_root = (
        Path(declared).expanduser().resolve()
        if isinstance(declared, str) and declared.strip()
        else None
    )
    path = Path(worktree)
    try:
        if not path.exists():
            return declared_root
        actual_root, _ = resolve_repo(path)
    except (LifecycleError, worktree_fleet_audit.FleetAuditError, OSError):
        return None
    if declared_root is not None and declared_root != actual_root:
        return None
    return actual_root


def status(
    ledger_path: Path,
    *,
    repo_roots: list[Path] | None = None,
    check_remote: bool = True,
    holders: dict[str, list[dict[str, Any]]] | None = None,
    holder_scan_available: bool | None = None,
) -> dict[str, Any]:
    payload = read_ledger(ledger_path)
    all_receipts = {
        str(Path(item["worktree"]).expanduser().resolve()): item
        for item in payload["entries"]
    }
    roots = [path.expanduser().resolve() for path in repo_roots or []]
    if not roots:
        for worktree, receipt in all_receipts.items():
            root = receipt_repo_root(worktree, receipt)
            if root is not None and root not in roots:
                roots.append(root)
        receipts = all_receipts
    else:
        receipts: dict[str, dict[str, Any]] = {}
        for worktree, receipt in all_receipts.items():
            receipt_root = receipt_repo_root(worktree, receipt)
            if receipt_root is None or receipt_root in roots:
                receipts[worktree] = receipt
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


def shared_index_identity(
    lane: Path,
    holders: list[dict[str, Any]],
) -> tuple[dict[tuple[int, str], dict[str, Any]], list[Path]]:
    expected: dict[tuple[int, str], dict[str, Any]] = {}
    roots: set[Path] = set()
    for holder in holders:
        pid = holder["pid"]
        for index in holder["codegraph_indexes"]:
            path = Path(index["path"]).resolve(strict=False)
            try:
                path.relative_to(lane)
            except ValueError:
                root = path.parent.parent
            else:
                continue
            roots.add(root)
            expected[(pid, str(path))] = {
                "started_at": holder["started_at"],
                "process_command": holder["process_command"],
                "device": index.get("device"),
                "inode": index.get("inode"),
            }
    return expected, sorted(roots)


def assert_shared_index_identity(
    expected: dict[tuple[int, str], dict[str, Any]],
    holders: dict[str, list[dict[str, Any]]],
) -> None:
    observed: dict[tuple[int, str], dict[str, Any]] = {}
    for path_holders in holders.values():
        for holder in path_holders:
            pid = holder.get("pid")
            if not isinstance(pid, int):
                continue
            for index in holder.get("codegraph_indexes", []):
                path = str(Path(str(index.get("path", ""))).resolve(strict=False))
                observed[(pid, path)] = {
                    "started_at": holder.get("started_at"),
                    "process_command": holder.get("process_command"),
                    "device": index.get("device"),
                    "inode": index.get("inode"),
                }
    changed = sorted(key for key, identity in expected.items() if observed.get(key) != identity)
    if changed:
        rendered = ", ".join(f"PID {pid} {path}" for pid, path in changed)
        raise LifecycleError(
            "shared CodeGraph service or non-target index identity changed: " + rendered
        )


def checkpoint_codegraph_index(database: Path) -> tuple[int, int, int]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(database), timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
        if not journal_mode or str(journal_mode[0]).lower() != "wal":
            raise LifecycleError("CodeGraph index is not in WAL mode")
        row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.Error as exc:
        raise LifecycleError(f"CodeGraph index quiescence failed: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
    if (
        not row
        or len(row) != 3
        or any(not isinstance(value, int) for value in row)
        or row[0] != 0
    ):
        raise LifecycleError(f"CodeGraph index checkpoint did not quiesce: {row!r}")
    return row


def detach_shared_codegraph_index(
    root: Path,
    lane: Path,
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
]:
    fresh_holders, available = worktree_fleet_audit.scan_holders([lane])
    if not available:
        raise LifecycleError("fresh holder proof is unavailable for CodeGraph index detach")
    lane_holders = fresh_holders.get(str(lane), [])
    classification = worktree_fleet_audit.classify_cleanup_holders(lane, lane_holders)
    if classification["kind"] != "shared_codegraph_index_only":
        issues = classification["issues"] or ["holder identity changed before detach"]
        raise LifecycleError("CodeGraph index detach is not safe: " + "; ".join(issues))

    expected_indexes, shared_roots = shared_index_identity(lane, lane_holders)
    if not expected_indexes or not shared_roots:
        raise LifecycleError("shared CodeGraph index identity proof is incomplete")

    index_dir = lane / ".codegraph"
    database = index_dir / "codegraph.db"
    if not database.is_file():
        raise LifecycleError("task-owned CodeGraph index is absent")
    common_dir = Path(
        git(
            root,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
    ).resolve()
    if os.stat(index_dir).st_dev != os.stat(common_dir).st_dev:
        raise LifecycleError("CodeGraph index cannot be atomically migrated across filesystems")

    quarantine_root = Path(
        tempfile.mkdtemp(prefix="opl-flow-codegraph-detach-", dir=common_dir)
    )
    quarantine_index = quarantine_root / ".codegraph"
    moved = False
    try:
        os.replace(index_dir, quarantine_index)
        moved = True
        if index_dir.exists():
            raise LifecycleError("target CodeGraph index path reappeared after migration")

        checkpoint = checkpoint_codegraph_index(quarantine_index / "codegraph.db")
        scan_paths = [lane, *shared_roots]
        post_holders, post_available = worktree_fleet_audit.scan_holders(scan_paths)
        if not post_available:
            raise LifecycleError("post-migration holder proof is unavailable")
        if post_holders.get(str(lane)):
            raise LifecycleError("target worktree still has holders after index migration")
        assert_shared_index_identity(expected_indexes, post_holders)
        if index_dir.exists():
            raise LifecycleError("target CodeGraph index was recreated after quiescence")

        final_holders, final_available = worktree_fleet_audit.scan_holders(scan_paths)
        if not final_available:
            raise LifecycleError(
                "final holder proof is unavailable while the index backup is preserved"
            )
        if final_holders.get(str(lane)):
            raise LifecycleError("target worktree regained a holder after index detach")
        assert_shared_index_identity(expected_indexes, final_holders)
        if index_dir.exists() or not quarantine_index.is_dir():
            raise LifecycleError("CodeGraph index backup state changed before close")
        return (
            {
                "classification": classification["kind"],
                "protocol": "atomic_migrate_wal_checkpoint_unlink",
                "pids": classification["pids"],
                "wal_checkpoint": list(checkpoint),
                "target_index_absent": True,
                "target_holders_absent": True,
                "quarantine_absent": False,
                "quarantine_preserved_until_close": True,
                "cleanup_owner": "worktree_lifecycle.close",
                "shared_processes_preserved": True,
                "external_indexes_preserved": True,
            },
            final_holders,
            {
                "quarantine_root": quarantine_root,
                "quarantine_index": quarantine_index,
                "target_index": index_dir,
                "lane": lane,
                "scan_paths": scan_paths,
                "expected_indexes": expected_indexes,
            },
        )
    except Exception:
        if moved and quarantine_index.exists():
            if index_dir.exists():
                raise LifecycleError(
                    f"CodeGraph index detach failed and target path reappeared; "
                    f"preserved migrated index at {quarantine_index}"
                )
            os.replace(quarantine_index, index_dir)
        if quarantine_root.exists():
            shutil.rmtree(quarantine_root)
        raise


def prove_detached_codegraph_index(
    cleanup: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    holders, available = worktree_fleet_audit.scan_holders(cleanup["scan_paths"])
    if not available:
        raise LifecycleError(
            "final close-owned holder proof is unavailable while the index backup "
            "is preserved"
        )
    if holders.get(str(cleanup["lane"])):
        raise LifecycleError("target worktree regained a holder before physical removal")
    assert_shared_index_identity(cleanup["expected_indexes"], holders)
    if cleanup["target_index"].exists() or not cleanup["quarantine_index"].is_dir():
        raise LifecycleError("CodeGraph index backup state changed before physical removal")
    return holders


def restore_detached_codegraph_index(cleanup: dict[str, Any]) -> None:
    quarantine_root = cleanup["quarantine_root"]
    quarantine_index = cleanup["quarantine_index"]
    target_index = cleanup["target_index"]
    if target_index.exists():
        raise LifecycleError(
            f"cannot restore CodeGraph index because target path reappeared; "
            f"preserved backup at {quarantine_index}"
        )
    if not quarantine_index.is_dir():
        raise LifecycleError("CodeGraph index backup is unavailable for rollback")
    os.replace(quarantine_index, target_index)
    if quarantine_root.exists():
        quarantine_root.rmdir()


def finalize_detached_codegraph_index(cleanup: dict[str, Any]) -> None:
    quarantine_root = cleanup["quarantine_root"]
    if not quarantine_root.is_dir():
        raise LifecycleError("CodeGraph index quarantine disappeared before close cleanup")
    shutil.rmtree(quarantine_root)
    if quarantine_root.exists():
        raise LifecycleError(
            f"CodeGraph index quarantine cleanup remains owned by close: {quarantine_root}"
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
        index_detach = None
        index_cleanup: dict[str, Any] | None = None
        lane_removed = False
        try:
            if (
                lane_result["action"] == "index_detach_ready"
                and not lane_result["blocking_issues"]
            ):
                (
                    index_detach,
                    post_detach_holders,
                    index_cleanup,
                ) = detach_shared_codegraph_index(root, lane)
                audit = worktree_fleet_audit.audit_fleet(
                    [root],
                    receipts,
                    target_override=target,
                    check_remote=True,
                    holders=post_detach_holders,
                    holder_scan_available=True,
                )
                repo = audit["repos"][0]
                lane_result = next(
                    item for item in repo["worktrees"] if item["worktree"] == str(lane)
                )
            if lane_result["action"] != "cleanup_ready" or lane_result["blocking_issues"]:
                issues = lane_result["issues"] or [lane_result["action"]]
                raise LifecycleError("worktree is not cleanup-ready: " + "; ".join(issues))

            branch = lane_result["branch"]
            head = lane_result["head"]
            tree = git(lane, "rev-parse", "HEAD^{tree}").stdout.strip()
            target_remote, target_branch = worktree_fleet_audit.split_remote_target(
                repo["target"]
            )
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
            if index_cleanup:
                final_holders = prove_detached_codegraph_index(index_cleanup)
                final_audit = worktree_fleet_audit.audit_fleet(
                    [root],
                    receipts,
                    target_override=target,
                    check_remote=True,
                    holders=final_holders,
                    holder_scan_available=True,
                )
                final_lane = next(
                    item
                    for item in final_audit["repos"][0]["worktrees"]
                    if item["worktree"] == str(lane)
                )
                if (
                    final_lane["action"] != "cleanup_ready"
                    or final_lane["blocking_issues"]
                ):
                    raise LifecycleError(
                        "worktree lost cleanup readiness before physical removal"
                    )
                index_detach["final_close_holder_proof"] = True
            git(root, "worktree", "remove", str(lane))
            lane_removed = True
            if index_cleanup:
                finalize_detached_codegraph_index(index_cleanup)
                index_detach["quarantine_absent"] = True
            git(root, "branch", "-D", branch)
            payload["entries"] = [
                item for item in payload["entries"] if item["worktree"] != str(lane)
            ]
            write_ledger(ledger_path, payload)
        except Exception as exc:
            if index_cleanup and not lane_removed:
                restore_detached_codegraph_index(index_cleanup)
            elif (
                index_cleanup
                and lane_removed
                and index_cleanup["quarantine_root"].exists()
            ):
                raise LifecycleError(
                    "worktree was removed but CodeGraph quarantine cleanup remains "
                    f"owned by this close: {index_cleanup['quarantine_root']}"
                ) from exc
            raise
    return {
        "worktree": str(lane),
        "branch": branch,
        "classification": lane_result["classification"],
        "remote_branch_deleted": bool(remote_head),
        "index_detach": index_detach,
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
        recovery_absorption = "not_applicable" if recovery is None else "unverified"
        recovery_absorption_proof: dict[str, Any] | None = None
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
            if absorbed.returncode == 0:
                recovery_absorbed = True
                recovery_absorption = "exact_merged"
                recovery_absorption_proof = {
                    "classification": recovery_absorption,
                    "lane_head": recovery_commit,
                    "target_head": target_head,
                }
            elif absorbed.returncode == 1:
                try:
                    absorption = worktree_absorption_audit.classify_commits(
                        root,
                        recovery_commit,
                        target,
                    )
                except worktree_absorption_audit.AuditError as exc:
                    raise LifecycleError(
                        "stale receipt recovery patch equivalence cannot be verified"
                    ) from exc
                strict_patch_equivalent = (
                    absorption.get("target_head") == target_head
                    and absorption.get("lane_head") == recovery_commit
                    and absorption.get("classification") == "patch_equivalent"
                    and absorption.get("cleanup_allowed") is True
                    and absorption.get("lane_commit_count", 0) > 0
                    and absorption.get("merge_commit_count") == 0
                    and absorption.get("equivalent_commit_count")
                    == absorption.get("lane_commit_count")
                    and absorption.get("unabsorbed_commit_count") == 0
                )
                if not strict_patch_equivalent:
                    raise LifecycleError(
                        "stale receipt recovery commit is not absorbed by the canonical target "
                        f"(classification={absorption.get('classification', 'owner_review')})"
                    )
                recovery_absorbed = True
                recovery_absorption = "patch_equivalent"
                recovery_absorption_proof = {
                    key: absorption[key]
                    for key in (
                        "classification",
                        "lane_head",
                        "target_head",
                        "merge_base",
                        "lane_commit_count",
                        "merge_commit_count",
                        "equivalent_commit_count",
                        "unabsorbed_commit_count",
                    )
                }
            else:
                raise LifecycleError(
                    "stale receipt recovery ancestry cannot be verified"
                )

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
        "recovery_absorption": recovery_absorption,
        "recovery_absorption_proof": recovery_absorption_proof,
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

    transfer_parser = commands.add_parser("transfer-owner")
    transfer_parser.add_argument("--repo-root", required=True, type=Path)
    transfer_parser.add_argument("--worktree", required=True, type=Path)
    transfer_parser.add_argument("--expected-thread-id", required=True)
    transfer_parser.add_argument("--expected-objective-id", required=True)
    transfer_parser.add_argument("--expected-owner", required=True)
    transfer_parser.add_argument("--expected-execution-owner", required=True)
    transfer_parser.add_argument("--new-thread-id", required=True)
    transfer_parser.add_argument("--new-owner", required=True)
    transfer_parser.add_argument("--new-execution-owner")
    transfer_parser.add_argument("--next-action", required=True)
    transfer_parser.add_argument("--reason", required=True)

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
        elif args.command == "transfer-owner":
            result = transfer_owner(
                ledger_path,
                repo_root=args.repo_root,
                worktree=args.worktree,
                expected_thread_id=args.expected_thread_id,
                expected_objective_id=args.expected_objective_id,
                expected_owner=args.expected_owner,
                expected_execution_owner=args.expected_execution_owner,
                new_thread_id=args.new_thread_id,
                new_owner=args.new_owner,
                new_execution_owner=args.new_execution_owner or args.new_owner,
                next_action=args.next_action,
                reason=args.reason,
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
