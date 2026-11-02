"""Instance configuration and Git primitives shared by Fleet operations.

This module depends only on fleet_common. It never invokes reconciliation,
Profile delivery, capacity scheduling, or task-state operations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import re
import subprocess
import sys

from . import fleet_common
from .fleet_common import (
    AVAILABILITY_POLICIES, FLOW_ROOT, FleetError, LEASE_WORKLOAD_CLASSES,
    ROLE_PATTERN, normalize_node_id, read_json, run,
)

def manifest() -> dict[str, Any]:
    payload = read_json(fleet_common.CONTROL_ROOT / "fleet.json")
    if payload.get("schema") != "codex_fleet_control.v1":
        raise FleetError("unsupported fleet manifest")
    runner = payload.get("runner")
    schedule = payload.get("schedule")
    if not isinstance(runner, dict) or not isinstance(
        runner.get("source_path", "skills/codex-machine-sync"), str
    ):
        raise FleetError("fleet runner definition is incomplete")
    repository_owner = payload.get("repository_owner")
    if not isinstance(repository_owner, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,100}", repository_owner
    ):
        raise FleetError("fleet repository owner is invalid")
    if not isinstance(schedule, dict) or not isinstance(
        schedule.get("service_id"), str
    ):
        raise FleetError("fleet schedule is incomplete")
    return payload

def managed_repository_owner() -> str:
    return str(manifest()["repository_owner"])

def node_registry(*, control_root: Path | None = None) -> dict[str, Any]:
    root = control_root or fleet_common.CONTROL_ROOT
    payload = read_json(root / "nodes.json")
    if set(payload) - {"flagship_node_id"} != {
        "schema",
        "nodes",
        "specialized_software",
        "runner_bindings",
        "runner_roles",
        "runner_role_workloads",
        "desired_unregistered",
    }:
        raise FleetError("node registry fields are not allowed")
    if payload.get("schema") != "codex_fleet_nodes.v1":
        raise FleetError("unsupported node registry")
    nodes = payload.get("nodes")
    definitions = payload.get("specialized_software")
    runner_bindings = payload.get("runner_bindings")
    runner_roles = payload.get("runner_roles")
    runner_role_workloads = payload.get("runner_role_workloads")
    desired_unregistered = payload.get("desired_unregistered")
    if (
        not isinstance(nodes, dict)
        or not isinstance(definitions, list)
        or not isinstance(runner_bindings, dict)
        or not isinstance(runner_roles, dict)
        or not isinstance(runner_role_workloads, dict)
        or not isinstance(desired_unregistered, list)
    ):
        raise FleetError("node registry is incomplete")
    flagship = payload.get("flagship_node_id")
    if flagship is not None and (
        not isinstance(flagship, str)
        or not isinstance(nodes.get(flagship), dict)
        or nodes[flagship].get("approved") is not True
    ):
        raise FleetError("flagship must name one approved Fleet node")
    for node_id, policy in nodes.items():
        if normalize_node_id(str(node_id)) != node_id or not isinstance(policy, dict):
            raise FleetError(f"invalid node registry entry: {node_id!r}")
        if set(policy) != {
            "approved",
            "display_name",
            "availability_policy",
            "labels",
            "notes",
            "scheduling",
        }:
            raise FleetError(f"node policy fields are not allowed: {node_id}")
        if not isinstance(policy["approved"], bool):
            raise FleetError(f"node approval is invalid: {node_id}")
        if not isinstance(policy["display_name"], str) or len(policy["display_name"]) > 80:
            raise FleetError(f"node display name is invalid: {node_id}")
        if policy["availability_policy"] not in AVAILABILITY_POLICIES:
            raise FleetError(f"node availability policy is invalid: {node_id}")
        labels = policy["labels"]
        notes = policy["notes"]
        if (
            not isinstance(labels, list)
            or any(not re.fullmatch(r"[a-z0-9-]{1,40}", str(item)) for item in labels)
            or not isinstance(notes, list)
        ):
            raise FleetError(f"node labels or notes are invalid: {node_id}")
        for note in notes:
            if (
                not isinstance(note, dict)
                or set(note) != {"category", "summary"}
                or not re.fullmatch(r"[a-z0-9-]{1,40}", str(note["category"]))
                or not isinstance(note["summary"], str)
                or len(note["summary"]) > 300
            ):
                raise FleetError(f"node note is invalid: {node_id}")
        scheduling = policy["scheduling"]
        if (
            not isinstance(scheduling, dict)
            or set(scheduling)
            != {
                "requires_ac",
                "min_free_gb",
                "occupancy_required",
                "idle_threshold_seconds",
                "preferred_for",
                "work_volume_required",
            }
            or not isinstance(scheduling["requires_ac"], bool)
            or not isinstance(scheduling["min_free_gb"], int)
            or not 0 <= scheduling["min_free_gb"] <= 10_000
            or not isinstance(scheduling["occupancy_required"], bool)
            or not isinstance(scheduling["work_volume_required"], bool)
            or not isinstance(scheduling["idle_threshold_seconds"], int)
            or not 60 <= scheduling["idle_threshold_seconds"] <= 86_400
            or not isinstance(scheduling["preferred_for"], list)
            or any(
                not re.fullmatch(r"[a-z0-9-]{1,40}", str(item))
                for item in scheduling["preferred_for"]
            )
        ):
            raise FleetError(f"node scheduling policy is invalid: {node_id}")
    for definition in definitions:
        if (
            not isinstance(definition, dict)
            or set(definition)
            != {"id", "purpose", "windows_display_name_patterns"}
            or not re.fullmatch(r"[a-z0-9-]{1,60}", str(definition["id"]))
            or not isinstance(definition["purpose"], str)
            or len(definition["purpose"]) > 160
            or not isinstance(definition["windows_display_name_patterns"], list)
            or any(
                not isinstance(item, str) or not 1 <= len(item) <= 80
                for item in definition["windows_display_name_patterns"]
            )
        ):
            raise FleetError("specialized software definition is invalid")
    for role, node_ids in runner_roles.items():
        if (
            not ROLE_PATTERN.fullmatch(str(role))
            or not isinstance(node_ids, list)
            or not node_ids
            or node_ids != sorted(set(node_ids))
            or any(node_id not in nodes for node_id in node_ids)
        ):
            raise FleetError(f"runner role is invalid: {role}")
    for role, workload_classes in runner_role_workloads.items():
        if (
            role not in runner_roles
            or not isinstance(workload_classes, list)
            or not workload_classes
            or workload_classes != sorted(set(workload_classes))
            or any(item not in LEASE_WORKLOAD_CLASSES for item in workload_classes)
        ):
            raise FleetError(f"runner role workload policy is invalid: {role}")
    for role, binding in runner_bindings.items():
        if (
            role not in runner_roles
            or not isinstance(binding, dict)
            or set(binding)
            != {
                "launch_mode",
                "min_memory_gb",
                "node_id",
                "repository",
                "required_features",
                "runner_name",
            }
            or binding["launch_mode"] not in {
                "ssh-session",
                "launchagent",
                "windows-session-task",
            }
            or binding["node_id"] not in runner_roles[role]
            or not re.fullmatch(
                r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}",
                str(binding["repository"]),
            )
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}",
                str(binding["runner_name"]),
            )
            or not isinstance(binding["required_features"], list)
            or binding["required_features"]
            != sorted(set(binding["required_features"]))
            or any(
                not re.fullmatch(r"[a-z0-9-]{1,40}", str(item))
                for item in binding["required_features"]
            )
            or not isinstance(binding["min_memory_gb"], int)
            or not 0 <= binding["min_memory_gb"] <= 10_000
            or (
                binding["launch_mode"] == "windows-session-task"
                and "windows" not in nodes[binding["node_id"]]["labels"]
            )
        ):
            raise FleetError(f"runner binding is invalid: {role}")
    if (
        desired_unregistered != sorted(set(desired_unregistered))
        or any(node_id not in nodes for node_id in desired_unregistered)
        or set(desired_unregistered).intersection(
            node_id
            for node_ids in runner_roles.values()
            for node_id in node_ids
        )
    ):
        raise FleetError("desired-unregistered nodes are invalid")
    return payload

def control_commit() -> str:
    return run(["git", "-C", str(fleet_common.CONTROL_ROOT), "rev-parse", "HEAD"]).stdout.strip()

def checkout_commit(root: Path) -> str:
    return run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()

def update_checkout(root: Path, *, label: str) -> str:
    if run(["git", "-C", str(root), "status", "--porcelain"]).stdout.strip():
        raise FleetError(f"{label} checkout is dirty")
    run(["git", "-C", str(root), "fetch", "origin", "main"])
    run(["git", "-C", str(root), "checkout", "main"])
    run(["git", "-C", str(root), "merge", "--ff-only", "origin/main"])
    return checkout_commit(root)

def update_flow() -> str:
    return update_checkout(FLOW_ROOT, label="OPL Flow")

def update_control() -> str:
    return update_checkout(fleet_common.CONTROL_ROOT, label="OPL Instance")

def github_repository_from_remote(
    remote: str,
    *,
    expected_owner: str | None = None,
) -> str | None:
    match = re.fullmatch(
        r"(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/|"
        r"ssh://git@ssh\.github\.com:443/)"
        r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        remote.strip(),
    )
    if match:
        owner = match.group("owner")
        if expected_owner is not None and owner.casefold() != expected_owner.casefold():
            return None
        return f"{owner}/{match.group('repo')}"
    if expected_owner is None:
        repo = Path(remote.removesuffix("/")).name.removesuffix(".git")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
            return repo
    return None

def git_value(
    repository: Path,
    arguments: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return run(
        ["git", "-C", str(repository), *arguments],
        check=check,
        timeout=timeout,
    )

def restart_after_flow_update(previous: str, current: str) -> None:
    if previous == current:
        return
    script = fleet_common.FLEET_ENTRY_SCRIPT
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[1:]])

def github_head(repository: str, branch: str) -> str:
    return run(
        ["gh", "api", f"repos/{repository}/commits/{branch}", "--jq", ".sha"]
    ).stdout.strip()
