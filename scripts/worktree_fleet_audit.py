#!/usr/bin/env python3
"""Audit worktree ownership, absorption, recovery, and canonical currentness."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from scripts.worktree_absorption_audit import AuditError, audit as absorption_audit
except ModuleNotFoundError:
    from worktree_absorption_audit import AuditError, audit as absorption_audit


SCHEMA = "opl_flow_worktree_fleet_audit.v1"
LEDGER_SCHEMA = "opl_flow_worktree_ownership_ledger.v1"
ACTIVE = "ACTIVE"
ARCHIVE_READY = "SAFE_TO_ARCHIVE"
REMOTE_PROBE_TIMEOUT_SECONDS = 10.0
REMOTE_PROBE_BACKOFF_SECONDS = (0.25, 0.75)
TRANSIENT_REMOTE_PROBE_ERRORS = (
    "could not resolve host",
    "connection reset by peer",
    "connection timed out",
    "failed to connect",
    "gnutls_handshake() failed",
    "network is unreachable",
    "operation timed out",
    "recv failure",
    "ssl_error_syscall",
    "stream error in the http/2 framing layer",
    "temporary failure in name resolution",
    "the remote end hung up unexpectedly",
    "tls handshake timeout",
)
CODEGRAPH_INDEX_FILENAMES = {
    "codegraph.db",
    "codegraph.db-wal",
    "codegraph.db-shm",
}


class FleetAuditError(RuntimeError):
    """Raised when fleet identity or ownership cannot be inspected safely."""


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        detail = f" timed out after {timeout:g}s" if timeout is not None else " timed out"
        raise FleetAuditError(f"{' '.join(args)}{detail}") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise FleetAuditError(f"{' '.join(args)} failed: {detail}")
    return result


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    if not args or args[0] != "ls-remote":
        return run(command, cwd=cwd, check=check)

    attempts = len(REMOTE_PROBE_BACKOFF_SECONDS) + 1
    for attempt in range(attempts):
        try:
            result = run(
                command,
                cwd=cwd,
                check=False,
                timeout=REMOTE_PROBE_TIMEOUT_SECONDS,
            )
        except FleetAuditError as exc:
            error = str(exc)
            result = None
        else:
            if result.returncode == 0:
                return result
            error = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"

        retryable = "timed out after" in error.lower() or any(
            marker in error.lower() for marker in TRANSIENT_REMOTE_PROBE_ERRORS
        )
        if not retryable or attempt == attempts - 1:
            if result is not None and not check:
                return result
            raise FleetAuditError(f"{' '.join(command)} failed: {error}")
        time.sleep(REMOTE_PROBE_BACKOFF_SECONDS[attempt])

    raise AssertionError("remote probe retry loop exhausted without a result")


def load_ledger(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FleetAuditError(f"cannot read ownership ledger {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != LEDGER_SCHEMA:
        raise FleetAuditError(f"ownership ledger must use {LEDGER_SCHEMA}")
    if not isinstance(payload.get("machine"), str) or not payload["machine"].strip():
        raise FleetAuditError("ownership ledger machine is required")
    if not isinstance(payload.get("recorded_at"), str) or not payload["recorded_at"].strip():
        raise FleetAuditError("ownership ledger recorded_at is required")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise FleetAuditError("ownership ledger entries must be a list")

    indexed: dict[str, dict[str, Any]] = {}
    required_strings = (
        "worktree",
        "thread_id",
        "objective_id",
        "owner",
        "execution_owner",
        "status",
        "next_action",
    )
    for entry in entries:
        if not isinstance(entry, dict):
            raise FleetAuditError("ownership ledger entries must be objects")
        for field in required_strings:
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise FleetAuditError(f"ownership ledger entry requires non-empty {field}")
        if entry["status"] not in {ACTIVE, ARCHIVE_READY}:
            raise FleetAuditError(f"unsupported worktree status: {entry['status']}")
        write_set = entry.get("write_set")
        if not isinstance(write_set, list) or any(
            not isinstance(item, str) or not item.strip() for item in write_set
        ):
            raise FleetAuditError("ownership ledger write_set must contain non-empty strings")
        worktree = str(Path(entry["worktree"]).expanduser().resolve())
        if worktree in indexed:
            raise FleetAuditError(f"duplicate ownership receipt for {worktree}")
        indexed[worktree] = entry
    return indexed


def list_worktrees(repo_root: Path) -> list[dict[str, str | bool]]:
    output = git(repo_root, "worktree", "list", "--porcelain").stdout.strip()
    if not output:
        return []
    records: list[dict[str, str | bool]] = []
    for block in output.split("\n\n"):
        record: dict[str, str | bool] = {}
        for line in block.splitlines():
            key, *rest = line.split(" ", 1)
            record[key] = rest[0] if rest else True
        if "worktree" in record:
            records.append(record)
    return records


def process_identity(pid: int) -> tuple[str | None, str | None]:
    try:
        result = run(
            ["ps", "-p", str(pid), "-o", "pid=", "-o", "lstart=", "-o", "command="],
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None, None
    if result.returncode != 0:
        return None, None
    fields = result.stdout.strip().split(maxsplit=6)
    if len(fields) != 7 or not fields[0].isdigit() or int(fields[0]) != pid:
        return None, None
    return " ".join(fields[1:6]), fields[6]


def normalized_open_path(raw_path: str, *, deleted: bool) -> tuple[Path, str | None]:
    clean_path = raw_path.removesuffix(" (deleted)") if deleted else raw_path
    opened_path = Path(clean_path)
    try:
        return opened_path.resolve(strict=False), None
    except (OSError, RuntimeError) as exc:
        return opened_path.absolute(), f"{type(exc).__name__}: {exc}"


def codegraph_index_identities(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    identities: dict[tuple[str, str | None, int | None], dict[str, Any]] = {}
    for item in files:
        path = Path(str(item.get("path", "")))
        if (
            item.get("type") != "REG"
            or item.get("deleted") is not False
            or item.get("path_resolution_error")
            or item.get("path_exists") is False
            or path.name != "codegraph.db"
            or path.parent.name != ".codegraph"
        ):
            continue
        identity = {
            "path": str(path),
            "device": item.get("device"),
            "inode": item.get("inode"),
        }
        identities[(identity["path"], identity["device"], identity["inode"])] = identity
    return sorted(identities.values(), key=lambda item: item["path"])


def same_device(raw_device: object, device: int) -> bool:
    if not isinstance(raw_device, str):
        return False
    try:
        return int(raw_device, 0) == device
    except ValueError:
        return False


def scan_holders(
    worktree_paths: list[Path],
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    try:
        result = run(["lsof", "-n", "-P", "-F", "pcftDikns"], check=False)
    except (FileNotFoundError, OSError):
        return {}, False
    if result.returncode not in (0, 1):
        return {}, False

    normalized = [path.resolve() for path in worktree_paths]
    processes: dict[int, dict[str, Any]] = {}
    process: dict[str, Any] | None = None
    opened_file: dict[str, Any] | None = None
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
            process = processes.setdefault(
                pid,
                {"pid": pid, "command": None, "files": []},
            )
            opened_file = None
        elif line.startswith("c"):
            if process is not None:
                process["command"] = line[1:]
        elif line.startswith("f") and process is not None:
            opened_file = {
                "fd": line[1:],
                "type": None,
                "device": None,
                "inode": None,
                "link_count": None,
            }
        elif line.startswith("t") and opened_file is not None:
            opened_file["type"] = line[1:]
        elif line.startswith("D") and opened_file is not None:
            opened_file["device"] = line[1:]
        elif line.startswith("i") and opened_file is not None:
            inode = line[1:]
            opened_file["inode"] = int(inode) if inode.isdigit() else None
        elif line.startswith("k") and opened_file is not None:
            link_count = line[1:]
            opened_file["link_count"] = (
                int(link_count) if link_count.isdigit() else None
            )
        elif line.startswith("n/") and process is not None:
            link_count = (opened_file or {}).get("link_count")
            deleted = link_count == 0 if isinstance(link_count, int) else None
            candidate, resolution_error = normalized_open_path(
                line[1:],
                deleted=deleted is True,
            )
            process["files"].append(
                {
                    **(opened_file or {}),
                    "path": str(candidate),
                    "raw_path": line[1:],
                    "path_exists": candidate.exists() if resolution_error is None else None,
                    "path_resolution_error": resolution_error,
                    "deleted": deleted,
                }
            )
            opened_file = None

    holders: dict[str, list[dict[str, Any]]] = {}
    for pid, item in processes.items():
        matched: dict[str, list[dict[str, Any]]] = {}
        for opened_file in item["files"]:
            candidate = Path(opened_file["path"])
            if opened_file.get("path_resolution_error"):
                for worktree in normalized:
                    matched.setdefault(str(worktree), []).append(opened_file)
                continue
            for worktree in normalized:
                try:
                    candidate.relative_to(worktree)
                except ValueError:
                    continue
                matched.setdefault(str(worktree), []).append(opened_file)
        if not matched:
            continue
        started_at, full_command = process_identity(pid)
        indexes = codegraph_index_identities(item["files"])
        for worktree_key, files in matched.items():
            holders.setdefault(worktree_key, []).append(
                {
                    "pid": pid,
                    "command": item["command"],
                    "process_command": full_command,
                    "started_at": started_at,
                    "files": files,
                    "codegraph_indexes": indexes,
                }
            )
    for items in holders.values():
        items.sort(key=lambda item: item["pid"])
    return holders, True


def is_codegraph_mcp_command(command: object) -> bool:
    if not isinstance(command, str) or not command.strip():
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    for index, token in enumerate(tokens):
        if Path(token).name != "codegraph.js":
            continue
        return tokens[index + 1 :] in (
            ["serve", "--mcp"],
            ["serve", "--mcp", "--no-watch"],
        )
    return False


def classify_cleanup_holders(
    worktree: Path,
    holders: list[dict[str, Any]],
) -> dict[str, Any]:
    if not holders:
        return {"kind": "none", "pids": [], "issues": []}

    lane = worktree.resolve()
    target_index = (lane / ".codegraph" / "codegraph.db").resolve(strict=False)
    target_stat = target_index.stat() if target_index.is_file() else None
    issues: list[str] = []
    pids: list[int] = []
    for holder in holders:
        pid = holder.get("pid")
        if not isinstance(pid, int):
            issues.append("holder PID is unavailable")
            continue
        pids.append(pid)
        if not holder.get("started_at") or not is_codegraph_mcp_command(
            holder.get("process_command")
        ):
            issues.append(f"PID {pid} is not a proven CodeGraph MCP process")

        files = holder.get("files")
        if not isinstance(files, list) or not files:
            issues.append(f"PID {pid} has no exact target FD evidence")
            continue
        for opened_file in files:
            resolution_error = opened_file.get("path_resolution_error")
            if resolution_error:
                raw_path = opened_file.get("raw_path") or opened_file.get("path")
                issues.append(
                    f"PID {pid} has unresolvable FD path {raw_path}: {resolution_error}"
                )
                continue
            opened_path = Path(str(opened_file.get("path", ""))).resolve(strict=False)
            try:
                relative = opened_path.relative_to(lane)
            except ValueError:
                issues.append(f"PID {pid} has an invalid target FD path")
                continue
            if opened_file.get("path_exists") is False:
                issues.append(
                    f"PID {pid} holds vanished target FD {relative.as_posix()}"
                )
                continue
            if (
                len(relative.parts) != 2
                or relative.parts[0] != ".codegraph"
                or relative.parts[1] not in CODEGRAPH_INDEX_FILENAMES
                or opened_file.get("type") != "REG"
                or opened_file.get("deleted") is not False
            ):
                issues.append(
                    f"PID {pid} holds non-detachable target FD {relative.as_posix()}"
                )

        indexes = holder.get("codegraph_indexes")
        if not isinstance(indexes, list):
            indexes = []
        matching_target = [
            item
            for item in indexes
            if Path(str(item.get("path", ""))).resolve(strict=False) == target_index
            and target_stat is not None
            and same_device(item.get("device"), target_stat.st_dev)
            and item.get("inode") == target_stat.st_ino
        ]
        if not matching_target:
            issues.append(f"PID {pid} target index inode is not proven")
        external_indexes = [
            item
            for item in indexes
            if Path(str(item.get("path", ""))).resolve(strict=False) != target_index
            and not str(Path(str(item.get("path", ""))).resolve(strict=False)).startswith(
                f"{lane}{os.sep}"
            )
        ]
        if not external_indexes:
            issues.append(f"PID {pid} is not proven to serve another CodeGraph index")

    return {
        "kind": "shared_codegraph_index_only" if not issues else "blocking",
        "pids": sorted(set(pids)),
        "issues": sorted(set(issues)),
    }


def upstream_target(repo_root: Path, override: str | None) -> str:
    if override:
        return override
    result = git(
        repo_root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    )
    target = result.stdout.strip()
    if not target:
        raise FleetAuditError(f"{repo_root} main checkout has no upstream; pass --target")
    return target


def split_remote_target(target: str) -> tuple[str, str]:
    if "/" not in target:
        raise FleetAuditError(f"target must name a remote tracking branch: {target}")
    remote, branch = target.split("/", 1)
    if not remote or not branch:
        raise FleetAuditError(f"invalid remote tracking target: {target}")
    return remote, branch


def read_remote_heads(repo_root: Path, remote: str) -> dict[str, str]:
    result = git(repo_root, "ls-remote", "--heads", remote)
    heads: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[1].startswith("refs/heads/"):
            continue
        heads[fields[1].removeprefix("refs/heads/")] = fields[0]
    return heads


def commit_exists(repo_root: Path, commit: str) -> bool:
    return (
        git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode
        == 0
    )


def is_ancestor(repo_root: Path, older: str, newer: str) -> bool:
    return (
        git(
            repo_root,
            "merge-base",
            "--is-ancestor",
            older,
            newer,
            check=False,
        ).returncode
        == 0
    )


def root_currentness(
    repo_root: Path,
    target: str,
    wire_head: str | None,
    *,
    remote_checked: bool,
) -> dict[str, Any]:
    root_head = git(repo_root, "rev-parse", "HEAD^{commit}").stdout.strip()
    target_head = git(repo_root, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    dirty_entries = [
        line
        for line in git(
            repo_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).stdout.splitlines()
        if line
    ]
    issues: list[str] = []

    if not remote_checked:
        status = "remote_unchecked"
        comparison = target_head
        issues.append("canonical wire was not checked")
    elif wire_head is None:
        status = "remote_target_missing"
        comparison = None
        issues.append("canonical target branch is absent from the remote")
    else:
        comparison = wire_head
        if target_head != wire_head:
            issues.append("local tracking ref does not match canonical wire")
        if root_head == wire_head and target_head == wire_head:
            status = "aligned"
        elif not commit_exists(repo_root, wire_head):
            status = "fetch_required"
        elif is_ancestor(repo_root, root_head, wire_head):
            status = "fast_forward_required"
        elif is_ancestor(repo_root, wire_head, root_head):
            status = "root_ahead_of_wire"
        else:
            status = "recovery_required"

    if dirty_entries:
        issues.append("canonical checkout is dirty")
    return {
        "status": status,
        "root_head": root_head,
        "target": target,
        "target_head": target_head,
        "wire_head": wire_head,
        "comparison_head": comparison,
        "dirty": bool(dirty_entries),
        "dirty_entries": dirty_entries,
        "issues": issues,
    }


def audit_repo(
    repo_root: Path,
    receipts: dict[str, dict[str, Any]],
    *,
    target_override: str | None,
    check_remote: bool,
    holders: dict[str, list[dict[str, Any]]],
    holder_scan_available: bool,
) -> dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    canonical_root = Path(
        git(repo_root, "rev-parse", "--show-toplevel").stdout.strip()
    ).resolve()
    if canonical_root != repo_root:
        raise FleetAuditError(f"repo root must be its Git top level: {repo_root}")

    target = upstream_target(repo_root, target_override)
    remote, target_branch = split_remote_target(target)
    remote_heads = read_remote_heads(repo_root, remote) if check_remote else {}
    wire_head = remote_heads.get(target_branch) if check_remote else None
    currentness = root_currentness(
        repo_root,
        target,
        wire_head,
        remote_checked=check_remote,
    )

    lanes: list[dict[str, Any]] = []
    registered_paths: set[str] = set()
    for record in list_worktrees(repo_root):
        path = Path(str(record["worktree"])).resolve()
        if path == canonical_root:
            continue
        registered_paths.add(str(path))
        try:
            absorption = absorption_audit(canonical_root, path, target)
        except AuditError as exc:
            absorption = {
                "classification": "owner_review",
                "cleanup_allowed": False,
                "dirty": None,
                "dirty_entries": [],
                "issues": [str(exc)],
            }

        receipt = receipts.get(str(path))
        receipt_status = receipt.get("status") if receipt else None
        active = receipt_status == ACTIVE
        path_holders = holders.get(str(path), [])
        holder_classification = classify_cleanup_holders(path, path_holders)
        issues = list(absorption.get("issues", []))
        blocking_issues: list[str] = []
        branch = absorption.get("lane_branch")
        remote_branch_head = remote_heads.get(branch) if check_remote and branch else None

        if active:
            action = "retain_active"
        elif absorption.get("cleanup_allowed"):
            if holder_classification["kind"] == "shared_codegraph_index_only":
                action = "index_detach_ready"
            elif path_holders:
                action = "holder_exit_required"
            elif not holder_scan_available:
                action = "holder_proof_required"
            else:
                action = "cleanup_ready"
        else:
            action = "recovery_owner_required"

        if (
            check_remote
            and not absorption.get("cleanup_allowed")
            and isinstance(branch, str)
            and remote_branch_head is None
        ):
            blocking_issues.append(
                "unabsorbed task branch is not recoverable from the remote"
            )
        if (
            check_remote
            and not absorption.get("cleanup_allowed")
            and isinstance(branch, str)
            and remote_branch_head is not None
            and remote_branch_head != absorption.get("lane_head")
        ):
            blocking_issues.append(
                "remote task branch does not match the worktree HEAD"
            )
        if (
            check_remote
            and not absorption.get("cleanup_allowed")
            and not branch
        ):
            blocking_issues.append(
                "unabsorbed worktree is detached; remote recovery cannot be proven"
            )
        if active and absorption.get("dirty"):
            blocking_issues.append(
                "dirty ACTIVE worktree has bytes not recoverable from the remote"
            )
        issues.extend(blocking_issues)

        lanes.append(
            {
                "worktree": str(path),
                "branch": branch,
                "head": absorption.get("lane_head"),
                "classification": absorption.get("classification"),
                "cleanup_allowed_by_absorption": absorption.get("cleanup_allowed", False),
                "dirty": absorption.get("dirty"),
                "dirty_entries": absorption.get("dirty_entries", []),
                "holders": path_holders,
                "holder_classification": holder_classification,
                "receipt_status": receipt_status,
                "thread_id": receipt.get("thread_id") if receipt else None,
                "objective_id": receipt.get("objective_id") if receipt else None,
                "owner": receipt.get("owner") if receipt else None,
                "execution_owner": receipt.get("execution_owner") if receipt else None,
                "next_action": receipt.get("next_action") if receipt else None,
                "write_set": receipt.get("write_set") if receipt else None,
                "integration_overlaps": [],
                "remote_branch_head": remote_branch_head,
                "action": action,
                "issues": issues,
                "blocking_issues": blocking_issues,
            }
        )

    active_lanes = [
        lane
        for lane in lanes
        if lane["receipt_status"] == ACTIVE and isinstance(lane["write_set"], list)
    ]
    for lane in active_lanes:
        for other in active_lanes:
            if lane["worktree"] == other["worktree"]:
                continue
            overlap_paths = sorted(set(lane["write_set"]) & set(other["write_set"]))
            if overlap_paths:
                lane["integration_overlaps"].append(
                    {
                        "worktree": other["worktree"],
                        "thread_id": other["thread_id"],
                        "objective_id": other["objective_id"],
                        "owner": other["owner"],
                        "paths": overlap_paths,
                    }
                )
        lane["integration_overlaps"].sort(
            key=lambda item: (item["worktree"], item["owner"])
        )

    unresolved = [
        lane
        for lane in lanes
        if lane["action"] != "retain_active" or lane["blocking_issues"]
    ]
    ok = (
        currentness["status"] == "aligned"
        and not currentness["dirty"]
        and not unresolved
    )
    return {
        "repo_root": str(canonical_root),
        "target": target,
        "remote_checked": check_remote,
        "holder_scan_available": holder_scan_available,
        "currentness": currentness,
        "worktrees": lanes,
        "summary": {
            "worktree_count": len(lanes),
            "active_owned": sum(lane["action"] == "retain_active" for lane in lanes),
            "cleanup_ready": sum(lane["action"] == "cleanup_ready" for lane in lanes),
            "index_detach_ready": sum(
                lane["action"] == "index_detach_ready" for lane in lanes
            ),
            "recovery_owner_required": sum(
                lane["action"] == "recovery_owner_required" for lane in lanes
            ),
            "holder_exit_required": sum(
                lane["action"] == "holder_exit_required" for lane in lanes
            ),
            "holder_proof_required": sum(
                lane["action"] == "holder_proof_required" for lane in lanes
            ),
        },
        "ok": ok,
    }


def audit_fleet(
    repo_roots: list[Path],
    receipts: dict[str, dict[str, Any]],
    *,
    target_override: str | None = None,
    check_remote: bool = True,
    holders: dict[str, list[dict[str, Any]]] | None = None,
    holder_scan_available: bool | None = None,
) -> dict[str, Any]:
    if holders is None:
        worktree_paths = [
            Path(str(record["worktree"]))
            for root in repo_roots
            for record in list_worktrees(root.expanduser().resolve())
            if Path(str(record["worktree"])).resolve() != root.expanduser().resolve()
        ]
        holders, detected = scan_holders(worktree_paths)
        if holder_scan_available is None:
            holder_scan_available = detected
    elif holder_scan_available is None:
        holder_scan_available = True

    repos = [
        audit_repo(
            root,
            receipts,
            target_override=target_override,
            check_remote=check_remote,
            holders=holders,
            holder_scan_available=bool(holder_scan_available),
        )
        for root in repo_roots
    ]
    registered_paths = {
        lane["worktree"]
        for repo in repos
        for lane in repo["worktrees"]
    }
    stale_receipts = sorted(set(receipts).difference(registered_paths))
    return {
        "schema": SCHEMA,
        "ok": all(repo["ok"] for repo in repos) and not stale_receipts,
        "remote_checked": check_remote,
        "holder_scan_available": bool(holder_scan_available),
        "stale_receipts": stale_receipts,
        "repos": repos,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", action="append", required=True, type=Path)
    parser.add_argument("--ownership-ledger", type=Path)
    parser.add_argument("--target", help="Override the upstream target for every repo.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not query canonical remote heads; the report cannot be terminal.",
    )
    parser.add_argument(
        "--skip-holder-scan",
        action="store_true",
        help="Skip lsof; cleanup candidates require separate holder proof.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        receipts = load_ledger(args.ownership_ledger)
        holders: dict[str, list[dict[str, Any]]] | None = None
        holder_scan_available: bool | None = None
        if args.skip_holder_scan:
            holders = {}
            holder_scan_available = False
        payload = audit_fleet(
            args.repo_root,
            receipts,
            target_override=args.target,
            check_remote=not args.offline,
            holders=holders,
            holder_scan_available=holder_scan_available,
        )
    except FleetAuditError as exc:
        payload = {
            "schema": SCHEMA,
            "ok": False,
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
