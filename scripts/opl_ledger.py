"""Beads/Dolt storage adapter. No routing, execution, or Fleet dependencies."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


class LedgerError(RuntimeError):
    pass


Runner = Callable[..., Any]


def run(
    argv: list[str], cwd: Path, *, check: bool = True, json_output: bool = False,
) -> subprocess.CompletedProcess[str] | Any:
    result = subprocess.run(
        argv, cwd=cwd, check=False, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    if check and result.returncode:
        raise LedgerError((result.stderr or result.stdout).strip())
    if not json_output:
        return result
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LedgerError(f"{argv[0]} returned invalid JSON") from exc


def probe(root: Path, bd: str, *, runner: Runner | None = None) -> dict[str, Any] | None:
    execute = runner or run
    result = execute([bd, "status", "--no-activity", "--json"], root, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        if "no beads project found" in detail.lower():
            return None
        raise LedgerError(f"bd status failed: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LedgerError("bd status returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise LedgerError("bd status returned an invalid payload")
    return payload


def _safe_directory(root: Path) -> bool:
    directory = root / ".beads"
    return root.is_dir() and directory.is_dir() and not directory.is_symlink()


def secure(root: Path) -> None:
    if not _safe_directory(root):
        raise LedgerError("ledger repository is missing or unsafe")
    try:
        os.chmod(root / ".beads", 0o700)
    except OSError as exc:
        raise LedgerError(f"cannot secure {root / '.beads'}: {exc}") from exc


def init(
    root: Path, bd: str, prefix: str, *, runner: Runner | None = None,
    probe_fn: Callable[[], dict[str, Any] | None] | None = None,
) -> dict[str, str]:
    execute = runner or run
    inspect = probe_fn or (lambda: probe(root, bd, runner=execute))
    if inspect() is not None:
        secure(root)
        return {"state": "already_initialized", "instance": str(root)}
    git_dir = str(execute(["git", "rev-parse", "--git-dir"], root).stdout).strip()
    common_dir = str(execute(["git", "rev-parse", "--git-common-dir"], root).stdout).strip()

    def git_path(value: str) -> Path:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    if git_path(git_dir) != git_path(common_dir):
        raise LedgerError("first bd init requires a primary checkout or standalone clone")
    if str(execute(["git", "status", "--porcelain", "--untracked-files=all"], root).stdout).strip():
        raise LedgerError("bd init creates a commit and requires a clean Git checkout")
    execute([
        bd, "init", "--prefix", prefix, "--skip-agents", "--skip-hooks", "--non-interactive",
    ], root)
    if inspect() is None:
        raise LedgerError("bd init completed without a readable ledger")
    secure(root)
    return {"state": "initialized", "instance": str(root), "prefix": prefix}


def read_issue(
    root: Path, bd: str, issue_id: str, *, runner: Runner | None = None,
) -> dict[str, Any]:
    execute = runner or run
    payload = execute([bd, "show", issue_id, "--json"], root, json_output=True)
    if isinstance(payload, list) and len(payload) == 1:
        payload = payload[0]
    if not isinstance(payload, dict) or payload.get("id") != issue_id:
        raise LedgerError(f"bd show returned an invalid issue: {issue_id}")
    if payload.get("metadata") is not None and not isinstance(payload["metadata"], dict):
        raise LedgerError(f"Bead metadata is invalid: {issue_id}")
    return payload


def pull(root: Path, bd: str, *, runner: Runner | None = None) -> None:
    execute = runner or run
    result = execute([bd, "dolt", "pull"], root, check=False)
    if result.returncode:
        raise LedgerError(f"bd dolt pull failed: {(result.stderr or result.stdout).strip()}")


def apply_metadata(
    root: Path, bd: str, issue: dict[str, Any], metadata: dict[str, Any],
    *, runner: Runner | None = None,
) -> dict[str, Any]:
    execute = runner or run
    issue_id = str(issue["id"])
    if issue.get("metadata") == metadata:
        return issue
    execute([
        bd, "update", issue_id, "--metadata",
        json.dumps(metadata, ensure_ascii=False, sort_keys=True), "--json",
    ], root)
    local = read_issue(root, bd, issue_id, runner=execute)
    if local.get("metadata") != metadata:
        raise LedgerError("Bead metadata write readback did not match")
    pushed = execute([bd, "dolt", "push"], root, check=False)
    if pushed.returncode:
        # Resolve an unknown push before considering another mutation.
        pulled = execute([bd, "dolt", "pull"], root, check=False)
        if pulled.returncode:
            raise LedgerError("owner migration push result is unknown; read-only reconcile required")
        reconciled = read_issue(root, bd, issue_id, runner=execute)
        if reconciled.get("metadata") != metadata:
            raise LedgerError("owner migration lost the Dolt CAS; winner readback required")
        return reconciled
    pull(root, bd, runner=execute)
    canonical = read_issue(root, bd, issue_id, runner=execute)
    if canonical.get("metadata") != metadata:
        raise LedgerError("owner migration Dolt parity did not match")
    return canonical


def workspace_readback(
    repository: Path, role: str, *, fresh_pull: bool,
    bd: str | None = None, runner: Runner | None = None,
) -> dict[str, Any]:
    execute = runner or run
    result = {"role": role, "fresh_pull": False, "readable": False, "state": "ATTENTION"}
    if not _safe_directory(repository):
        return result
    if (repository / ".beads").stat().st_mode & 0o077:
        return {**result, "state": "PERMISSIONS"}
    configured = execute(["git", "config", "--get", "beads.role"], repository, check=False)
    if configured.returncode or configured.stdout.strip() != role:
        return {**result, "state": "ROLE_MISMATCH"}
    bd = bd or shutil.which("bd")
    if not bd:
        return {**result, "state": "TOOL_MISSING"}
    if fresh_pull:
        pulled = execute([bd, "dolt", "pull"], repository, check=False)
        if pulled.returncode:
            return {**result, "state": "PULL_FAILED"}
        result["fresh_pull"] = True
    readable = execute([bd, "--readonly", "list", "--limit", "1", "--json"], repository, check=False)
    if readable.returncode:
        return {**result, "state": "UNREADABLE"}
    try:
        payload = json.loads(readable.stdout)
    except json.JSONDecodeError:
        return {**result, "state": "UNREADABLE"}
    if not isinstance(payload, list):
        return {**result, "state": "UNREADABLE"}
    return {**result, "readable": True, "state": "CURRENT"}


def sync_workspace_ledger(
    repository: Path, role: str, *, bd: str | None = None, runner: Runner | None = None,
) -> None:
    execute = runner or run
    if not _safe_directory(repository):
        raise LedgerError("workspace ledger repository is missing or unsafe")
    secure(repository)
    configured = execute(["git", "config", "beads.role", role], repository, check=False)
    if configured.returncode:
        raise LedgerError("workspace ledger role configuration failed")
    bd = bd or shutil.which("bd")
    if not bd:
        raise LedgerError("workspace ledger requires bd")
    existing = workspace_readback(repository, role, fresh_pull=False, bd=bd, runner=execute)
    if existing["state"] != "CURRENT":
        bootstrapped = execute([bd, "bootstrap", "--yes"], repository, check=False)
        if bootstrapped.returncode:
            raise LedgerError("workspace ledger bootstrap failed")
    pulled = execute([bd, "dolt", "pull"], repository, check=False)
    if pulled.returncode:
        raise LedgerError("workspace ledger pull failed")


def list_issues(
    root: Path, bd: str, *, statuses: tuple[str, ...] | None = None,
    skip_labels: bool = False, limit: int = 0, runner: Runner | None = None,
) -> list[Any]:
    execute = runner or run
    selection = ["--status", ",".join(statuses)] if statuses is not None else ["--all"]
    argv = [bd, "list", *selection, "--limit", str(limit)]
    if skip_labels:
        argv.append("--skip-labels")
    payload = execute([*argv, "--json"], root, json_output=True)
    if isinstance(payload, dict):
        payload = payload.get("issues")
    if not isinstance(payload, list):
        raise LedgerError("bd list returned an invalid payload")
    return payload


def update_status(
    root: Path, bd: str, issue_id: str, status: str, *, runner: Runner | None = None,
) -> None:
    execute = runner or run
    execute([bd, "update", issue_id, "--status", status, "--json"], root)


def create_issue(
    root: Path, bd: str, *, title: str, issue_type: str, external_ref: str,
    labels: str, description: str, metadata: dict[str, Any], priority: str = "P2",
    due: str | None = None, parent: str | None = None, runner: Runner | None = None,
) -> dict[str, Any]:
    execute = runner or run
    argv = [
        bd, "create", title, "--type", issue_type, "--priority", priority,
        "--external-ref", external_ref, "--labels", labels, "--description", description,
        "--metadata", json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    ]
    if due:
        argv += ["--defer", due, "--due", due]
    if parent:
        argv += ["--parent", parent]
    payload = execute([*argv, "--json"], root, json_output=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        raise LedgerError("bd create returned an invalid payload")
    return payload


def status(root: Path, bd: str, *, runner: Runner | None = None) -> dict[str, Any]:
    execute = runner or run
    payload = execute([bd, "status", "--no-activity", "--json"], root, json_output=True)
    if not isinstance(payload, dict):
        raise LedgerError("bd status returned an invalid payload")
    return payload


def ready(root: Path, bd: str, *, limit: int = 0, runner: Runner | None = None) -> list[Any]:
    execute = runner or run
    payload = execute([bd, "ready", "--limit", str(limit), "--json"], root, json_output=True)
    if not isinstance(payload, list):
        raise LedgerError("bd ready returned an invalid payload")
    return payload


def dolt_status(root: Path, bd: str, *, runner: Runner | None = None) -> dict[str, Any]:
    execute = runner or run
    payload = execute([bd, "dolt", "status", "--json"], root, json_output=True)
    if not isinstance(payload, dict):
        raise LedgerError("bd dolt status returned an invalid payload")
    return payload


def version(root: Path, bd: str, *, runner: Runner | None = None) -> str:
    execute = runner or run
    return execute([bd, "version"], root).stdout.strip()


def legacy_linear_status(root: Path, bd: str, *, runner: Runner | None = None) -> dict[str, Any]:
    execute = runner or run
    result = execute([bd, "linear", "status", "--json"], root, check=False)
    if result.returncode:
        raise LedgerError((result.stderr or result.stdout).strip())
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LedgerError("bd linear status returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise LedgerError("bd linear status returned an invalid payload")
    allowed = (
        "auth_mode", "configured", "has_api_key", "has_oauth", "last_sync",
        "pending_push", "team_id", "team_ids", "total_issues", "with_linear_ref",
    )
    return {key: payload.get(key) for key in allowed}
