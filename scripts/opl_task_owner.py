"""Pure state transitions for Beads-backed execution-owner migration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
import hashlib
import json
import re
import uuid


MIGRATION_SCHEMA = "opl_task_owner_migration.v1"
MIGRATION_STATES = {
    "source_checkpointed",
    "target_preflighted",
    "target_acknowledged",
    "target_verified",
    "completed",
    "blocked",
    "unknown",
    "rolled_back",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NODE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
PROFILE_ID = NODE_ID
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class TaskOwnerError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def objective_fingerprint(issue: dict[str, Any]) -> str:
    return digest(
        {
            field: issue.get(field)
            for field in (
                "id",
                "title",
                "description",
                "acceptance_criteria",
                "external_ref",
                "parent",
            )
        }
    )


def instruction_fingerprint(revision: int, summary: str) -> str:
    if not isinstance(revision, int) or revision < 1 or not summary.strip():
        raise TaskOwnerError("instruction revision and summary are required")
    return digest({"revision": revision, "summary": summary.strip()})


def _identity(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 128:
        raise TaskOwnerError(f"{label} is invalid")
    return text


def _relative(value: Any, label: str) -> str:
    text = str(value or "").strip()
    path = PurePosixPath(text)
    if (
        not text
        or text.startswith("/")
        or "\\" in text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise TaskOwnerError(f"{label} must be repository-relative")
    return text


def validate_checkpoint(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "write_set",
        "remaining",
        "next_action",
        "git_recovery",
    }:
        raise TaskOwnerError("source checkpoint fields are invalid")
    write_set = value["write_set"]
    remaining = value["remaining"]
    recovery = value["git_recovery"]
    next_action = str(value["next_action"] or "").strip()
    if (
        not isinstance(write_set, list)
        or not write_set
        or write_set != sorted(set(write_set))
        or not isinstance(remaining, list)
        or any(not isinstance(item, str) or not item.strip() for item in remaining)
        or not isinstance(recovery, list)
        or not next_action
    ):
        raise TaskOwnerError("source checkpoint content is invalid")
    normalized_write_set = [_relative(item, "write-set path") for item in write_set]
    normalized_recovery: list[dict[str, str]] = []
    seen_repositories: set[str] = set()
    for entry in recovery:
        if not isinstance(entry, dict) or set(entry) != {
            "repository",
            "ref",
            "commit",
            "tree",
        }:
            raise TaskOwnerError("git recovery entry fields are invalid")
        repository = str(entry["repository"])
        ref = str(entry["ref"] or "").strip()
        if (
            not REPOSITORY.fullmatch(repository)
            or repository in seen_repositories
            or not ref
            or len(ref) > 200
            or not SHA40.fullmatch(str(entry["commit"]))
            or not SHA40.fullmatch(str(entry["tree"]))
        ):
            raise TaskOwnerError("git recovery entry is invalid")
        seen_repositories.add(repository)
        normalized_recovery.append(
            {
                "repository": repository,
                "ref": ref,
                "commit": str(entry["commit"]),
                "tree": str(entry["tree"]),
            }
        )
    return {
        "recorded_at": now(),
        "write_set": normalized_write_set,
        "remaining": [item.strip() for item in remaining],
        "next_action": next_action,
        "git_recovery": normalized_recovery,
    }


def validate_workspace_preflight(value: Any, *, profile_id: str, node_id: str) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or value.get("schema") != "opl_fleet_workspace_readback.v1"
        or value.get("profile_id") != profile_id
        or node_id not in value.get("node_ids", [])
        or value.get("state") != "CURRENT"
        or value.get("claim_ready") is not True
        or value.get("fresh_fetch") is not True
        or value.get("fresh_github") is not True
    ):
        raise TaskOwnerError("target workspace is not claim-ready")
    fingerprints = {
        "workspace_fingerprint": value.get("profile_fingerprint"),
        "environment_fingerprint": value.get("environment_fingerprint"),
        "repository_fingerprint": value.get("repository_fingerprint"),
    }
    if any(not isinstance(item, str) or not SHA256.fullmatch(item) for item in fingerprints.values()):
        raise TaskOwnerError("target workspace fingerprints are invalid")
    return {"checked_at": str(value.get("observed_at") or now()), **fingerprints}


def validate_node_admission(
    value: Any,
    *,
    node_id: str,
    bead_id: str,
) -> dict[str, str]:
    lease = value.get("lease") if isinstance(value, dict) else None
    capacity_owned = isinstance(lease, dict) and lease.get("owner_task") == bead_id
    if (
        not isinstance(value, dict)
        or value.get("schema") != "codex_fleet_doctor.v1"
        or value.get("node_id") != node_id
        or value.get("admission_ready") is not True
        or (value.get("ready_for_dispatch") is not True and not capacity_owned)
        or value.get("receipt_state") != "CURRENT"
        or value.get("control_current") is not True
    ):
        raise TaskOwnerError("target node is not admitted for owner migration")
    control_commit = value.get("current_control_commit")
    if not isinstance(control_commit, str) or not SHA40.fullmatch(control_commit):
        raise TaskOwnerError("target node control revision is invalid")
    return {
        "node_checked_at": str(value.get("checked_at") or now()),
        "control_commit": control_commit,
    }


def _transition(receipt: dict[str, Any], state: str, actor: str) -> None:
    if state not in MIGRATION_STATES:
        raise TaskOwnerError("migration state is invalid")
    receipt["state"] = state
    receipt["transitions"].append(
        {"state": state, "recorded_at": now(), "actor": _identity(actor, "actor")}
    )


def current_claim(
    metadata: dict[str, Any],
    *,
    source_owner_id: str,
    source_node_id: str,
    source_executor_handle: str,
) -> dict[str, Any]:
    existing = metadata.get("opl_owner_claim")
    expected = {
        "owner_id": _identity(source_owner_id, "source owner"),
        "node_id": _identity(source_node_id, "source node"),
        "executor_handle": _identity(source_executor_handle, "source executor"),
    }
    if not NODE_ID.fullmatch(expected["node_id"]):
        raise TaskOwnerError("source node is invalid")
    if existing is None:
        execution_owner = metadata.get("execution_owner")
        if (
            metadata.get("execution_thread") != expected["executor_handle"]
            or execution_owner not in {None, expected["owner_id"]}
        ):
            raise TaskOwnerError("source executor does not match the Bead")
        return {"generation": 0, **expected}
    if (
        not isinstance(existing, dict)
        or set(existing) != {"generation", "owner_id", "node_id", "executor_handle"}
        or not isinstance(existing.get("generation"), int)
        or existing["generation"] < 0
    ):
        raise TaskOwnerError("current execution owner claim is invalid")
    if any(existing.get(field) != value for field, value in expected.items()):
        raise TaskOwnerError("current execution owner claim changed")
    return deepcopy(existing)


def prepare(
    issue: dict[str, Any],
    *,
    source_owner_id: str,
    source_node_id: str,
    source_executor_handle: str,
    target_owner_id: str,
    target_node_id: str,
    target_profile_id: str,
    instruction_revision: int,
    instruction_summary: str,
    checkpoint: dict[str, Any],
    actor: str,
    migration_id: str | None = None,
) -> dict[str, Any]:
    metadata = deepcopy(issue.get("metadata") or {})
    active = metadata.get("opl_owner_migration")
    if isinstance(active, dict) and active.get("state") not in {"completed", "rolled_back"}:
        raise TaskOwnerError("another owner migration is active")
    claim = current_claim(
        metadata,
        source_owner_id=source_owner_id,
        source_node_id=source_node_id,
        source_executor_handle=source_executor_handle,
    )
    target_node = _identity(target_node_id, "target node")
    profile_id = _identity(target_profile_id, "target profile")
    if not NODE_ID.fullmatch(target_node) or not PROFILE_ID.fullmatch(profile_id):
        raise TaskOwnerError("target node or profile is invalid")
    identifier = migration_id or str(uuid.uuid4())
    try:
        uuid.UUID(identifier)
    except ValueError as exc:
        raise TaskOwnerError("migration id is invalid") from exc
    summary = instruction_summary.strip()
    receipt = {
        "schema": MIGRATION_SCHEMA,
        "migration_id": identifier,
        "generation": int((active or {}).get("generation", 0)) + 1,
        "state": "source_checkpointed",
        "objective": {
            "bead_id": str(issue["id"]),
            "fingerprint": objective_fingerprint(issue),
        },
        "instruction": {
            "revision": instruction_revision,
            "fingerprint": instruction_fingerprint(instruction_revision, summary),
            "summary": summary,
        },
        "source_claim": claim,
        "source_checkpoint": validate_checkpoint(checkpoint),
        "target": {
            "node_id": target_node,
            "profile_id": profile_id,
            "owner_id": _identity(target_owner_id, "target owner"),
            "executor_handle": None,
            "preflight": None,
        },
        "transitions": [],
    }
    _transition(receipt, "source_checkpointed", actor)
    metadata["opl_owner_claim"] = claim
    metadata["opl_owner_migration"] = receipt
    metadata["owner_mutation_frozen"] = True
    return metadata


def preflight(
    issue: dict[str, Any],
    *,
    migration_id: str,
    workspace_readback: dict[str, Any],
    node_readback: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    metadata = deepcopy(issue.get("metadata") or {})
    receipt = metadata.get("opl_owner_migration")
    if not isinstance(receipt, dict) or receipt.get("migration_id") != migration_id:
        raise TaskOwnerError("owner migration does not match")
    if receipt.get("state") == "target_preflighted":
        return metadata
    if receipt.get("state") != "source_checkpointed":
        raise TaskOwnerError("owner migration is not ready for target preflight")
    if objective_fingerprint(issue) != receipt["objective"]["fingerprint"]:
        raise TaskOwnerError("objective changed after source checkpoint")
    target = receipt["target"]
    target["preflight"] = {
        **validate_workspace_preflight(
        workspace_readback,
        profile_id=target["profile_id"],
        node_id=target["node_id"],
        ),
        **validate_node_admission(
            node_readback,
            node_id=target["node_id"],
            bead_id=receipt["objective"]["bead_id"],
        ),
    }
    _transition(receipt, "target_preflighted", actor)
    return metadata


def claim(
    issue: dict[str, Any],
    *,
    migration_id: str,
    target_executor_handle: str,
    expected_instruction_revision: int,
    expected_instruction_fingerprint: str,
    workspace_readback: dict[str, Any],
    node_readback: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    metadata = deepcopy(issue.get("metadata") or {})
    receipt = metadata.get("opl_owner_migration")
    if not isinstance(receipt, dict) or receipt.get("migration_id") != migration_id:
        raise TaskOwnerError("owner migration does not match")
    target_handle = _identity(target_executor_handle, "target executor")
    if receipt.get("state") in {"target_acknowledged", "target_verified", "completed"}:
        if receipt["target"].get("executor_handle") == target_handle:
            return metadata
        raise TaskOwnerError("owner migration was claimed by another executor")
    if receipt.get("state") != "target_preflighted":
        raise TaskOwnerError("owner migration is not ready to claim")
    instruction = receipt["instruction"]
    if (
        instruction["revision"] != expected_instruction_revision
        or instruction["fingerprint"] != expected_instruction_fingerprint
    ):
        raise TaskOwnerError("instruction revision or fingerprint changed")
    source_claim = receipt["source_claim"]
    if metadata.get("opl_owner_claim") != source_claim:
        raise TaskOwnerError("execution owner claim changed")
    target = receipt["target"]
    fresh_preflight = validate_workspace_preflight(
        workspace_readback,
        profile_id=target["profile_id"],
        node_id=target["node_id"],
    )
    if any(
        fresh_preflight[field] != target["preflight"][field]
        for field in (
            "workspace_fingerprint",
            "environment_fingerprint",
            "repository_fingerprint",
        )
    ):
        raise TaskOwnerError("target workspace changed after preflight")
    fresh_node = validate_node_admission(
        node_readback,
        node_id=target["node_id"],
        bead_id=receipt["objective"]["bead_id"],
    )
    if fresh_node["control_commit"] != target["preflight"]["control_commit"]:
        raise TaskOwnerError("target node control revision changed after preflight")
    target["preflight"] = fresh_preflight
    target["preflight"].update(fresh_node)
    target["executor_handle"] = target_handle
    metadata["opl_owner_claim"] = {
        "generation": source_claim["generation"] + 1,
        "owner_id": target["owner_id"],
        "node_id": target["node_id"],
        "executor_handle": target_handle,
    }
    metadata["last_execution_thread"] = source_claim["executor_handle"]
    metadata["execution_owner"] = target["owner_id"]
    metadata["execution_thread"] = target_handle
    metadata["execution_node"] = target["node_id"]
    _transition(receipt, "target_acknowledged", actor)
    return metadata


def verify_target(
    issue: dict[str, Any],
    *,
    migration_id: str,
    target_executor_handle: str,
    workspace_readback: dict[str, Any],
    node_readback: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    metadata = deepcopy(issue.get("metadata") or {})
    receipt = metadata.get("opl_owner_migration")
    claim_value = metadata.get("opl_owner_claim")
    if not isinstance(receipt, dict) or receipt.get("migration_id") != migration_id:
        raise TaskOwnerError("owner migration does not match")
    if receipt.get("state") in {"target_verified", "completed"}:
        return metadata
    target = receipt["target"]
    expected_claim = {
        "generation": receipt["source_claim"]["generation"] + 1,
        "owner_id": target["owner_id"],
        "node_id": target["node_id"],
        "executor_handle": target_executor_handle,
    }
    if (
        receipt.get("state") != "target_acknowledged"
        or claim_value != expected_claim
        or metadata.get("execution_owner") != target["owner_id"]
        or metadata.get("execution_thread") != target_executor_handle
        or target.get("executor_handle") != target_executor_handle
    ):
        raise TaskOwnerError("target execution owner readback does not match")
    fresh_preflight = validate_workspace_preflight(
        workspace_readback,
        profile_id=target["profile_id"],
        node_id=target["node_id"],
    )
    if any(
        fresh_preflight[field] != target["preflight"][field]
        for field in (
            "workspace_fingerprint",
            "environment_fingerprint",
            "repository_fingerprint",
        )
    ):
        raise TaskOwnerError("target workspace changed after claim")
    fresh_node = validate_node_admission(
        node_readback,
        node_id=target["node_id"],
        bead_id=receipt["objective"]["bead_id"],
    )
    if fresh_node["control_commit"] != target["preflight"]["control_commit"]:
        raise TaskOwnerError("target node control revision changed after claim")
    target["preflight"] = fresh_preflight
    target["preflight"].update(fresh_node)
    _transition(receipt, "target_verified", actor)
    return metadata


def release_source(
    issue: dict[str, Any],
    *,
    migration_id: str,
    actor: str,
) -> dict[str, Any]:
    metadata = deepcopy(issue.get("metadata") or {})
    receipt = metadata.get("opl_owner_migration")
    if not isinstance(receipt, dict) or receipt.get("migration_id") != migration_id:
        raise TaskOwnerError("owner migration does not match")
    if receipt.get("state") == "completed":
        return metadata
    if receipt.get("state") != "target_verified":
        raise TaskOwnerError("owner migration is not verified")
    _transition(receipt, "completed", actor)
    metadata["owner_mutation_frozen"] = False
    return metadata


def rollback(
    issue: dict[str, Any],
    *,
    migration_id: str,
    actor: str,
) -> dict[str, Any]:
    metadata = deepcopy(issue.get("metadata") or {})
    receipt = metadata.get("opl_owner_migration")
    if not isinstance(receipt, dict) or receipt.get("migration_id") != migration_id:
        raise TaskOwnerError("owner migration does not match")
    if receipt.get("state") == "rolled_back":
        return metadata
    if receipt.get("state") not in {"source_checkpointed", "target_preflighted", "blocked"}:
        raise TaskOwnerError("owner migration cannot roll back after target claim")
    if metadata.get("opl_owner_claim") != receipt["source_claim"]:
        raise TaskOwnerError("target mutation was observed; start a reverse migration")
    _transition(receipt, "rolled_back", actor)
    metadata["owner_mutation_frozen"] = False
    return metadata


def public_status(issue: dict[str, Any]) -> dict[str, Any]:
    metadata = issue.get("metadata") or {}
    receipt = metadata.get("opl_owner_migration")
    return {
        "schema": "opl_task_owner_migration_status.v1",
        "bead_id": issue.get("id"),
        "claim": metadata.get("opl_owner_claim"),
        "migration": receipt,
        "mutation_frozen": metadata.get("owner_mutation_frozen") is True,
    }
