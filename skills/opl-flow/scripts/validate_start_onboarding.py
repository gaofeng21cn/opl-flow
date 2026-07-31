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

    supervisor = require_object(receipt.get("supervisor"), "supervisor")
    decisions = supervisor.get("decisions")
    require(isinstance(decisions, list), "supervisor.decisions must be a list")
    require(set(decisions) == SUPERVISOR_DECISIONS, "supervisor decisions are incomplete or contain extras")
    require(supervisor.get("writes_ledger_facts") is True, "supervisor must write ledger facts")
    require(supervisor.get("performs_adjustments") is True, "supervisor must perform required adjustments")

    ledger = require_object(receipt.get("ledger"), "ledger")
    require(ledger.get("pull") == "passed", "Dolt pull must pass")
    require(ledger.get("push") in {"passed", "no_change"}, "Dolt push must pass or report no_change")
    require(ledger.get("parity") == "passed", "Dolt parity must pass")

    boundaries = require_object(receipt.get("boundaries"), "boundaries")
    require(boundaries.get("task_ssot") == "beads_dolt", "Beads/Dolt must remain task SSOT")
    require(boundaries.get("codex_cloud_used") is False, "Codex Cloud must not be used")
    require(boundaries.get("automatic_archive_performed") is False, "automatic archive is forbidden")

    return {
        "schema": "opl_flow_start_onboarding_validation.v1",
        "status": "passed",
        "dashboard_thread_id": thread_id,
        "bead_id": bead["id"],
        "heartbeat_id": heartbeat["id"],
        "duplicate_counts": {"dashboard": 0, "bead": 0, "heartbeat": 0},
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
