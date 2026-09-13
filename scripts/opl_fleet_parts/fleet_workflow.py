"""Flagship authoring and reviewed Profile delivery through the Framework writer.

The Instance owns selection and review provenance. Flow Git owns reusable
bytes. This module never copies flagship instructions into the public source.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from . import fleet_common as common
from . import fleet_reconcile as reconcile

PROFILE_PATH = "templates/AGENTS.md"
PROJECTION_FIELDS = {"flagship_node_id", "source_agents_sha256", "flow_commit"}


@contextlib.contextmanager
def control_lock():
    root = common.CONTROL_ROOT
    directory = Path(reconcile.git_value(root, ["rev-parse", "--git-common-dir"]).stdout.strip())
    if not directory.is_absolute():
        directory = root / directory
    with (directory / "opl-fleet-workflow.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def workflow_projection() -> dict[str, str] | None:
    projection = reconcile.manifest().get("workflow_projection")
    if projection is None:
        return None
    if (
        not isinstance(projection, dict)
        or set(projection) != PROJECTION_FIELDS
        or not isinstance(projection["flagship_node_id"], str)
        or not common.NODE_ID_PATTERN.fullmatch(projection["flagship_node_id"])
        or not isinstance(projection["source_agents_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", projection["source_agents_sha256"])
        or not isinstance(projection["flow_commit"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", projection["flow_commit"])
    ):
        raise common.FleetError("invalid Instance workflow projection")
    return projection


def published_profile(commit: str) -> str:
    # A private review receipt may pin an older version, never an unpublished
    # branch or uncommitted worktree. Read immutable Git bytes, not the checkout.
    ancestor = reconcile.git_value(
        common.FLOW_ROOT, ["merge-base", "--is-ancestor", commit, "origin/main"], check=False,
    )
    if ancestor.returncode:
        raise common.FleetError("workflow projection is not published on Flow main")
    content = reconcile.git_value(common.FLOW_ROOT, ["show", f"{commit}:{PROFILE_PATH}"]).stdout
    if not content.strip() or "\0" in content or not content.endswith("\n"):
        raise common.FleetError("published workflow Profile is invalid")
    return content


def workflow_status() -> dict[str, Any]:
    registry = reconcile.node_registry()
    node = common.node_identity()
    flagship = registry.get("flagship_node_id")
    projection = workflow_projection()
    target = common.effective_codex_home() / "AGENTS.md"
    regular = target.is_file() and not target.is_symlink()
    digest = common.sha256_file(target) if regular else None
    result: dict[str, Any] = {
        "schema": "opl_fleet_workflow.v1",
        "node_id": node,
        "flagship_node_id": flagship,
        "role": "flagship" if node == flagship else "receiver",
        "authority": "instance_checkout",
        "projection": projection,
        "agents_sha256": digest,
        "state": "UNCONFIGURED",
        "changed": False,
    }
    if not flagship:
        return result
    if not registry["nodes"].get(node, {}).get("approved"):
        return {**result, "state": "UNAPPROVED_NODE"}
    if target.is_symlink() or (target.exists() and not regular):
        return {**result, "state": "LOCAL_CHANGES", "reason": "instructions_not_regular_file"}
    content = published_profile(projection["flow_commit"]) if projection else None
    if result["role"] == "flagship":
        reviewed = bool(projection and projection["flagship_node_id"] == node
                        and projection["source_agents_sha256"] == digest)
        return {**result, "state": "CURRENT" if reviewed else "PROJECTION_REQUIRED"}
    if not projection:
        return {**result, "state": "PROJECTION_REQUIRED"}
    expected = hashlib.sha256(content.encode()).hexdigest()
    result["target_sha256"] = expected
    if digest == expected:
        return {**result, "state": "CURRENT"}
    if not target.exists():
        return {**result, "state": "UPDATE_AVAILABLE"}
    # Only exact, unmodified historical templates can be replaced automatically.
    # Git history is the baseline; no additional managed-file registry/cache.
    blob = reconcile.git_value(common.FLOW_ROOT, ["hash-object", str(target)]).stdout.strip()
    objects = reconcile.git_value(
        common.FLOW_ROOT,
        ["rev-list", "--objects", projection["flow_commit"], "--", PROFILE_PATH],
    ).stdout.splitlines()
    known_template = f"{blob} {PROFILE_PATH}" in objects
    return {**result, "state": "UPDATE_AVAILABLE" if known_template else "LOCAL_CHANGES"}


def assert_published_control() -> None:
    # An unpushed selection/review is a proposal, not fleet-wide authority.
    for name in ("nodes.json", "fleet.json"):
        published = reconcile.git_value(
            common.CONTROL_ROOT, ["show", f"origin/main:fleet/{name}"],
        ).stdout
        if common.read_json(common.CONTROL_ROOT / name) != json.loads(published):
            raise common.FleetError("publish the Instance flagship/projection change to main before sync")


def reconcile_workflow() -> dict[str, Any]:
    assert_published_control()
    result = workflow_status()
    if result["state"] != "UPDATE_AVAILABLE" or result["role"] == "flagship":
        return result
    content = published_profile(result["projection"]["flow_commit"])
    # Recheck selection and local bytes immediately before entering the owner
    # writer. Framework owns expected-hash checking, backup and atomic replace.
    if workflow_status() != result:
        raise common.FleetError("workflow state changed before apply; rerun sync")
    succeeded = apply_profile(content, result["agents_sha256"])
    verified = workflow_status()
    if not succeeded or verified["state"] != "CURRENT":
        return {**verified, "state": "APPLY_FAILED", "reason": "framework_write_or_readback_failed"}
    return {**verified, "changed": True, "writer": "framework.codex_user_instructions_set"}


def apply_profile(content: str, expected_sha256: str | None) -> bool:
    command = shutil.which("opl")
    if not command:
        return False
    payload = json.dumps({"content": content, "expected_sha256": expected_sha256})
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(common.effective_codex_home())
    applied = subprocess.run(
        [command, "app", "action", "execute", "--action", "codex_user_instructions_set",
         "--payload", payload, "--json"],
        env=environment, text=True, capture_output=True, timeout=120, check=False,
    )
    # Do not log the writer's content-bearing response or private instructions.
    return applied.returncode == 0


def set_flagship(node_id: str, *, expected_current: str) -> dict[str, Any]:
    with control_lock():
        registry = reconcile.node_registry()
        previous = registry.get("flagship_node_id")
        if (previous or "none") != expected_current:
            raise common.FleetError("flagship changed; reload before switching")
        if not registry["nodes"].get(node_id, {}).get("approved"):
            raise common.FleetError("flagship must be an approved Fleet node")
        registry["flagship_node_id"] = node_id
        common.atomic_json(common.CONTROL_ROOT / "nodes.json", registry, sort_keys=False, ensure_ascii=False)
    return {"flagship_node_id": node_id, "previous_flagship_node_id": previous,
            "state": "PUBLISH_REQUIRED", "authority": "instance_checkout"}


def record_projection(commit: str, *, source_sha256: str) -> dict[str, Any]:
    with control_lock():
        registry = reconcile.node_registry()
        node = common.node_identity()
        if registry.get("flagship_node_id") != node:
            raise common.FleetError("only the selected flagship can record a workflow projection")
        reconcile.git_value(common.CONTROL_ROOT, ["fetch", "origin", "main"])
        published = json.loads(reconcile.git_value(
            common.CONTROL_ROOT, ["show", "origin/main:fleet/nodes.json"],
        ).stdout)
        if published.get("flagship_node_id") != node:
            raise common.FleetError("flagship selection is not current on Instance main")
        reconcile.git_value(common.FLOW_ROOT, ["fetch", "origin", "main"])
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise common.FleetError("an exact Flow commit is required")
        published_profile(commit)
        target = common.effective_codex_home() / "AGENTS.md"
        if (target.is_symlink() or not target.is_file() or not target.read_bytes().strip()
                or common.sha256_file(target) != source_sha256):
            raise common.FleetError("flagship instructions changed since semantic review")
        spec = reconcile.manifest()
        spec["workflow_projection"] = {
            "flagship_node_id": node, "source_agents_sha256": source_sha256, "flow_commit": commit,
        }
        common.atomic_json(common.CONTROL_ROOT / "fleet.json", spec, sort_keys=False, ensure_ascii=False)
    return {"projection": spec["workflow_projection"], "state": "PUBLISH_REQUIRED",
            "authority": "instance_checkout"}


def workflow_command(args) -> dict[str, Any]:
    if args.workflow_action == "record-projection":
        return record_projection(args.flow_commit, source_sha256=args.source_sha256)
    if args.workflow_action == "sync":
        previous = reconcile.checkout_commit(common.FLOW_ROOT)
        revision = reconcile.update_flow()
        reconcile.restart_after_flow_update(previous, revision)
        reconcile.update_control()
        result = reconcile_workflow()
        common.atomic_json(common.STATE_ROOT / "workflow.json", result)
        return result
    return workflow_status()
