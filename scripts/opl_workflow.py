#!/usr/bin/env python3
"""Small OPL entry for Beads-backed ledger setup and reconciliation."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from . import opl_ledger, opl_execution
    from .opl_fleet_parts import fleet_execution
    from .opl_task_owner import (
        TaskOwnerError,
        claim as claim_owner_migration,
        preflight as preflight_owner_migration,
        prepare as prepare_owner_migration,
        public_status as owner_migration_status,
        release_source as release_owner_migration,
        rollback as rollback_owner_migration,
        verify_target as verify_owner_migration,
    )
except ImportError:  # Direct script execution.
    import opl_ledger, opl_execution
    from opl_fleet_parts import fleet_execution
    from opl_task_owner import (
        TaskOwnerError,
        claim as claim_owner_migration,
        preflight as preflight_owner_migration,
        prepare as prepare_owner_migration,
        public_status as owner_migration_status,
        release_source as release_owner_migration,
        rollback as rollback_owner_migration,
        verify_target as verify_owner_migration,
    )


PROGRAM_REF = "opl://program/operations-maintenance"
SUPERVISOR_EXECUTION_MODES = {
    "active",
    "backlog",
    "waiting_user",
    "waiting_external",
    "monitoring",
    "on_demand",
    "aggregate",
}
SUPERVISOR_METADATA_FIELDS = (
    "task_lifecycle_class",
    "classification",
    "classification_reason",
    "execution_mode",
    "execution_thread",
    "last_execution_thread",
    "current_slice",
    "first_blocker",
    "next_action",
    "remaining",
    "linear_issue_identifier",
    "linear_issue_url",
    "last_user_comment_id",
    "last_user_comment_at",
    "last_agent_writeback_comment_id",
    "last_supervised_at",
    "thread_intake_cursor_at",
    "next_review_at",
    "trigger_condition",
)
REGISTRY_SECTIONS = (
    ("services", "service"),
    ("domains", "domain"),
    ("platform_accounts", "platform-account"),
)


class WorkflowError(RuntimeError):
    pass


def flow_root() -> Path:
    return Path(__file__).resolve().parents[1]


def executable(name: str, explicit: str | None = None, env: str | None = None) -> str:
    candidate = explicit or (os.environ.get(env) if env else None) or shutil.which(name)
    if not candidate:
        raise WorkflowError(f"owner CLI is unavailable: {name}")
    path = Path(candidate).expanduser()
    if path.is_absolute() and not os.access(path, os.X_OK):
        raise WorkflowError(f"owner CLI is not executable: {path}")
    return str(path)


def cli_probe(
    name: str,
    cwd: Path,
    explicit: str | None = None,
    *,
    version_args: tuple[str, ...] = ("--version",),
) -> dict[str, Any]:
    try:
        command = executable(name, explicit)
        result = run([command, *version_args], cwd)
        assert isinstance(result, subprocess.CompletedProcess)
        version = (result.stdout or result.stderr).strip()
        resolved = shutil.which(command) or command
        return {
            "available": True,
            "path": str(Path(resolved).resolve()),
            "version": version,
        }
    except WorkflowError as exc:
        return {"available": False, "error": str(exc)}


def github_probe(cwd: Path, explicit: str | None = None) -> dict[str, Any]:
    tool = cli_probe("gh", cwd, explicit)
    if not tool["available"]:
        return tool
    auth = run(
        [str(tool["path"]), "auth", "status", "--hostname", "github.com"],
        cwd,
        check=False,
    )
    assert isinstance(auth, subprocess.CompletedProcess)
    tool["authenticated"] = auth.returncode == 0
    return tool


def run(
    argv: list[str],
    cwd: Path,
    *,
    check: bool = True,
    json_output: bool = False,
) -> subprocess.CompletedProcess[str] | Any:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode:
        raise WorkflowError((result.stderr or result.stdout).strip())
    if not json_output:
        return result
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"{argv[0]} returned invalid JSON") from exc


def instance_root(value: str | Path | None, *, required: bool = True) -> Path | None:
    configured = value or os.environ.get("OPL_INSTANCE")
    if not configured:
        if required:
            raise WorkflowError("pass --instance or set OPL_INSTANCE")
        return None
    root = Path(configured).expanduser().resolve()
    if not root.is_dir():
        raise WorkflowError(f"OPL Instance does not exist: {root}")
    return root


def fleet_command(instance: Path | None, explicit: str | None) -> tuple[list[str], str]:
    bundled = flow_root() / "scripts" / "opl_fleet.py"
    if instance and (instance / "fleet/fleet.json").is_file() and (
        instance / "fleet/nodes.json"
    ).is_file():
        return (
            [sys.executable, str(bundled), "--instance", str(instance)],
            "opl-flow",
        )
    fleet = executable("opl-fleet", explicit, "OPL_FLEET_BIN")
    return ([fleet], "opl-fleet")


def ledger_probe(root: Path, bd: str) -> dict[str, Any] | None:
    try:
        return opl_ledger.probe(root, bd, runner=run)
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc


def linear_adapter_probe(root: Path, bd: str) -> dict[str, Any]:
    try:
        payload = opl_ledger.legacy_linear_status(root, bd, runner=run)
    except (opl_ledger.LedgerError, WorkflowError) as exc:
        return {"state": "error", "error": str(exc)}
    return {"state": "current", **payload}


def linear_projection_probe(root: Path, bd: str) -> dict[str, Any]:
    try:
        issues = opl_ledger.list_issues(root, bd, skip_labels=True, runner=run)
    except (opl_ledger.LedgerError, WorkflowError) as exc:
        return {"state": "error", "error": str(exc)}
    if any(not isinstance(item, dict) for item in issues):
        return {"state": "error", "error": "Ledger issue list contains an invalid entry"}

    managed = 0
    identifiers = 0
    urls = 0
    for item in issues:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        managed += metadata.get("linear_projection") == "managed"
        identifiers += isinstance(metadata.get("linear_issue_identifier"), str)
        urls += isinstance(metadata.get("linear_issue_url"), str)
    total = len(issues)
    return {
        "state": "current",
        "total_issue_count": total,
        "managed_issue_count": managed,
        "identifier_count": identifiers,
        "url_count": urls,
        "coverage_complete": total > 0 and managed == identifiers == urls == total,
    }


def linear_probe(root: Path, bd: str) -> dict[str, Any]:
    adapter = linear_adapter_probe(root, bd)
    projection = linear_projection_probe(root, bd)
    sources: list[str] = []
    if adapter.get("state") == "current" and adapter.get("configured") is True:
        sources.append("legacy_adapter")
    if projection.get("state") == "current" and int(projection.get("managed_issue_count", 0)) > 0:
        sources.append("managed_projection")

    current_planes = sum(item.get("state") == "current" for item in (adapter, projection))
    state = "current" if current_planes == 2 else "degraded" if current_planes == 1 else "error"
    compatibility = {
        key: adapter.get(key)
        for key in (
            "auth_mode",
            "has_api_key",
            "has_oauth",
            "last_sync",
            "pending_push",
            "team_id",
            "team_ids",
            "total_issues",
            "with_linear_ref",
        )
    }
    return {
        "state": state,
        "configured": bool(sources),
        "configuration_sources": sources,
        "legacy_adapter_configured": adapter.get("configured") is True,
        "legacy_external_ref_count": adapter.get("with_linear_ref"),
        "legacy_adapter": adapter,
        "projection": projection,
        **compatibility,
    }


def secure_ledger_dir(root: Path) -> None:
    try:
        opl_ledger.secure(root)
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc


def bead_issue(root: Path, bd: str, issue_id: str) -> dict[str, Any]:
    try:
        return opl_ledger.read_issue(root, bd, issue_id, runner=run)
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc


def dolt_pull(root: Path, bd: str) -> None:
    try:
        opl_ledger.pull(root, bd, runner=run)
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc


def apply_bead_metadata(
    root: Path, bd: str, issue: dict[str, Any], metadata: dict[str, Any],
) -> dict[str, Any]:
    try:
        return opl_ledger.apply_metadata(root, bd, issue, metadata, runner=run)
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc


def read_json_argument(value: str, label: str) -> dict[str, Any]:
    path = Path(value[1:] if value.startswith("@") else value).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise WorkflowError(f"{label} must be a JSON object")
    return payload


def owner_migration_command(root: Path, bd: str, args: argparse.Namespace) -> dict[str, Any]:
    dolt_pull(root, bd)
    issue = bead_issue(root, bd, args.bead_id)
    action = args.owner_action
    if action == "status":
        return owner_migration_status(issue)
    # Translate carrier receipts at the coordination boundary, before pure Ledger transitions.
    def admission_inputs():
        workspace = read_json_argument(args.workspace_readback_json, "workspace readback")
        node = read_json_argument(args.node_readback_json, "node readback")
        migration = (issue.get("metadata") or {}).get("opl_owner_migration") or {}
        target = migration.get("target") or {}
        if workspace.get("schema") == "opl_fleet_workspace_readback.v1":
            workspace = fleet_execution.workspace_evidence(workspace, node_id=target.get("node_id", ""))
        if node.get("schema") == "codex_fleet_doctor.v1":
            node = fleet_execution.node_evidence(node, objective_id=str(issue["id"]))
        return {"workspace_readback": workspace, "node_readback": node}
    try:
        if action == "prepare":
            metadata = prepare_owner_migration(
                issue,
                source_owner_id=args.source_owner,
                source_node_id=args.source_node,
                source_executor_handle=args.source_executor,
                target_owner_id=args.target_owner,
                target_node_id=args.target_node,
                target_profile_id=args.target_profile,
                instruction_revision=args.instruction_revision,
                instruction_summary=args.instruction_summary,
                checkpoint=read_json_argument(args.checkpoint_json, "source checkpoint"),
                actor=args.actor,
                migration_id=args.migration_id,
            )
        elif action == "preflight":
            metadata = preflight_owner_migration(
                issue,
                migration_id=args.migration_id,
                **admission_inputs(),
                actor=args.actor,
            )
        elif action == "claim":
            metadata = claim_owner_migration(
                issue,
                migration_id=args.migration_id,
                target_executor_handle=args.target_executor,
                expected_instruction_revision=args.instruction_revision,
                expected_instruction_fingerprint=args.instruction_fingerprint,
                **admission_inputs(),
                actor=args.actor,
            )
        elif action == "verify":
            metadata = verify_owner_migration(
                issue,
                migration_id=args.migration_id,
                target_executor_handle=args.target_executor,
                **admission_inputs(),
                actor=args.actor,
            )
        elif action == "release":
            metadata = release_owner_migration(
                issue,
                migration_id=args.migration_id,
                actor=args.actor,
            )
        else:
            metadata = rollback_owner_migration(
                issue,
                migration_id=args.migration_id,
                actor=args.actor,
            )
    except TaskOwnerError as exc:
        raise WorkflowError(str(exc)) from exc
    canonical = apply_bead_metadata(root, bd, issue, metadata)
    return owner_migration_status(canonical)


def init_ledger(root: Path, bd: str, prefix: str) -> dict[str, str]:
    try:
        return opl_ledger.init(root, bd, prefix, runner=run, probe_fn=lambda: ledger_probe(root, bd))
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc


def registry_items(registry_path: Path) -> Iterable[dict[str, str]]:
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read Operations Registry: {registry_path}") from exc
    if not isinstance(registry, dict) or registry.get("schema") != "opl_operations_registry.v1":
        raise WorkflowError("Operations Registry must use opl_operations_registry.v1")
    for section, kind in REGISTRY_SECTIONS:
        entries = registry.get(section, [])
        if not isinstance(entries, list):
            raise WorkflowError(f"Operations Registry {section} must be an array")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise WorkflowError(f"Operations Registry {section} entry lacks id")
            maintenance = entry.get("maintenance")
            if maintenance is None:
                continue
            if not isinstance(maintenance, dict):
                raise WorkflowError(f"Operations Registry {section} entry has invalid maintenance")
            review_on = maintenance.get("next_review_on")
            if review_on is None:
                continue
            if not isinstance(review_on, str):
                raise WorkflowError(f"Operations Registry {section} entry has invalid next_review_on")
            asset_id = entry["id"]
            yield {
                "asset_id": asset_id,
                "kind": kind,
                "display": str(entry.get("name") or entry.get("fqdn") or entry.get("provider") or asset_id),
                "review_on": review_on,
                "action": str(maintenance.get("action_zh") or "按 owner 路径核对状态并更新复核日期。"),
            }


def create_bead(
    root: Path,
    bd: str,
    *,
    title: str,
    issue_type: str,
    external_ref: str,
    labels: str,
    description: str,
    metadata: dict[str, str],
    due: str | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    try:
        return opl_ledger.create_issue(
            root, bd, title=title, issue_type=issue_type, external_ref=external_ref,
            labels=labels, description=description, metadata=metadata,
            due=due, parent=parent, runner=run,
        )
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc


def reconcile_operations(
    root: Path,
    bd: str,
    registry_path: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    registry = (registry_path or root / "operations" / "registry.json").expanduser().resolve()
    items = list(registry_items(registry))
    if not items:
        return {
            "schema": "opl_flow_operations_reconcile.v1",
            "instance": str(root),
            "registry": str(registry),
            "dry_run": dry_run,
            "created": [],
            "unchanged": [],
            "counts": {
                "scheduled_assets": 0,
                "created": 0,
                "unchanged": 0,
            },
        }
    try:
        listed = opl_ledger.list_issues(root, bd, runner=run)
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc
    existing = {
        item["external_ref"]: item
        for item in listed
        if isinstance(item, dict) and isinstance(item.get("external_ref"), str)
    }
    created: list[dict[str, str]] = []
    unchanged: list[dict[str, str]] = []
    program = existing.get(PROGRAM_REF)
    program_id = str(program["id"]) if program else None
    if program and program.get("status") == "open" and not dry_run:
        opl_ledger.update_status(root, bd, program_id, "in_progress", runner=run)
    if not program_id:
        created.append({"kind": "program", "external_ref": PROGRAM_REF})
        if not dry_run:
            program = create_bead(
                root,
                bd,
                title="OPL Operations maintenance",
                issue_type="epic",
                external_ref=PROGRAM_REF,
                labels="opl,operations",
                description="Operations Registry 到期复核的持久总账；凭据和 live state 仍由各 owner 管理。",
                metadata={"source": "operations/registry.json"},
            )
            program_id = str(program["id"])
            opl_ledger.update_status(root, bd, program_id, "in_progress", runner=run)

    for item in items:
        external_ref = f"opl://operations/{item['kind']}/{item['asset_id']}/review/{item['review_on']}"
        summary = {key: item[key] for key in ("kind", "asset_id", "review_on")}
        summary["external_ref"] = external_ref
        if external_ref in existing:
            unchanged.append(summary)
            continue
        created.append(summary)
        if not dry_run:
            create_bead(
                root,
                bd,
                title=f"复核运维资产：{item['display']}",
                issue_type="task",
                external_ref=external_ref,
                labels=f"opl,operations-review,{item['kind']}",
                description=(
                    f"资产：{item['kind']}/{item['asset_id']}\n"
                    f"计划日期：{item['review_on']}\n维护动作：{item['action']}\n"
                    "完成后更新 Registry 的 verified_on/next_review_on；不得记录 secret。"
                ),
                metadata={
                    "asset_id": item["asset_id"],
                    "asset_kind": item["kind"],
                    "source": "operations/registry.json",
                },
                due=item["review_on"],
                parent=program_id,
            )
    return {
        "schema": "opl_flow_operations_reconcile.v1",
        "instance": str(root),
        "registry": str(registry),
        "dry_run": dry_run,
        "created": created,
        "unchanged": unchanged,
        "counts": {
            "scheduled_assets": len(items),
            "created": len(created),
            "unchanged": len(unchanged),
        },
    }


def supervisor_snapshot(root: Path, bd: str, git_arg: str | None = None) -> dict[str, Any]:
    """Collect a compact, read-only Ledger input for one supervisor episode."""

    try:
        status = opl_ledger.status(root, bd, runner=run)
        ready = opl_ledger.ready(root, bd, runner=run)
        issues = opl_ledger.list_issues(
            root, bd, statuses=("open", "in_progress", "blocked", "deferred"), runner=run,
        )
        dolt = opl_ledger.dolt_status(root, bd, runner=run)
    except opl_ledger.LedgerError as exc:
        raise WorkflowError(str(exc)) from exc

    ready_ids = {
        str(item["id"])
        for item in ready
        if isinstance(item, dict) and item.get("id") is not None
    }
    compact: list[dict[str, Any]] = []
    errors: list[str] = []
    linear_identifiers: dict[str, str] = {}
    linear_urls: dict[str, str] = {}
    status_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    live_executor_count = 0

    for raw in issues:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            errors.append("unfinished issue payload is missing a string id")
            continue
        issue_id = raw["id"]
        issue_status = raw.get("status")
        status_counts[str(issue_status)] = status_counts.get(str(issue_status), 0) + 1
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        selected_metadata = {
            field: metadata[field]
            for field in SUPERVISOR_METADATA_FIELDS
            if field in metadata
        }
        mode = metadata.get("execution_mode")
        if mode not in SUPERVISOR_EXECUTION_MODES:
            errors.append(f"{issue_id}: missing or unknown metadata.execution_mode")
        else:
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        execution_thread = metadata.get("execution_thread")
        if isinstance(execution_thread, str) and execution_thread.strip():
            live_executor_count += 1
        classification = metadata.get("classification") or metadata.get(
            "task_lifecycle_class"
        )
        if mode == "backlog":
            if classification != "managed_objective":
                errors.append(
                    f"{issue_id}: backlog is reserved for managed_objective"
                )
            if isinstance(execution_thread, str) and execution_thread.strip():
                errors.append(f"{issue_id}: backlog must not bind execution_thread")
        if mode == "on_demand":
            if classification != "interactive_longline":
                errors.append(
                    f"{issue_id}: on_demand is reserved for interactive_longline"
                )
            if isinstance(execution_thread, str) and execution_thread.strip():
                errors.append(f"{issue_id}: on_demand must not bind execution_thread")
        if "remaining" in metadata and not isinstance(metadata["remaining"], list):
            errors.append(f"{issue_id}: metadata.remaining must be a JSON array")
        for field, seen in (
            ("linear_issue_identifier", linear_identifiers),
            ("linear_issue_url", linear_urls),
        ):
            value = metadata.get(field)
            if not isinstance(value, str) or not value:
                continue
            if value in seen:
                errors.append(f"{issue_id}: duplicate {field} with {seen[value]}")
            else:
                seen[value] = issue_id

        dependencies = []
        for dependency in raw.get("dependencies", []):
            if not isinstance(dependency, dict):
                continue
            dependencies.append(
                {
                    key: dependency[key]
                    for key in ("depends_on_id", "type")
                    if dependency.get(key) is not None
                }
            )
        compact.append(
            {
                "id": issue_id,
                "title": raw.get("title"),
                "status": issue_status,
                "priority": raw.get("priority"),
                "issue_type": raw.get("issue_type"),
                "owner": raw.get("owner"),
                "updated_at": raw.get("updated_at"),
                "due_at": raw.get("due_at"),
                "defer_until": raw.get("defer_until"),
                "parent": raw.get("parent"),
                "ready": issue_id in ready_ids,
                "labels": raw.get("labels") if isinstance(raw.get("labels"), list) else [],
                "dependencies": dependencies,
                "metadata": selected_metadata,
            }
        )

    git = executable("git", git_arg)
    git_root = run([git, "rev-parse", "--show-toplevel"], root)
    git_head = run([git, "rev-parse", "HEAD"], root)
    git_branch = run([git, "branch", "--show-current"], root)
    git_status = run([git, "status", "--porcelain=v1", "--branch"], root)
    assert isinstance(git_root, subprocess.CompletedProcess)
    assert isinstance(git_head, subprocess.CompletedProcess)
    assert isinstance(git_branch, subprocess.CompletedProcess)
    assert isinstance(git_status, subprocess.CompletedProcess)

    return {
        "schema": "opl_flow_supervisor_snapshot.v1",
        "instance": str(root),
        "git": {
            "root": git_root.stdout.strip(),
            "head": git_head.stdout.strip(),
            "branch": git_branch.stdout.strip(),
            "status": git_status.stdout.splitlines(),
            "clean": not any(
                line and not line.startswith("##")
                for line in git_status.stdout.splitlines()
            ),
        },
        "dolt": dolt,
        "ledger_status": status,
        "counts": {
            "unfinished": len(compact),
            "ready": len(ready_ids),
            "by_status": dict(sorted(status_counts.items())),
            "by_execution_mode": dict(sorted(mode_counts.items())),
            "semantic": {
                "unfinished_tasks": sum(
                    count
                    for mode, count in mode_counts.items()
                    if mode != "aggregate"
                ),
                "active_objectives": mode_counts.get("active", 0),
                "backlog": mode_counts.get("backlog", 0),
                "live_executors": live_executor_count,
                "monitoring": mode_counts.get("monitoring", 0),
                "on_demand": mode_counts.get("on_demand", 0),
                "aggregate_control_planes": mode_counts.get("aggregate", 0),
            },
            "validation_errors": len(errors),
        },
        "ready_ids": sorted(ready_ids),
        "issues": sorted(compact, key=lambda item: item["id"]),
        "validation_errors": errors,
    }


def workflow_status(
    instance: Path | None,
    bd_arg: str | None,
    fleet_arg: str | None,
    *,
    git_arg: str | None = None,
    gh_arg: str | None = None,
    codex_arg: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema": "opl_flow_workflow_status.v1", "instance": str(instance) if instance else None}
    cwd = instance or Path.cwd()
    payload["git"] = cli_probe("git", cwd, git_arg)
    payload["github"] = github_probe(cwd, gh_arg)
    payload["codex"] = cli_probe("codex", cwd, codex_arg)
    try:
        bd = executable("bd", bd_arg)
        version = opl_ledger.version(cwd, bd, runner=run)
        payload["beads"] = {"available": True, "path": str(Path(bd).resolve()), "version": version}
    except WorkflowError as exc:
        payload["beads"] = {"available": False, "error": str(exc)}
        payload["ledger"] = {"state": "unknown" if instance else "not_configured"}
        payload["linear"] = {"state": "unknown" if instance else "not_configured"}
    else:
        try:
            payload["ledger"] = ledger_probe(instance, bd) if instance else {"state": "not_configured"}
        except WorkflowError as exc:
            payload["ledger"] = {"state": "error", "error": str(exc)}
        payload["linear"] = linear_probe(instance, bd) if instance else {"state": "not_configured"}
    try:
        fleet, owner = fleet_command(instance, fleet_arg)
        executable_path = Path(fleet[1] if fleet[0] == sys.executable else fleet[0])
        payload["fleet"] = {
            "available": True,
            "path": str(executable_path.resolve()),
            "owner": owner,
        }
    except WorkflowError as exc:
        payload["fleet"] = {
            "available": False,
            "error": str(exc),
            "owner": "opl-flow",
        }
    return payload


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--instance")
    status.add_argument("--bd-bin")
    status.add_argument("--fleet-bin")
    status.add_argument("--git-bin")
    status.add_argument("--gh-bin")
    status.add_argument("--codex-bin")
    worker = commands.add_parser("worker", help="validate a carrier-neutral handoff or result")
    worker.add_argument("worker_action", choices=("handoff", "result"))
    worker.add_argument("--handoff-json", required=True)
    worker.add_argument("--result-json")
    ledger = commands.add_parser("ledger")
    ledger_commands = ledger.add_subparsers(dest="ledger_command", required=True)
    init = ledger_commands.add_parser("init")
    init.add_argument("--instance", required=True)
    init.add_argument("--prefix", default="opl")
    init.add_argument("--bd-bin")
    reconcile = ledger_commands.add_parser("reconcile-operations")
    reconcile.add_argument("--instance")
    reconcile.add_argument("--registry", type=Path)
    reconcile.add_argument("--dry-run", action="store_true")
    reconcile.add_argument("--bd-bin")
    supervisor = ledger_commands.add_parser("supervisor-snapshot")
    supervisor.add_argument("--instance")
    supervisor.add_argument("--bd-bin")
    supervisor.add_argument("--git-bin")
    owner = ledger_commands.add_parser("owner")
    owner_commands = owner.add_subparsers(dest="owner_action", required=True)

    def owner_common(command: argparse.ArgumentParser) -> None:
        command.add_argument("bead_id")
        command.add_argument("--instance")
        command.add_argument("--bd-bin")
        command.add_argument("--actor", default="opl-flow")

    owner_status = owner_commands.add_parser("status")
    owner_common(owner_status)
    owner_prepare = owner_commands.add_parser("prepare")
    owner_common(owner_prepare)
    owner_prepare.add_argument("--source-owner", required=True)
    owner_prepare.add_argument("--source-node", required=True)
    owner_prepare.add_argument("--source-executor", required=True)
    owner_prepare.add_argument("--target-owner", required=True)
    owner_prepare.add_argument("--target-node", required=True)
    owner_prepare.add_argument("--target-profile", required=True)
    owner_prepare.add_argument("--instruction-revision", type=int, required=True)
    owner_prepare.add_argument("--instruction-summary", required=True)
    owner_prepare.add_argument("--checkpoint-json", required=True)
    owner_prepare.add_argument("--migration-id")
    owner_preflight = owner_commands.add_parser("preflight")
    owner_common(owner_preflight)
    owner_preflight.add_argument("--migration-id", required=True)
    owner_preflight.add_argument("--workspace-readback-json", required=True)
    owner_preflight.add_argument("--node-readback-json", required=True)
    owner_claim = owner_commands.add_parser("claim")
    owner_common(owner_claim)
    owner_claim.add_argument("--migration-id", required=True)
    owner_claim.add_argument("--target-executor", required=True)
    owner_claim.add_argument("--instruction-revision", type=int, required=True)
    owner_claim.add_argument("--instruction-fingerprint", required=True)
    owner_claim.add_argument("--workspace-readback-json", required=True)
    owner_claim.add_argument("--node-readback-json", required=True)
    owner_verify = owner_commands.add_parser("verify")
    owner_common(owner_verify)
    owner_verify.add_argument("--migration-id", required=True)
    owner_verify.add_argument("--target-executor", required=True)
    owner_verify.add_argument("--workspace-readback-json", required=True)
    owner_verify.add_argument("--node-readback-json", required=True)
    owner_release = owner_commands.add_parser("release")
    owner_common(owner_release)
    owner_release.add_argument("--migration-id", required=True)
    owner_rollback = owner_commands.add_parser("rollback")
    owner_common(owner_rollback)
    owner_rollback.add_argument("--migration-id", required=True)
    fleet = commands.add_parser("fleet", add_help=False)
    fleet.add_argument("--instance")
    fleet.add_argument("--fleet-bin")
    fleet.add_argument("fleet_args", nargs=argparse.REMAINDER)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "worker":
            handoff = opl_execution.validate_handoff(read_json_argument(args.handoff_json, "worker handoff"))
            if args.worker_action == "result":
                if not args.result_json:
                    raise WorkflowError("worker result requires --result-json")
                result = opl_execution.validate_result(read_json_argument(args.result_json, "worker result"), handoff)
            else:
                result = {"handoff": handoff, "binding": opl_execution.handoff_binding(handoff)}
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "status":
            print(
                json.dumps(
                    workflow_status(
                        instance_root(args.instance, required=False),
                        args.bd_bin,
                        args.fleet_bin,
                        git_arg=args.git_bin,
                        gh_arg=args.gh_bin,
                        codex_arg=args.codex_bin,
                    ),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "fleet":
            instance = instance_root(args.instance, required=False)
            fleet, _ = fleet_command(instance, args.fleet_bin)
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            return subprocess.run(
                [*fleet, *(args.fleet_args or ["status"])],
                check=False,
                env=environment,
            ).returncode
        root = instance_root(args.instance)
        assert root is not None
        bd = executable("bd", args.bd_bin)
        if args.ledger_command == "owner":
            result = owner_migration_command(root, bd, args)
        elif args.ledger_command == "init":
            result = init_ledger(root, bd, args.prefix)
        elif args.ledger_command == "reconcile-operations":
            result = reconcile_operations(root, bd, args.registry, dry_run=args.dry_run)
        else:
            result = supervisor_snapshot(root, bd, args.git_bin)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if args.ledger_command == "supervisor-snapshot" and result["validation_errors"]:
            return 3
        return 0
    except (WorkflowError, opl_execution.ExecutionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
