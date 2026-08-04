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
    "develop-and-deliver",
    "github-ssot-patrol",
    "opl-fleet",
    "opl-flow",
    "recover-codex-tasks",
    "task-mode-gate",
)

REQUIRED_FILES = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "contracts/workflow-policy.json",
    "contracts/workflow-policy.schema.json",
    "contracts/worktree-ownership-ledger.schema.json",
    "README.md",
    "docs/compatibility.md",
    "docs/new-machine-codex-setup.md",
    "LICENSE",
    "skills/coordinate-concurrent-tasks/SKILL.md",
    "skills/coordinate-concurrent-tasks/agents/openai.yaml",
    "skills/develop-and-deliver/SKILL.md",
    "skills/develop-and-deliver/agents/openai.yaml",
    "skills/github-ssot-patrol/SKILL.md",
    "skills/github-ssot-patrol/agents/openai.yaml",
    "skills/github-ssot-patrol/references/decision-contract.md",
    "skills/github-ssot-patrol/scripts/github_patrol.py",
    "skills/opl-fleet/SKILL.md",
    "skills/opl-fleet/agents/openai.yaml",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "skills/opl-flow/references/app-integration.md",
    "skills/opl-flow/references/codex-baseline.md",
    "skills/opl-flow/references/ledger-start.md",
    "skills/opl-flow/references/ledger-supervisor.md",
    "skills/opl-flow/references/package-lifecycle.md",
    "skills/opl-flow/references/setup-update.md",
    "skills/opl-flow/references/terminal-readback.md",
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
    "scripts/fleet_inventory.py",
    "profile/manifest.json",
    "profile/modules/01-user-preferences.md",
)

CORE_TEST_MODULES = (
    "tests/test_develop_and_deliver.py",
    "tests/test_verify_lanes.py",
    "tests/test_worktree_absorption_audit.py",
    "tests/test_worktree_fleet_audit.py",
    "tests/test_worktree_lifecycle.py",
    "tests/test_opl_workflow.py",
    "tests/test_opl_fleet.py",
    "tests/test_fleet_inventory.py",
    "tests/test_github_ssot_patrol.py",
    "tests/test_package_descriptor.py",
)
VERIFY_LANES = ("core", "full")

def check_required_files(repo_root: Path) -> list[str]:
    return [f"missing {rel}" for rel in REQUIRED_FILES if not (repo_root / rel).exists()]


def check_plugin_json(repo_root: Path) -> list[str]:
    errors: list[str] = []
    manifest = json.loads((repo_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "opl-flow":
        errors.append("plugin name must be opl-flow")
    if manifest.get("skills") != "./skills/":
        errors.append("plugin skills path must be ./skills/")
    discoverable_skills = {
        path.name for path in (repo_root / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    }
    if discoverable_skills != set(CORE_SKILL_IDS):
        errors.append("default plugin must expose exactly the seven OPL Flow core skills")
    policy = json.loads((repo_root / "contracts" / "workflow-policy.json").read_text(encoding="utf-8"))
    if manifest.get("version") != policy.get("package", {}).get("version"):
        errors.append("plugin version must match contracts/workflow-policy.json package.version")
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
        "provides", "requires", "experience_baseline", "compatible_optional",
        "capability_bundles",
        "conflicts", "retires", "ledger_supervisor_policy", "codex_model_policy", "migration_policy",
        "historical_fingerprints",
    )
    for section in required_sections:
        if section not in policy:
            errors.append(f"workflow policy missing {section}")
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
        "develop-and-deliver": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/develop-and-deliver",
        ),
        "github-ssot-patrol": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/github-ssot-patrol",
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
        "mineru-document-extractor", "ui-ux-pro-max",
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
        "ui-ux-pro-max": (
            "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill",
            ".claude/skills/ui-ux-pro-max",
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
    supervisor = policy.get("ledger_supervisor_policy", {})
    expected_incremental_fast_path = {
        "phase_order": ["change_detection", "selective_expansion"],
        "state_owner": "private_supervisor_memory_cursor_location",
        "thread_detection": {
            "inventory_source": "list_threads",
            "observation_fields": ["updatedAt", "status", "hasUnreadTurn"],
            "excluded_observation_fields": ["title"],
            "live_progress_source": "wait_threads",
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
            "cadence_hours": 24,
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
            "wait_threads_calls_per_live_batch": 1,
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
        "on_demand": {
            "beads_status": "pinned",
            "linear_status": "On Demand",
            "linear_status_type": "backlog",
            "execution_thread": None,
            "dispatch": "user_intent_or_explicit_trigger_only",
            "terminal_inference": "forbidden",
        }
    }
    if supervisor.get("execution_modes") != expected_execution_modes:
        errors.append("Ledger Supervisor must map on_demand to pinned/On Demand without automatic dispatch")
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
        "visual-design": "experience_baseline",
        "architecture-enhancement": "compatible_optional",
        "official-codex-office-runtime": "compatible_optional",
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

    instruction_count = sum(
        line.startswith("- ") or bool(re.match(r"^\d+\. ", line))
        for line in agents.splitlines()
    )
    if instruction_count > 8:
        errors.append("AGENTS.md must contain at most 8 prioritized instructions")

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
    roots = ("README.md", "docs", "profile", "templates", "skills", "optional-skills", "scripts", "tests", ".codex-plugin")
    for root_name in roots:
        root = repo_root / root_name
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file() or path == Path(__file__).resolve():
                continue
            try:
                if retired in path.read_text(encoding="utf-8"):
                    errors.append(f"retired skill reference remains: {path.relative_to(repo_root)}")
            except UnicodeDecodeError:
                continue
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
