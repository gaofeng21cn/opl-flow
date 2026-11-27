"""Flagship authoring and reviewed Profile delivery through the Framework writer.

The Instance owns selection and review provenance. Flow Git owns reusable
bytes. This module never copies flagship instructions into the public source.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr
from . import fleet_common as common
from . import fleet_control as control

PROFILE_PATH = "templates/AGENTS.md"
PROJECTION_FIELDS = {"flagship_node_id", "source_agents_sha256", "flow_commit"}


class _WorkflowProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flagship_node_id: Annotated[StrictStr, Field(pattern=common.NODE_ID_PATTERN.pattern)]
    source_agents_sha256: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
    flow_commit: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{40}$")]


@contextlib.contextmanager
def control_lock():
    root = common.CONTROL_ROOT
    directory = Path(control.git_value(root, ["rev-parse", "--git-common-dir"]).stdout.strip())
    if not directory.is_absolute():
        directory = root / directory
    with common.runtime.file_lock(directory / "opl-fleet-workflow.lock", mode=0o600):
        yield


def workflow_projection() -> dict[str, str] | None:
    projection = control.manifest().get("workflow_projection")
    if projection is None:
        return None
    common.runtime.validate_model(
        _WorkflowProjectionModel,
        projection,
        error_cls=common.FleetError,
        message="invalid Instance workflow projection",
    )
    return projection


def published_profile(commit: str) -> str:
    # A private review receipt may pin an older version, never an unpublished
    # branch or uncommitted worktree. Read immutable Git bytes, not the checkout.
    ancestor = control.git_value(
        common.FLOW_ROOT, ["merge-base", "--is-ancestor", commit, "origin/main"], check=False,
    )
    if ancestor.returncode:
        raise common.FleetError("workflow projection is not published on Flow main")
    content = control.git_value(common.FLOW_ROOT, ["show", f"{commit}:{PROFILE_PATH}"]).stdout
    if not content.strip() or "\0" in content or not content.endswith("\n"):
        raise common.FleetError("published workflow Profile is invalid")
    return content


def workflow_status() -> dict[str, Any]:
    registry = control.node_registry()
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
    blob = control.git_value(common.FLOW_ROOT, ["hash-object", str(target)]).stdout.strip()
    objects = control.git_value(
        common.FLOW_ROOT,
        ["rev-list", "--objects", projection["flow_commit"], "--", PROFILE_PATH],
    ).stdout.splitlines()
    known_template = f"{blob} {PROFILE_PATH}" in objects
    return {**result, "state": "UPDATE_AVAILABLE" if known_template else "LOCAL_CHANGES"}


def assert_published_control() -> None:
    # An unpushed selection/review is a proposal, not fleet-wide authority.
    for name in ("nodes.json", "fleet.json"):
        published = control.git_value(
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
    if (verified["state"] != "CURRENT" or verified.get("projection") != result["projection"]
            or verified["agents_sha256"] != result["target_sha256"]):
        return {**verified, "state": "APPLY_FAILED", "reason": "framework_write_or_readback_failed"}
    if not succeeded:
        return {**verified, "changed": True, "reason": "reviewed_profile_confirmed_after_writer_error"}
    return {**verified, "changed": True, "writer": "framework.codex_user_instructions_set"}


def apply_profile(content: str, expected_sha256: str | None) -> bool:
    command = shutil.which("opl")
    if not command:
        return False
    target = common.effective_codex_home() / "AGENTS.md"
    environment = {**os.environ, "CODEX_HOME": str(target.parent)}
    payload = {"content": content, "expected_sha256": expected_sha256}
    try:
        version = subprocess.run(
            [command, "--version", "--json"], env=environment, text=True,
            capture_output=True, timeout=30, check=False,
        )
        if version.returncode != 0:
            return False
        raw = version.stdout.strip()
        if re.fullmatch(r"0\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?", raw):
            # Legacy Framework reports a plain package version even with --json.
            args = [command, "app", "action", "execute", "--action", "codex_user_instructions_set",
                    "--payload", json.dumps(payload), "--json"]
            applied = subprocess.run(args, env=environment, text=True, capture_output=True,
                                     timeout=120, check=False)
        else:
            metadata = json.loads(raw)
            if not isinstance(metadata, dict) or metadata.get("api_version") != "2.0":
                return False
            payload["expected_path"] = str(target)
            applied = subprocess.run(
                [command, "daemon", "apply-codex-profile", "--json"], input=json.dumps(payload),
                env=environment, text=True, capture_output=True, timeout=120, check=False,
            )
        # Caller reads back the selected file. Never retry an unknown write.
        return applied.returncode == 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def set_flagship(node_id: str, *, expected_current: str) -> dict[str, Any]:
    with control_lock():
        registry = control.node_registry()
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
        registry = control.node_registry()
        node = common.node_identity()
        if registry.get("flagship_node_id") != node:
            raise common.FleetError("only the selected flagship can record a workflow projection")
        control.git_value(common.CONTROL_ROOT, ["fetch", "origin", "main"])
        published = json.loads(control.git_value(
            common.CONTROL_ROOT, ["show", "origin/main:fleet/nodes.json"],
        ).stdout)
        if published.get("flagship_node_id") != node:
            raise common.FleetError("flagship selection is not current on Instance main")
        control.git_value(common.FLOW_ROOT, ["fetch", "origin", "main"])
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise common.FleetError("an exact Flow commit is required")
        published_profile(commit)
        target = common.effective_codex_home() / "AGENTS.md"
        if (target.is_symlink() or not target.is_file() or not target.read_bytes().strip()
                or common.sha256_file(target) != source_sha256):
            raise common.FleetError("flagship instructions changed since semantic review")
        spec = control.manifest()
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
        previous = control.checkout_commit(common.FLOW_ROOT)
        revision = control.update_flow()
        control.restart_after_flow_update(previous, revision)
        control.update_control()
        result = reconcile_workflow()
        common.atomic_json(common.STATE_ROOT / "workflow.json", result)
        return result
    return workflow_status()
