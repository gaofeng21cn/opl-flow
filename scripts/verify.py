#!/usr/bin/env python3
"""Repository contract checks for OPL Flow."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


CORE_SKILL_IDS = (
    "coordinate-concurrent-tasks",
    "codex-app-owner-migration",
    "develop-and-deliver",
    "github-ssot-patrol",
    "opl-doc",
    "opl-fleet",
    "opl-flow",
    "recover-codex-tasks",
    "task-mode-gate",
)

REQUIRED_FILES = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "plugin.json",
    "contracts/workflow-policy.json",
    "contracts/workflow-policy.schema.json",
    "contracts/fleet-workspace-profile.schema.json",
    "contracts/task-owner-migration.schema.json",
    "contracts/worktree-ownership-ledger.schema.json",
    "LICENSE",
    "skills/coordinate-concurrent-tasks/SKILL.md",
    "skills/coordinate-concurrent-tasks/agents/openai.yaml",
    "skills/codex-app-owner-migration/SKILL.md",
    "skills/codex-app-owner-migration/agents/openai.yaml",
    "skills/develop-and-deliver/SKILL.md",
    "skills/develop-and-deliver/agents/openai.yaml",
    "skills/github-ssot-patrol/SKILL.md",
    "skills/github-ssot-patrol/agents/openai.yaml",
    "skills/github-ssot-patrol/references/decision-contract.md",
    "skills/github-ssot-patrol/scripts/github_patrol.py",
    "skills/opl-doc/SKILL.md",
    "skills/opl-doc/agents/openai.yaml",
    "skills/opl-fleet/SKILL.md",
    "skills/opl-fleet/agents/openai.yaml",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "skills/opl-flow/references/app-integration.md",
    "skills/opl-flow/references/codex-baseline.md",
    "skills/opl-flow/references/ledger-start.md",
    "skills/opl-flow/references/ledger-supervisor.md",
    "skills/opl-flow/references/package-lifecycle.md",
    "skills/opl-flow/references/package-release.md",
    "skills/opl-flow/references/setup-update.md",
    "skills/opl-flow/references/terminal-readback.md",
    "skills/opl-flow/scripts/package_release.py",
    "skills/recover-codex-tasks/SKILL.md",
    "skills/recover-codex-tasks/agents/openai.yaml",
    "skills/task-mode-gate/SKILL.md",
    "skills/task-mode-gate/agents/openai.yaml",
    "templates/AGENTS.md",
    "templates/TASTE.md",
    "scripts/worktree_absorption_audit.py",
    "scripts/worktree_fleet_audit.py",
    "scripts/worktree_lifecycle.py",
    "scripts/opl_workflow.py",
    "scripts/opl_fleet.py",
    "scripts/opl_fleet_parts/__init__.py",
    "scripts/opl_fleet_parts/fleet_cli.py",
    "scripts/opl_fleet_parts/fleet_common.py",
    "scripts/opl_fleet_parts/fleet_dispatch.py",
    "scripts/opl_fleet_parts/fleet_features.py",
    "scripts/opl_fleet_parts/fleet_lease.py",
    "scripts/opl_fleet_parts/fleet_reconcile.py",
    "scripts/opl_fleet_parts/fleet_runner.py",
    "scripts/opl_fleet_parts/fleet_workspace.py",
    "scripts/opl_task_owner.py",
    "scripts/fleet_inventory.py",
    "profile/manifest.json",
    "profile/modules/01-user-preferences.md",
)

CORE_TEST_MODULES = (
    "tests/test_verify_lanes.py",
    "tests/test_worktree_absorption_audit.py",
    "tests/test_worktree_fleet_audit.py",
    "tests/test_worktree_lifecycle.py",
    "tests/test_opl_workflow.py",
    "tests/test_opl_fleet.py",
    "tests/test_task_owner_migration.py",
    "tests/test_fleet_inventory.py",
    "tests/test_github_ssot_patrol.py",
    "tests/test_package_descriptor.py",
    "tests/test_package_release.py",
)
VERIFY_LANES = ("core", "full")

def check_required_files(repo_root: Path) -> list[str]:
    return [f"missing {rel}" for rel in REQUIRED_FILES if not (repo_root / rel).exists()]


def check_plugin_json(repo_root: Path) -> list[str]:
    errors: list[str] = []
    manifest = json.loads((repo_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    portable = json.loads((repo_root / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "opl-flow":
        errors.append("plugin name must be opl-flow")
    if manifest.get("skills") != "./skills/":
        errors.append("plugin skills path must be ./skills/")
    discoverable_skills = {
        path.name for path in (repo_root / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    }
    if discoverable_skills != set(CORE_SKILL_IDS):
        errors.append("default plugin must expose exactly the nine OPL Flow core skills")
    policy = json.loads((repo_root / "contracts" / "workflow-policy.json").read_text(encoding="utf-8"))
    if manifest.get("version") != policy.get("package", {}).get("version"):
        errors.append("plugin version must match contracts/workflow-policy.json package.version")
    if portable.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        errors.append("portable plugin must use Agent Plugins 1.0")
    portable_interface = portable.get("extensions", {}).get("com.openai", {}).get("interface")
    if (
        portable.get("name") != manifest.get("name")
        or portable.get("version") != manifest.get("version")
        or portable_interface != manifest.get("interface")
    ):
        errors.append("portable and Codex plugin manifests must bind the same identity and interface")
    description = manifest.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("plugin description must be a non-empty string")
    interface = manifest.get("interface", {})
    long_description = interface.get("longDescription")
    if not isinstance(long_description, str) or not long_description.strip():
        errors.append("interface.longDescription must be a non-empty string")
    default_prompt = interface.get("defaultPrompt")
    if not default_prompt or len(default_prompt) > 128:
        errors.append("interface.defaultPrompt must exist and be at most 128 characters")
    return errors


def check_workflow_policy(repo_root: Path) -> list[str]:
    errors: list[str] = []
    policy = json.loads((repo_root / "contracts" / "workflow-policy.json").read_text(encoding="utf-8"))
    schema = json.loads((repo_root / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"))
    if policy.get("$schema") != "./workflow-policy.schema.json":
        errors.append("workflow policy must point to ./workflow-policy.schema.json")
    if "$schema" not in schema.get("properties", {}):
        errors.append("workflow policy schema must admit the policy $schema pointer")
    if policy.get("schema") != "opl_flow_workflow_policy.v4":
        errors.append("workflow policy schema must be opl_flow_workflow_policy.v4")
    if policy.get("package", {}).get("id") != "opl-flow":
        errors.append("workflow policy package id must be opl-flow")
    required_sections = (
        "task_boundary_policy", "external_artifact_language_policy", "provides", "requires",
        "experience_baseline", "compatible_optional",
        "capability_bundles",
        "conflicts", "retires", "ledger_supervisor_policy", "task_owner_migration_policy",
        "codex_app_owner_migration_policy",
        "codex_model_policy", "migration_policy",
        "historical_fingerprints",
    )
    for section in required_sections:
        if section not in policy:
            errors.append(f"workflow policy missing {section}")
    expected_task_boundary_policy = {
        "authority": "opl-flow",
        "stop_ladder": [
            "user_request",
            "necessity",
            "reachable_evidence",
            "acceptance_dependency",
        ],
        "expansion_rule": "only_stop_ladder_reasons",
        "unsupported_expansion": "defer_and_report",
        "task_modes": [
            {"id": "answer", "mutation": "read_only", "scope": "requested_answer"},
            {"id": "review", "mutation": "read_only", "scope": "requested_review_surface"},
            {
                "id": "change",
                "mutation": "requested_result_and_necessary_consequences",
                "scope": "requested_change",
            },
            {
                "id": "monitor",
                "mutation": "read_only",
                "scope": "bounded_observation_and_requested_alerts",
            },
        ],
        "task_mode_gate_handoff": {
            "skill_id": "task-mode-gate",
            "precondition": "stop_ladder_supported_reason_and_high_risk_mutation",
            "relationship": "stop_ladder_then_gate",
            "gate_authority": "task-mode-gate",
        },
    }
    if policy.get("task_boundary_policy") != expected_task_boundary_policy:
        errors.append(
            "workflow policy task boundary policy must keep the Stop Ladder, four task modes, and task-mode-gate handoff fixed"
        )
    expected_external_artifact_language_policy = {
        "authority_order": [
            "explicit_user_language_or_authoritative_repository_rule",
            "existing_object_dominant_language",
            "current_user_request_language_for_new_or_full_rewrite",
        ],
        "consistency_scope": [
            "agent_created_or_user_authorized_title",
            "agent_created_or_user_authorized_body",
            "agent_created_or_user_authorized_reply",
        ],
        "source_language_exemptions": [
            "product_name",
            "code_identifier",
            "api_route",
            "environment_variable",
            "verbatim_quote",
        ],
        "pre_write_gate": "resolve_and_check_artifact_language",
        "post_write_gate": "fresh_readback_language_consistency",
        "third_party_content": "preserve_without_explicit_authority",
    }
    if policy.get("external_artifact_language_policy") != expected_external_artifact_language_policy:
        errors.append(
            "workflow policy must resolve one external artifact language and verify owned surfaces after writes"
        )
    capabilities = [
        item
        for section in ("provides", "requires", "experience_baseline", "compatible_optional")
        for item in policy.get(section, [])
    ]
    capability_keys = [(item.get("kind"), item.get("id")) for item in capabilities]
    if len(capability_keys) != len(set(capability_keys)):
        errors.append("workflow capability identity must be unique by (kind, id)")
    required_metadata = {"id", "kind", "online_install_default", "activation"}
    if any(not required_metadata.issubset(item) for item in capabilities):
        errors.append("workflow policy capabilities must declare identity and activation metadata")
    skill_capabilities = [
        item for item in capabilities if item.get("kind") == "codex_skill"
    ]
    if any(
        not isinstance(item.get("source"), str)
        or re.fullmatch(r"https://github\.com/[^/\s]+/[^/\s]+/?", item["source"]) is None
        or not isinstance(item.get("source_path"), str)
        or not item["source_path"].strip()
        or item["source_path"].startswith("/")
        or "\\" in item["source_path"]
        or ".." in PurePosixPath(item["source_path"]).parts
        for item in skill_capabilities
    ):
        errors.append(
            "all codex_skill capabilities must declare their original GitHub source "
            "and repository-relative source_path"
        )
    expected_provides = {
        ("codex_plugin", "opl-flow"),
        *(("codex_skill", skill_id) for skill_id in CORE_SKILL_IDS),
    }
    provides = policy.get("provides", [])
    if {(item.get("kind"), item.get("id")) for item in provides} != expected_provides:
        errors.append("workflow policy provided Plugin and Skills must match the package payload")
    provided_skill_sources = {
        item.get("id"): (item.get("source"), item.get("source_path"))
        for item in provides
        if item.get("kind") == "codex_skill"
    }
    expected_provided_skill_sources = {
        "opl-flow": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/opl-flow",
        ),
        "coordinate-concurrent-tasks": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/coordinate-concurrent-tasks",
        ),
        "codex-app-owner-migration": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/codex-app-owner-migration",
        ),
        "develop-and-deliver": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/develop-and-deliver",
        ),
        "github-ssot-patrol": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/github-ssot-patrol",
        ),
        "opl-doc": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/opl-doc",
        ),
        "opl-fleet": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/opl-fleet",
        ),
        "recover-codex-tasks": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/recover-codex-tasks",
        ),
        "task-mode-gate": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/task-mode-gate",
        ),
    }
    if provided_skill_sources != expected_provided_skill_sources:
        errors.append("workflow policy provided Skills must use their canonical GitHub source and path")
    if any(item.get("online_install_default") is not True for item in provides):
        errors.append("provided capabilities must be enabled by default")
    schema_kind_enum = (
        schema.get("$defs", {}).get("capability", {}).get("properties", {})
        .get("kind", {}).get("enum", [])
    )
    if not {"codex_plugin", "mcp_server"}.issubset(schema_kind_enum):
        errors.append("workflow policy schema must admit codex_plugin and mcp_server capabilities")
    baseline_ids = {
        item.get("id") for item in policy.get("experience_baseline", [])
        if item.get("kind") == "codex_skill"
    }
    expected = {
        "agent-reach",
        "officecli", "officecli-docx", "officecli-pptx", "officecli-xlsx",
        "officecli-academic-paper", "officecli-data-dashboard",
        "officecli-financial-model", "officecli-pitch-deck",
        "mineru-document-extractor",
    }
    if baseline_ids != expected:
        errors.append("workflow policy experience baseline is incomplete or contains duplicates")
    baseline_skill_sources = {
        item.get("id"): (item.get("source"), item.get("source_path"))
        for item in policy.get("experience_baseline", [])
        if item.get("kind") == "codex_skill"
    }
    officecli_source = "https://github.com/iOfficeAI/OfficeCLI"
    expected_skill_sources = {
        "agent-reach": (
            "https://github.com/Panniantong/Agent-Reach",
            "agent_reach/skill",
        ),
        "officecli": (officecli_source, "."),
        "officecli-docx": (officecli_source, "skills/officecli-docx"),
        "officecli-pptx": (officecli_source, "skills/officecli-pptx"),
        "officecli-xlsx": (officecli_source, "skills/officecli-xlsx"),
        "officecli-academic-paper": (officecli_source, "skills/officecli-academic-paper"),
        "officecli-data-dashboard": (officecli_source, "skills/officecli-data-dashboard"),
        "officecli-financial-model": (officecli_source, "skills/officecli-financial-model"),
        "officecli-pitch-deck": (officecli_source, "skills/officecli-pitch-deck"),
        "mineru-document-extractor": (
            "https://github.com/opendatalab/MinerU-Ecosystem",
            "skills",
        ),
    }
    if baseline_skill_sources != expected_skill_sources:
        errors.append("workflow policy experience baseline skills must use their canonical GitHub source and path")
    if any(not item.get("online_install_default") for item in policy.get("experience_baseline", [])):
        errors.append("workflow policy experience baseline must be repaired by default")
    baseline = policy.get("experience_baseline", [])
    baseline_lifecycle_metadata = {
        "bundle_id", "install_source", "lifecycle_owner", "offline_bundle",
        "readiness_adapter", "conflict_policy", "credential_policy",
    }
    if any(not baseline_lifecycle_metadata.issubset(item) for item in baseline):
        errors.append(
            "workflow policy experience baseline must declare bundle, lifecycle, distribution, and readiness metadata"
        )
    expected_owner_migration = {
        "authority": "beads_dolt",
        "objective_identity": "bead_id",
        "executor_handle": "replaceable_codex_task",
        "native_handoff": "optional_non_authoritative",
        "workspace_authority": "private_instance_profile",
        "workspace_admission": [
            "declared_environment_current",
            "fresh_fetch",
            "fresh_github_head",
            "clean_default_branch",
            "no_active_task_worktree",
            "current_instance_control_receipt",
        ],
        "state_sequence": [
            "source_checkpointed",
            "target_preflighted",
            "target_acknowledged",
            "target_verified",
            "completed",
        ],
        "claim_mutations": [
            "opl_owner_claim_generation",
            "execution_owner",
            "execution_thread",
            "execution_node",
        ],
        "post_claim_rollback": "reverse_migration_only",
        "dolt_unknown_result": "read_only_reconcile_no_retry",
        "automation_cutover": ["old_disabled_readback", "new_active_readback"],
    }
    if policy.get("task_owner_migration_policy") != expected_owner_migration:
        errors.append("workflow policy task owner migration contract must remain fail-closed")
    expected_codex_app_owner_migration = {
        "authority": "codex_app_native_owner_tools",
        "executor_kind": "native_codex_app_task",
        "target_visibility": [
            "connected_host_visible",
            "all_profile_repositories_visible",
            "native_task_visible_in_target_app",
            "task_readback_matches_host_project_and_cwd",
        ],
        "creation_route": [
            "codex_app_create_thread_in_saved_project",
            "codex_app_handoff_thread_when_supported",
        ],
        "ssh_role": "transport_bootstrap_or_readback_only",
        "headless_cli_policy": "never_accept_as_native_owner",
        "source_release_gate": [
            "target_task_acknowledged",
            "target_task_readable",
            "claim_readback_matches",
            "target_started_or_waiting",
        ],
        "failure_fallback": "local_owner_continues;rollback_before_claim_or_reverse_migration_after_claim",
        "workspace_scope": "instance_profile_repository_allowlist",
        "full_workspace_required": True,
        "automation_policy": "separate_singleton_cas_cutover",
    }
    if policy.get("codex_app_owner_migration_policy") != expected_codex_app_owner_migration:
        errors.append("Codex App owner migration policy must remain native-visible and fail-closed")
    supervisor = policy.get("ledger_supervisor_policy", {})
    expected_event_driven_control_plane = {
        "dispatch_mode": "event_driven",
        "global_supervisor": {
            "role": "ledger_macro_reconciliation_and_exception_fallback",
            "scheduled_episode_scope": "bounded_change_detection_and_ledger_reconciliation",
            "product_progress_polling": False,
        },
        "product_controller": {
            "role": "objective_graph_acceptance_and_successor_dispatch",
            "callback_handling": "same_episode_accept_repair_or_dispatch",
            "resident_polling": False,
        },
        "executor": {
            "role": "bounded_slice_execution",
            "callback_target": "product_controller",
            "callback_events": ["checkpoint", "terminal", "real_blocker"],
            "callback_is_completion_evidence": False,
        },
        "fallback": {
            "owner": "global_supervisor",
            "triggers": [
                "executor_lost",
                "callback_missing",
                "cross_objective_owner_or_write_set_conflict",
            ],
            "routine_progress_polling": False,
        },
        "idle_product_activity": {
            "product_reads": 0,
            "successor_dispatches": 0,
            "semantic_writes": 0,
        },
    }
    if supervisor.get("event_driven_control_plane") != expected_event_driven_control_plane:
        errors.append(
            "Ledger coordination must remain event-driven across the global supervisor, "
            "product controller, and bounded executors"
        )
    expected_incremental_fast_path = {
        "phase_order": ["change_detection", "selective_expansion"],
        "state_owner": "private_supervisor_memory_cursor_location",
        "thread_detection": {
            "inventory_source": "list_threads",
            "observation_fields": ["updatedAt", "status", "hasUnreadTurn"],
            "excluded_observation_fields": ["title"],
            "progress_signal_source": "executor_callback_to_product_controller",
            "wait_threads_policy": "fallback_only_after_executor_loss_missing_callback_or_cross_objective_conflict",
            "wait_timeout_ms": 0,
            "wait_batch_size": 8,
            "exact_read_triggers": [
                "new_thread",
                "summary_changed",
                "wait_cursor_changed",
                "has_unread_turn",
                "review_due",
                "ambiguous_owner_state",
            ],
        },
        "linear_detection": {
            "issue_delta_source": "list_issues_updated_after_project_waterline",
            "comment_read_scope": "changed_issues_only",
            "newest_comment_order_assumption": "forbidden",
        },
        "external_review": {
            "backoff_field": "next_review_at",
            "hourly_polling": False,
            "early_recheck_triggers": [
                "user_change",
                "owner_change",
                "issue_change",
                "schema_or_policy_change",
                "relevant_repository_change",
            ],
        },
        "full_audit": {
            "periodic_schedule": False,
            "minimum_interval_hours": 24,
            "triggers": [
                "missing_or_ambiguous_cursor",
                "schema_or_policy_change",
                "timeout_unknown",
                "explicit_user_request",
            ],
        },
        "observability_counters": [
            "threads_listed",
            "thread_summaries_changed",
            "wait_targets",
            "wait_cursors_changed",
            "threads_read",
            "linear_projects_probed",
            "linear_issues_changed",
            "linear_comment_pages",
            "authority_checks",
            "semantic_writes",
            "retries",
            "elapsed_seconds",
            "full_audit_reason",
        ],
        "no_change_budget": {
            "list_threads_calls": 1,
            "wait_threads_calls": 0,
            "linear_issue_delta_calls_per_project": 1,
            "read_thread_calls": 0,
            "linear_comment_calls": 0,
            "authority_checks": 0,
            "semantic_writes": 0,
            "expected_runtime_seconds": 60,
        },
    }
    if supervisor.get("incremental_fast_path") != expected_incremental_fast_path:
        errors.append("Ledger Supervisor must keep the bounded incremental no-change fast path")
    expected_linear_assignee_projection = {
        "mode": "single_authorized_human",
        "source": "heartbeat_authorized_human_accounts",
        "single_account_required": True,
        "multiple_accounts_policy": "fail_closed_require_project_mapping",
        "scope": "all_registered_project_issues",
        "repair_selection": "changed_or_drifted_issues_only",
        "full_repair_triggers": [
            "explicit_user_request",
            "policy_change",
            "missing_assignment_waterline",
        ],
        "write_batch_size": 10,
        "readback": "exact_project_issue_count_and_zero_mismatches",
        "execution_truth_owner": "beads_dolt_not_linear_assignee",
    }
    if supervisor.get("linear_assignee_projection") != expected_linear_assignee_projection:
        errors.append(
            "Ledger Supervisor must keep one authorized human assignee projection with drift-only repair"
        )
    expected_task_lifecycle_classes = {
        "managed_objective": {
            "enrollment": "default_for_finite_development_and_delivery",
            "lifecycle_authority": "beads_and_owner_readback",
            "terminal_inference": "authoritative_outcome_and_remaining_empty",
            "title_projection": "execution_state",
        },
        "interactive_longline": {
            "enrollment": "explicit_or_existing_registered_long_lived_interactive_task",
            "lifecycle_authority": "user_codex_task_archive",
            "terminal_inference": "forbidden",
            "title_projection": "fresh_thread_activity",
        },
        "ephemeral_operation": {
            "enrollment": "excluded_by_default_or_explicit_record_only",
            "lifecycle_authority": "user_codex_task_archive",
            "terminal_inference": "forbidden",
            "title_projection": "fresh_thread_activity",
        },
    }
    if supervisor.get("task_lifecycle_classes") != expected_task_lifecycle_classes:
        errors.append("Ledger Supervisor must keep the three task lifecycle authorities")
    expected_execution_modes = {
        "backlog": {
            "beads_status": "deferred",
            "linear_status": "Backlog",
            "linear_status_type": "backlog",
            "execution_thread": None,
            "dispatch": "planned_capacity_or_dependency_release",
            "eligible_classes": ["managed_objective"],
        },
        "on_demand": {
            "beads_status": "pinned",
            "linear_status": "On Demand",
            "linear_status_type": "backlog",
            "execution_thread": None,
            "dispatch": "user_intent_or_explicit_trigger_only",
            "terminal_inference": "forbidden",
            "eligible_classes": ["interactive_longline"],
            "purpose": "long_horizon_irregular_manual_followup",
        }
    }
    if supervisor.get("execution_modes") != expected_execution_modes:
        errors.append(
            "Ledger Supervisor must separate planned managed backlog from long-horizon manual on_demand"
        )
    expected_bounded_executor_policy = {
        "live_binding": "execution_thread",
        "history_binding": "last_execution_thread",
        "archived_history_policy": "provenance_only_never_resume",
        "trigger_action": "resume_unarchived_or_create_new",
        "unbind_after_authoritative_readback": True,
    }
    if supervisor.get("bounded_executor_policy") != expected_bounded_executor_policy:
        errors.append("Ledger Supervisor must never resume an archived bounded executor")
    owner_tools = supervisor.get("native_owner_tools", {})
    expected_failure_classes = {
        "invalid_arguments": "caller_schema_error",
        "permission_denied": "authorization_required",
        "timeout_unknown": "destination_reconciliation_required",
        "unavailable": "owner_tool_absent_or_unreachable",
    }
    if (
        owner_tools.get("preflight_required") is not True
        or owner_tools.get("list_threads_max_limit") != 50
        or owner_tools.get("failure_classes") != expected_failure_classes
    ):
        errors.append("Ledger Supervisor native owner tools must keep the bounded failure taxonomy")
    delivery = supervisor.get("comment_delivery", {})
    expected_states = [
        "comment_observed",
        "destination_delivery_confirmed",
        "owner_answer_read",
        "linear_reply_posted",
        "linear_reply_read_back",
        "cursor_advanced",
    ]
    expected_timeout = {
        "status": "timeout_unknown",
        "readback": "destination_read_thread",
        "bounded_retry_limit": 1,
        "retry_condition": "confirmed_absent_after_destination_readback",
    }
    if (
        delivery.get("idempotency_key") != "linear_comment_id"
        or delivery.get("state_sequence") != expected_states
        or delivery.get("delivery_confirmation_sources") != [
            "send_message_to_thread_success",
            "destination_read_thread_reconciliation",
        ]
        or delivery.get("timeout_reconciliation") != expected_timeout
        or delivery.get("cursor_advance_gate") != "linear_reply_read_back"
    ):
        errors.append("Ledger Supervisor comment delivery must reconcile timeout and close reply readback before cursor advance")
    expected_reply = {
        "first_line": "【OPL Flow · Codex 自动回复】",
        "required_provenance": ["source_codex_task", "answer_provenance"],
        "non_user_detection": "marker_not_linear_author_identity",
    }
    if delivery.get("automated_reply") != expected_reply:
        errors.append("Ledger Supervisor automated replies must carry marker and answer provenance")
    full_offline_keys = {
        (item.get("kind"), item.get("id"))
        for item in baseline
        if item.get("offline_bundle") == "full"
    }
    if full_offline_keys != {("cli", "officecli"), ("cli", "mineru-open-api")}:
        errors.append("workflow policy Full offline seeds must be selected only by Flow policy")
    bundle_members = {
        f"{item.get('kind')}:{item.get('id')}": item.get("bundle_id")
        for item in [*baseline, *policy.get("compatible_optional", [])]
    }
    bundles = policy.get("capability_bundles", [])
    bundle_ids = [item.get("id") for item in bundles]
    if len(bundle_ids) != len(set(bundle_ids)):
        errors.append("workflow policy capability bundle ids must be unique")
    declared_member_refs = [
        member_ref
        for bundle in bundles
        for member_ref in bundle.get("member_refs", [])
    ]
    if len(declared_member_refs) != len(set(declared_member_refs)):
        errors.append("workflow policy capability bundle members must have one source bundle")
    if set(declared_member_refs) != set(bundle_members):
        errors.append("workflow policy capability bundles must cover every baseline and optional capability exactly once")
    for bundle in bundles:
        for member_ref in bundle.get("member_refs", []):
            if bundle_members.get(member_ref) != bundle.get("id"):
                errors.append(f"workflow capability {member_ref} must point back to bundle {bundle.get('id')}")
    expected_bundle_relationships = {
        "internet-research": "experience_baseline",
        "office-authoring": "experience_baseline",
        "document-extraction": "experience_baseline",
        "architecture-enhancement": "compatible_optional",
        "official-codex-office-runtime": "compatible_optional",
        "task-boundary-guard": "compatible_optional",
    }
    if {item.get("id"): item.get("relationship") for item in bundles} != expected_bundle_relationships:
        errors.append("workflow policy capability bundle relationships are incomplete")
    for bundle in bundles:
        relationship = bundle.get("relationship")
        readiness = bundle.get("readiness", {})
        if relationship == "experience_baseline" and (
            bundle.get("online_materialization") != "members_marked_default"
            or bundle.get("full_distribution") != "members_marked_full"
            or readiness.get("absence_effect") != "degraded_non_blocking"
            or readiness.get("repair_policy") != "framework_or_owner_adapter"
        ):
            errors.append(f"experience bundle {bundle.get('id')} must be repairable and non-blocking")
        if relationship == "compatible_optional" and (
            bundle.get("online_materialization") != "observe_only"
            or bundle.get("full_distribution") != "none"
            or readiness.get("absence_effect") != "optional_absent"
            or readiness.get("repair_policy") != "none"
        ):
            errors.append(f"optional bundle {bundle.get('id')} must remain observe-only")
    agent_reach = next(
        (
            item for item in policy.get("experience_baseline", [])
            if item.get("kind") == "codex_skill" and item.get("id") == "agent-reach"
        ),
        None,
    )
    expected_agent_reach = {
        "id": "agent-reach",
        "kind": "codex_skill",
        "owner": "agent-reach",
        "bundle_id": "internet-research",
        "install_source": "owner_cli",
        "lifecycle_owner": "agent-reach",
        "online_install_default": True,
        "offline_bundle": "none",
        "activation": "task_routed",
        "readiness_adapter": "codex_skill_payload",
        "source": "https://github.com/Panniantong/Agent-Reach",
        "source_path": "agent_reach/skill",
    }
    if agent_reach is None or any(
        agent_reach.get(key) != value
        for key, value in expected_agent_reach.items()
    ):
        errors.append("workflow policy experience baseline must include agent-reach from its canonical GitHub source")
    agent_reach_cli = next(
        (
            item for item in policy.get("experience_baseline", [])
            if item.get("kind") == "cli" and item.get("id") == "agent-reach"
        ),
        None,
    )
    if not agent_reach_cli or (
        agent_reach_cli.get("bundle_id") != "internet-research"
        or agent_reach_cli.get("install_source") != "owner_cli"
        or agent_reach_cli.get("readiness_adapter") != "agent_reach_doctor"
        or agent_reach_cli.get("offline_bundle") != "none"
    ):
        errors.append("agent-reach baseline must include its owner CLI and doctor readiness")
    if any(item.get("id") == "agent-reach" for item in policy.get("requires", [])):
        errors.append("agent-reach must not make the OPL Flow package operational dependency set")
    architect = next(
        (
            item for item in policy.get("compatible_optional", [])
            if item.get("kind") == "codex_skill" and item.get("id") == "architect-and-simplify"
        ),
        None,
    )
    expected_architect = {
        "id": "architect-and-simplify",
        "kind": "codex_skill",
        "owner": "opl-skills",
        "online_install_default": False,
        "activation": "task_routed",
        "source": "https://github.com/gaofeng21cn/opl-skills",
        "source_path": "skills/architect-and-simplify",
    }
    if architect is None or any(
        architect.get(key) != value
        for key, value in expected_architect.items()
    ):
        errors.append("architect-and-simplify must remain an observed optional OPL Skills capability")
    stop_guard = next(
        (
            item for item in policy.get("compatible_optional", [])
            if item.get("kind") == "codex_plugin" and item.get("id") == "stop-that-shit"
        ),
        None,
    )
    expected_stop_guard = {
        "id": "stop-that-shit",
        "kind": "codex_plugin",
        "owner": "lennney",
        "bundle_id": "task-boundary-guard",
        "online_install_default": False,
        "offline_bundle": "none",
        "activation": "explicit",
        "readiness_adapter": "runtime_observation",
        "source": "https://github.com/lennney/stop-that-shit",
        "source_path": ".codex-plugin",
    }
    if stop_guard is None or any(
        stop_guard.get(key) != value
        for key, value in expected_stop_guard.items()
    ):
        errors.append("stop-that-shit must remain an explicit, non-blocking optional guard")
    dependencies = [
        item
        for section in ("requires", "experience_baseline")
        for item in policy.get(section, [])
    ]
    if any(
        item.get("version_requirement") == "release_lock_exact"
        or item.get("install_source") == "framework_managed_release_lock"
        for item in dependencies
    ):
        errors.append("workflow dependencies must not require a release lock")
    if "installation_convergence" in policy:
        errors.append("workflow policy must not bind composition to a delivery carrier")
    conflict_ids = {item.get("id") for item in policy.get("conflicts", [])}
    if not {"upstream-superpowers", "ponytail", "codexcont-intelligence-enhancement"}.issubset(conflict_ids):
        errors.append("workflow policy must retire the known legacy global workflow conflicts")
    migrations = [*policy.get("conflicts", []), *policy.get("retires", [])]
    ponytail_conflict = next(
        (item for item in policy.get("conflicts", []) if item.get("id") == "ponytail"),
        {},
    )
    expected_ponytail_conflicts = {"ponytail", "ponytail-local", "ponytail-ponytail"}
    if set(ponytail_conflict.get("discovery_ids", [])) != expected_ponytail_conflicts:
        errors.append("workflow policy must retire only Ponytail plugin and main-persona discovery aliases")
    expected_ponytail_surfaces = {"plugin", "config_table", "service", "prompt_or_agent"}
    if set(ponytail_conflict.get("surface_kinds", [])) != expected_ponytail_surfaces:
        errors.append("workflow policy must preserve the explicit task-local Ponytail Skill surface")
    retired_discovery_ids = {
        discovery_id
        for item in migrations
        for discovery_id in item.get("discovery_ids", [])
    }
    if {"ponytail-audit", "ponytail-review"} & retired_discovery_ids:
        errors.append("explicit Ponytail audit and review skills must remain outside workflow retirement")
    if any(not isinstance(item.get("config_markers"), list) or not isinstance(item.get("service_ids"), list) for item in migrations):
        errors.append("workflow migrations must declare config_markers and service_ids")
    core_skill_retirement = next(
        (
            item
            for item in policy.get("retires", [])
            if item.get("id") == "opl-skills-core-workflow-projections"
        ),
        None,
    )
    expected_retired_ids = {"develop-and-deliver", "recover-codex-tasks", "task-mode-gate"}
    expected_skill_paths = {
        skill_id: f"skills/{skill_id}/SKILL.md" for skill_id in expected_retired_ids
    }
    expected_skill_source = {
        "discovery_root": "agent_skills",
        "lock_file": "agent_skill_lock",
        "source": "gaofeng21cn/opl-skills",
        "source_url": "https://github.com/gaofeng21cn/opl-skills.git",
        "skill_paths": expected_skill_paths,
    }
    if (
        core_skill_retirement is None
        or set(core_skill_retirement.get("discovery_ids", [])) != expected_retired_ids
        or core_skill_retirement.get("skill_source") != expected_skill_source
    ):
        errors.append("core Skill retirement must require exact former OPL Skills lock provenance")
    migration_policy = policy.get("migration_policy", {})
    if not migration_policy.get("discovery_root_ids"):
        errors.append("workflow migration policy must declare bounded discovery roots")
    if migration_policy.get("profile_optimization", {}).get("default_mode") != "codex_semantic_merge":
        errors.append("workflow profile optimization must default to Codex semantic merge")
    fingerprints = policy.get("historical_fingerprints", {})
    if not fingerprints.get("agents_marker_pairs") or not fingerprints.get("agents_legacy_section_headings"):
        errors.append("workflow policy must declare historical AGENTS markers and section headings")
    precedence = policy.get("codex_model_policy", {}).get("override_precedence", [])
    expected_precedence = [
        "explicit_user_override",
        "opl_flow_recommendation",
        "fresh_codex_model_catalog",
        "app_fallback_when_flow_unavailable",
    ]
    if precedence != expected_precedence:
        errors.append("model precedence must be user, installed Flow, live Codex, then App fallback")
    dependency_ids = {
        item.get("id")
        for section in ("requires", "experience_baseline", "compatible_optional")
        for item in policy.get(section, [])
    }
    if "codex-ops-kit" in dependency_ids:
        errors.append("retired codex-ops-kit must not remain in workflow dependencies")
    return errors


def check_profile(repo_root: Path) -> list[str]:
    errors: list[str] = []
    agents = (repo_root / "templates" / "AGENTS.md").read_text(encoding="utf-8")

    profile_size = len(agents.encode("utf-8"))
    if profile_size > 2048:
        print(
            "WARNING: AGENTS.md exceeds the 2 KB focus target; "
            "keep reviewing clarity and move detail only when functionality is preserved",
            file=sys.stderr,
        )
    if profile_size > 4096:
        print(
            "WARNING: AGENTS.md exceeds 4 KB; this is a soft maintainability signal, not a gate",
            file=sys.stderr,
        )

    profile_source = (repo_root / "profile" / "modules" / "01-user-preferences.md").read_text(
        encoding="utf-8"
    )
    if agents != profile_source:
        errors.append("templates/AGENTS.md must match profile/modules/01-user-preferences.md")
    return errors


def check_retired_skill(repo_root: Path) -> list[str]:
    retired = "risk-based-" + "development-flow"
    errors: list[str] = []
    if (repo_root / "skills" / retired).exists():
        errors.append(f"retired skill directory still exists: skills/{retired}")
    if (repo_root / "optional-skills" / "codex-ops-kit").exists():
        errors.append("retired skill directory still exists: optional-skills/codex-ops-kit")
    return errors


def contract_test_modules(lane: str) -> tuple[str, ...]:
    if lane in {"core", "full"}:
        return CORE_TEST_MODULES
    raise ValueError(f"unknown verification lane: {lane}")


def check_contract_tests(repo_root: Path, lane: str) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-v",
            *contract_test_modules(lane),
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        return []
    return ["contract tests failed: " + (result.stdout + result.stderr).strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", nargs="?", choices=VERIFY_LANES, default="core")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    errors.extend(check_required_files(repo_root))
    errors.extend(check_plugin_json(repo_root))
    errors.extend(check_workflow_policy(repo_root))
    errors.extend(check_profile(repo_root))
    errors.extend(check_retired_skill(repo_root))
    errors.extend(check_contract_tests(repo_root, args.lane))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OPL Flow {args.lane} verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
