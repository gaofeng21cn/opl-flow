#!/usr/bin/env python3
"""Validate an OPL Flow start onboarding receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA = "opl_flow_start_onboarding_receipt.v1"
SUPERVISOR_DECISIONS = {
    "continue",
    "resume",
    "scope_correct",
    "parallelize",
    "merge_scope",
    "event_trigger_idle",
    "terminal_review",
}
LINEAR_PROJECTED_FIELDS = {
    "bead_id",
    "title",
    "hierarchy",
    "status",
    "execution_mode",
    "display_status",
    "priority",
    "due",
    "codex_ready",
    "codex_paused",
    "cancel",
    "short_blocker",
    "short_result",
    "links",
}
LINEAR_TO_BEADS_FIELDS = {
    "human_intent",
    "priority",
    "due",
    "codex_ready",
    "codex_paused",
    "cancel",
}
BEADS_TO_LINEAR_FIELDS = {"execution_state", "execution_mode", "display_status", "blocker", "result"}
EXECUTION_MODES = {"active", "waiting_user", "waiting_external", "monitoring", "aggregate"}
LINEAR_DISPLAY_STATUSES = {"Backlog", "Todo", "In Progress", "Waiting", "Monitoring", "Done"}
LINEAR_STATUS_NORMALIZATION = {
    "Backlog": "deferred",
    "Todo": "open",
    "In Progress": "in_progress",
    "Waiting": ["in_progress", "blocked"],
    "Monitoring": "in_progress",
    "Done": "closed",
}


class ReceiptError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReceiptError(message)


def require_object(value: object, field: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{field} must be an object")
    return value  # type: ignore[return-value]


def validate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    require(receipt.get("schema") == RECEIPT_SCHEMA, f"schema must be {RECEIPT_SCHEMA}")
    require(receipt.get("status") == "passed", "status must be passed")
    require(receipt.get("action") == "start", "receipt must come from explicit $opl-flow start")
    require(receipt.get("installation_side_effects") == "none", "installation must not perform onboarding")
    fingerprint = receipt.get("objective_fingerprint")
    require(isinstance(fingerprint, str) and bool(fingerprint.strip()), "objective_fingerprint is required")

    project = require_object(receipt.get("project"), "project")
    require(isinstance(project.get("id"), str) and bool(project["id"].strip()), "project.id is required")
    require(project.get("saved") is True, "project must be a saved Codex project")
    require(project.get("execution_environment") == "local", "execution environment must be local")

    dashboard = require_object(receipt.get("dashboard"), "dashboard")
    thread_id = dashboard.get("thread_id")
    require(isinstance(thread_id, str) and bool(thread_id.strip()), "dashboard.thread_id is required")
    require(dashboard.get("match_count") == 1, "dashboard must have exactly one match")
    require(dashboard.get("pinned") is True, "dashboard must be pinned")

    bead = require_object(receipt.get("bead"), "bead")
    require(isinstance(bead.get("id"), str) and bool(bead["id"].strip()), "bead.id is required")
    require(bead.get("match_count") == 1, "dashboard thread must have exactly one Bead")
    require(
        bead.get("external_ref") == f"codex://thread/{thread_id}",
        "bead.external_ref must bind the exact dashboard thread",
    )

    heartbeat = require_object(receipt.get("heartbeat"), "heartbeat")
    require(isinstance(heartbeat.get("id"), str) and bool(heartbeat["id"].strip()), "heartbeat.id is required")
    require(heartbeat.get("match_count") == 1, "dashboard must have exactly one heartbeat")
    require(heartbeat.get("kind") == "heartbeat", "automation must use the native heartbeat kind")
    require(heartbeat.get("target_thread_id") == thread_id, "heartbeat must target the dashboard thread")
    require(heartbeat.get("status") == "ACTIVE", "heartbeat must be ACTIVE")
    require(heartbeat.get("schedule") == "hourly", "heartbeat schedule must be hourly")
    require(heartbeat.get("display_name") == "OPL Flow Supervisor", "supervisor display name is fixed")

    supervisor = require_object(receipt.get("supervisor"), "supervisor")
    decisions = supervisor.get("decisions")
    require(isinstance(decisions, list), "supervisor.decisions must be a list")
    require(set(decisions) == SUPERVISOR_DECISIONS, "supervisor decisions are incomplete or contain extras")
    require(supervisor.get("writes_ledger_facts") is True, "supervisor must write ledger facts")
    require(supervisor.get("performs_adjustments") is True, "supervisor must perform required adjustments")
    require(supervisor.get("display_name") == "OPL Flow Supervisor", "supervisor identity is invalid")
    registered_project_ids = supervisor.get("registered_linear_project_ids")
    require(
        isinstance(registered_project_ids, list)
        and bool(registered_project_ids)
        and all(isinstance(value, str) and value.strip() for value in registered_project_ids)
        and len(registered_project_ids) == len(set(registered_project_ids)),
        "supervisor must register one or more unique Linear projects",
    )
    require(
        supervisor.get("single_heartbeat_for_registered_projects") is True,
        "registered projects must share one Supervisor heartbeat",
    )

    ledger = require_object(receipt.get("ledger"), "ledger")
    require(ledger.get("pull") == "passed", "Dolt pull must pass")
    require(ledger.get("push") in {"passed", "no_change"}, "Dolt push must pass or report no_change")
    require(ledger.get("parity") == "passed", "Dolt parity must pass")

    linear = require_object(receipt.get("linear"), "linear")
    require(linear.get("connector") == "official_linear_connector", "official Linear Connector is required")
    projects = linear.get("registered_projects")
    require(isinstance(projects, list) and bool(projects), "Linear must contain one or more registered projects")
    project_ids: list[str] = []
    for index, project_value in enumerate(projects):
        project = require_object(project_value, f"linear.registered_projects[{index}]")
        project_id = project.get("id")
        require(isinstance(project_id, str) and bool(project_id.strip()), "registered project id is required")
        project_ids.append(project_id)
        require(project.get("managed_by") == "local_codex", "registered Linear projects must be managed locally")
        require(project.get("coverage_parity") == "passed", "registered Linear project coverage must pass")
        cursor = project.get("last_processed_comment_id")
        require(
            isinstance(cursor, str) and bool(cursor.strip()),
            "registered project last_processed_comment_id is required",
        )
    require(len(project_ids) == len(set(project_ids)), "registered Linear projects must be unique")
    require(set(project_ids) == set(registered_project_ids), "Supervisor and Linear project registration must match")
    require(any(project.get("name") == "OPL Ledger" for project in projects), "default OPL Ledger project is required")
    ledger_bead_count = linear.get("ledger_bead_count")
    projected_issue_count = linear.get("projected_issue_count")
    require(isinstance(ledger_bead_count, int) and ledger_bead_count > 0, "linear.ledger_bead_count must be positive")
    require(projected_issue_count == ledger_bead_count, "Linear must project every user-ledger Bead")
    require(linear.get("missing_bead_ids") == [], "Linear projection has missing Beads")
    require(linear.get("duplicate_bead_ids") == [], "Linear projection has duplicate Bead mappings")
    require(linear.get("hierarchy_parity") == "passed", "Linear hierarchy parity must pass")
    require(set(linear.get("projected_fields", [])) == LINEAR_PROJECTED_FIELDS, "Linear projected field set is incomplete or contains extras")
    authority = require_object(linear.get("field_authority"), "linear.field_authority")
    require(set(authority.get("linear_to_beads", [])) == LINEAR_TO_BEADS_FIELDS, "Linear-to-Beads authority is invalid")
    require(set(authority.get("beads_to_linear", [])) == BEADS_TO_LINEAR_FIELDS, "Beads-to-Linear authority is invalid")
    execution_status = require_object(linear.get("execution_status"), "linear.execution_status")
    require(set(execution_status.get("execution_modes", [])) == EXECUTION_MODES, "execution mode set is invalid")
    require(
        set(execution_status.get("linear_display_statuses", [])) == LINEAR_DISPLAY_STATUSES,
        "Linear display status set is invalid",
    )
    require(
        execution_status.get("linear_to_beads_normalization") == LINEAR_STATUS_NORMALIZATION,
        "Linear display status normalization is invalid",
    )
    require(execution_status.get("drift_issue_ids") == [], "Linear execution status projection has drift")
    require(execution_status.get("unknown_mode_count") == 0, "unknown execution mode must fail closed")
    require(linear.get("excluded_fields_absent") is True, "sensitive or internal fields escaped into Linear")
    require(linear.get("terminal_readback") == "passed", "Linear terminal readback must pass")
    require(linear.get("bd_linear_sync_used") is False, "bd linear sync is forbidden for this route")
    admission = require_object(linear.get("execution_admission"), "linear.execution_admission")
    require(admission.get("default") == "local_codex_managed", "registered issues default to local Codex management")
    require(admission.get("codex_ready") == "compatibility_optional", "codex-ready must remain optional compatibility")
    require(
        admission.get("codex_paused") == "dispatch_only_reconciliation_and_comment_intake_continue",
        "codex-paused must block dispatch only",
    )
    paused_issue_ids = admission.get("paused_issue_ids")
    reconciled_paused_issue_ids = admission.get("reconciled_paused_issue_ids")
    dispatched_paused_issue_ids = admission.get("dispatched_paused_issue_ids")
    require(
        isinstance(paused_issue_ids, list)
        and all(isinstance(value, str) and value.strip() for value in paused_issue_ids)
        and len(paused_issue_ids) == len(set(paused_issue_ids)),
        "paused issue ids must be unique strings",
    )
    require(
        reconciled_paused_issue_ids == paused_issue_ids,
        "every codex-paused issue must remain reconciled",
    )
    require(dispatched_paused_issue_ids == [], "codex-paused issues must not be dispatched")

    comments = require_object(linear.get("comment_intake"), "linear.comment_intake")
    require(
        comments.get("route") == "mcp__codex_apps__linear_list_comments",
        "Linear comments must use the official list_comments route",
    )
    require(comments.get("cursor_scope") == "per_registered_project", "comment cursor scope is invalid")
    require(comments.get("cursor_kind") == "linear_comment_id_high_watermark", "comment cursor kind is invalid")
    require(comments.get("idempotency_key") == "linear_comment_id", "comment id must be the idempotency key")
    authorized_comment_ids = comments.get("authorized_user_comment_ids")
    delivered_comment_ids = comments.get("delivered_comment_ids")
    ignored_non_user_comment_ids = comments.get("ignored_non_user_comment_ids")
    require(
        isinstance(authorized_comment_ids, list)
        and all(isinstance(value, str) and value.strip() for value in authorized_comment_ids)
        and len(authorized_comment_ids) == len(set(authorized_comment_ids)),
        "authorized user comment ids must be unique strings",
    )
    require(
        isinstance(delivered_comment_ids, list)
        and all(isinstance(value, str) and value.strip() for value in delivered_comment_ids)
        and len(delivered_comment_ids) == len(set(delivered_comment_ids)),
        "delivered comment ids must be unique strings",
    )
    require(
        delivered_comment_ids == authorized_comment_ids,
        "every authorized new comment must reach its local task exactly once and in cursor order",
    )
    require(
        isinstance(ignored_non_user_comment_ids, list)
        and all(isinstance(value, str) and value.strip() for value in ignored_non_user_comment_ids)
        and len(ignored_non_user_comment_ids) == len(set(ignored_non_user_comment_ids)),
        "ignored non-user comment ids must be unique strings",
    )
    require(
        not set(delivered_comment_ids).intersection(ignored_non_user_comment_ids),
        "ignored non-user comments must not be delivered",
    )
    require(comments.get("duplicate_delivery_count") == 0, "comment delivery must be idempotent")
    require(comments.get("non_user_comments_ignored") is True, "Supervisor and Agent comments must be ignored")
    require(
        comments.get("paused_issue_reconciliation_continues") is True,
        "codex-paused issues must remain reconciled",
    )
    require(
        comments.get("paused_issue_comment_intake_continues") is True,
        "codex-paused issues must keep comment intake",
    )
    require(
        comments.get("cursor_advance") == "after_successful_delivery_or_documented_non_user_ignore",
        "comment cursor must advance only after handled evidence",
    )
    require(comments.get("processed_by") == "next_heartbeat", "comments must be handled by the next heartbeat")
    require(comments.get("cloud_delegate_conflict_count") == 0, "Cloud delegate conflicts must fail closed")

    ambient_ops = require_object(receipt.get("ambient_ops"), "ambient_ops")
    require(ambient_ops.get("registered") is True, "Ambient Ops must be registered in the Ledger")
    require(ambient_ops.get("owner") == "opl-fleet", "Ambient Ops must remain an OPL Fleet extension")
    require(ambient_ops.get("role") == "observability_extension", "Ambient Ops role is invalid")

    boundaries = require_object(receipt.get("boundaries"), "boundaries")
    require(boundaries.get("task_ssot") == "beads_dolt", "Beads/Dolt must remain task SSOT")
    require(boundaries.get("ledger_meaning") == "complete_owner_human_ledger", "OPL Ledger meaning is invalid")
    require(boundaries.get("codex_cloud_used") is False, "Codex Cloud must not be used")
    require(boundaries.get("cloud_delegate_used") is False, "Cloud delegate must not be used")
    require(boundaries.get("automatic_archive_performed") is False, "automatic archive is forbidden")

    return {
        "schema": "opl_flow_start_onboarding_validation.v1",
        "status": "passed",
        "dashboard_thread_id": thread_id,
        "bead_id": bead["id"],
        "heartbeat_id": heartbeat["id"],
        "registered_linear_project_count": len(project_ids),
        "linear_projected_issue_count": projected_issue_count,
        "paused_linear_issue_count": len(paused_issue_ids),
        "delivered_linear_comment_count": len(delivered_comment_ids),
        "ignored_non_user_comment_count": len(ignored_non_user_comment_ids),
        "duplicate_counts": {"dashboard": 0, "bead": 0, "heartbeat": 0, "linear_issue": 0},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        value = json.loads(args.receipt.read_text(encoding="utf-8"))
        require(isinstance(value, dict), "receipt must be a JSON object")
        result = validate_receipt(value)
    except (OSError, json.JSONDecodeError, ReceiptError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
