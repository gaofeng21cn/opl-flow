from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from scripts.verify import (
    CORE_TEST_MODULES,
    REQUIRED_FILES,
    ROUTER_SKILL_IDS,
    check_required_files,
    check_plugin_json,
    check_workflow_policy,
    contract_test_modules,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class VerifyLaneTests(unittest.TestCase):
    def test_required_files_cover_every_fleet_runtime_module(self) -> None:
        self.assertEqual(check_required_files(REPO_ROOT), [])
        runtime_modules = (
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
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            errors = check_required_files(Path(temp_dir))
        missing = {error.removeprefix("missing ") for error in errors}
        for relative_path in runtime_modules:
            self.assertIn(
                relative_path,
                missing,
                f"check_required_files must flag missing {relative_path}",
            )

    def test_required_files_include_owner_migration_contracts(self) -> None:
        required = set(REQUIRED_FILES)
        self.assertIn("contracts/fleet-workspace-profile.schema.json", required)
        self.assertIn("contracts/task-owner-migration.schema.json", required)

    def test_plugin_exposes_only_three_router_skills(self) -> None:
        self.assertEqual(check_plugin_json(REPO_ROOT), [])

        discoverable = {
            path.relative_to(REPO_ROOT).as_posix()
            for path in (REPO_ROOT / "skills").rglob("SKILL.md")
        }
        expected = {
            f"skills/{skill_id}/SKILL.md" for skill_id in ROUTER_SKILL_IDS
        }
        self.assertEqual(discoverable, expected)

    def test_deepseek_adaptation_preserves_mit_provenance(self) -> None:
        notice = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        self.assertIn("https://github.com/deepseek-ai/deepseek-harness", notice)
        self.assertIn("141eb6fef83422698aef7a981029e843e8161534", notice)
        self.assertIn("Copyright (c) 2026 DeepSeek", notice)
        self.assertIn("MIT License", notice)

    def test_package_declares_apache_2_license_consistently(self) -> None:
        plugin = json.loads(
            (REPO_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertEqual(plugin["license"], "Apache-2.0")
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)
        self.assertIn("Copyright 2026 Gaofeng", license_text)

    def test_full_lane_runs_the_complete_current_suite(self) -> None:
        core = contract_test_modules("core")

        self.assertEqual(core, CORE_TEST_MODULES)
        self.assertEqual(contract_test_modules("full"), core)
        with self.assertRaisesRegex(ValueError, "unknown verification lane: ops-kit"):
            contract_test_modules("ops-kit")

    def test_workflow_policy_rejects_retired_codex_ops_kit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            policy["compatible_optional"].append(
                {
                    "id": "codex-ops-kit",
                    "kind": "codex_skill",
                    "offline_bundle": "full",
                    "online_install_default": False,
                    "activation": "explicit",
                    "source": "opl-flow:optional-skills/codex-ops-kit",
                }
            )
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            errors = check_workflow_policy(repo_root)

        self.assertIn("retired codex-ops-kit must not remain in workflow dependencies", errors)

    def test_workflow_policy_keeps_stop_guard_out_of_default_bundles(self) -> None:
        policy = json.loads(
            (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
        )
        guard = next(item for item in policy["compatible_optional"] if item["id"] == "stop-that-shit")
        self.assertFalse(guard["online_install_default"])
        bundle = next(item for item in policy["capability_bundles"] if item["id"] == "task-boundary-guard")
        self.assertEqual(bundle["online_materialization"], "observe_only")
        self.assertEqual(bundle["readiness"]["absence_effect"], "optional_absent")

    def test_workflow_policy_fixes_task_boundary_modes_and_handoff(self) -> None:
        policy = json.loads(
            (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
        )
        boundary = policy["task_boundary_policy"]
        self.assertEqual(
            boundary["stop_ladder"],
            ["user_request", "necessity", "reachable_evidence", "acceptance_dependency"],
        )
        self.assertEqual(
            [mode["id"] for mode in boundary["task_modes"]],
            ["answer", "review", "change", "monitor"],
        )
        self.assertEqual(
            boundary["production_change_handoff"],
            {
                "router_skill_id": "software-development",
                "reference": "references/delivery/production-change.md",
                "precondition": "stop_ladder_supported_reason_and_high_risk_mutation",
                "relationship": "stop_ladder_then_reference",
            },
        )
        self.assertEqual(
            boundary["repair_progress_policy"],
            {
                "known_breakpoint_next_action": "owner_side_repair_or_delivery_bridge",
                "proof_role": "tests_verify_after_repair",
                "green_without_breakpoint_movement": "not_progress",
                "post_event_transition": {
                    "breakpoint_unchanged": ["direct_fix", "delivery_bridge", "stop"],
                    "breakpoint_moved": ["proof", "acceptance", "complete"],
                    "proof_failed": ["direct_fix", "delivery_bridge", "stop"],
                    "external_blocker": ["stop"],
                },
                "wait_only_active": False,
                "stale_test_contract": "preserve_product_fix_update_test_contract",
            },
        )

    def test_workflow_policy_fixes_external_artifact_language_boundary(self) -> None:
        policy = json.loads(
            (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
        )
        language = policy["external_artifact_language_policy"]

        self.assertEqual(
            language["consistency_scope"],
            [
                "agent_created_or_user_authorized_title",
                "agent_created_or_user_authorized_body",
                "agent_created_or_user_authorized_reply",
            ],
        )
        self.assertEqual(language["pre_write_gate"], "resolve_and_check_artifact_language")
        self.assertEqual(language["post_write_gate"], "fresh_readback_language_consistency")
        self.assertEqual(
            language["third_party_content"],
            "preserve_without_explicit_authority",
        )

    def test_workflow_policy_preserves_explicit_ponytail_skills(self) -> None:
        self.assertEqual(check_workflow_policy(REPO_ROOT), [])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            ponytail = next(item for item in policy["conflicts"] if item["id"] == "ponytail")
            ponytail["discovery_ids"].append("ponytail-audit")
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            errors = check_workflow_policy(repo_root)

        self.assertIn(
            "explicit Ponytail audit and review skills must remain outside workflow retirement",
            errors,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            ponytail = next(item for item in policy["conflicts"] if item["id"] == "ponytail")
            ponytail["surface_kinds"].append("skill")
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            errors = check_workflow_policy(repo_root)

        self.assertIn(
            "workflow policy must preserve the explicit task-local Ponytail Skill surface",
            errors,
        )

    def test_workflow_policy_requires_canonical_github_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            mineru = next(
                item for item in policy["experience_baseline"]
                if item["id"] == "mineru-document-extractor"
            )
            mineru["source"] = "https://github.com/example/mineru"
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            errors = check_workflow_policy(repo_root)

        self.assertIn(
            "workflow policy experience baseline skills must use their canonical GitHub source and path",
            errors,
        )

    def workflow_policy_errors_after(self, mutate) -> list[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            mutate(policy)
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            return check_workflow_policy(repo_root)

    def test_workflow_policy_rejects_weakened_owner_migration_gate(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: policy["task_owner_migration_policy"].update(
                native_handoff="authoritative"
            )
        )
        self.assertIn(
            "workflow policy task owner migration contract must remain fail-closed",
            errors,
        )

    def test_every_skill_requires_original_github_source(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: next(
                item
                for item in policy["provides"]
                if item["kind"] == "codex_skill" and item["id"] == "opl-flow"
            ).update(source="package:opl-flow/skills/opl-flow")
        )
        self.assertIn(
            "all codex_skill capabilities must declare their original GitHub source "
            "and repository-relative source_path",
            errors,
        )

    def test_ledger_supervisor_contract_rejects_delivery_and_provenance_regressions(self) -> None:
        event_driven_error = (
            "Ledger coordination must remain event-driven across the global supervisor, "
            "product controller, and bounded executors"
        )
        missing_product_controller_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]
            ["event_driven_control_plane"].pop("product_controller")
        )
        self.assertIn(event_driven_error, missing_product_controller_errors)

        resident_polling_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]
            ["event_driven_control_plane"]["product_controller"].update(
                resident_polling=True,
            )
        )
        self.assertIn(event_driven_error, resident_polling_errors)

        periodic_progress_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]
            ["event_driven_control_plane"]["global_supervisor"].update(
                product_progress_polling=True,
            )
        )
        self.assertIn(event_driven_error, periodic_progress_errors)

        periodic_audit_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["incremental_fast_path"]
            ["full_audit"].update(periodic_schedule=True)
        )
        self.assertIn(
            "Ledger Supervisor must keep the bounded incremental no-change fast path",
            periodic_audit_errors,
        )

        incomplete_callback_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]
            ["event_driven_control_plane"]["executor"].update(
                callback_events=["checkpoint", "terminal"],
            )
        )
        self.assertIn(event_driven_error, incomplete_callback_errors)

        expanded_fallback_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]
            ["event_driven_control_plane"]["fallback"]["triggers"].append(
                "scheduled_progress_scan"
            )
        )
        self.assertIn(event_driven_error, expanded_fallback_errors)

        fast_path_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["incremental_fast_path"]
            ["no_change_budget"].update(read_thread_calls=1)
        )
        self.assertIn(
            "Ledger Supervisor must keep the bounded incremental no-change fast path",
            fast_path_errors,
        )

        routine_wait_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["incremental_fast_path"]
            ["no_change_budget"].update(wait_threads_calls=1)
        )
        self.assertIn(
            "Ledger Supervisor must keep the bounded incremental no-change fast path",
            routine_wait_errors,
        )

        title_signature_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["incremental_fast_path"]
            ["thread_detection"]["observation_fields"].append("title")
        )
        self.assertIn(
            "Ledger Supervisor must keep the bounded incremental no-change fast path",
            title_signature_errors,
        )

        duplicate_backoff_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["incremental_fast_path"]
            ["external_review"].update(backoff_field="next_authority_check_at")
        )
        self.assertIn(
            "Ledger Supervisor must keep the bounded incremental no-change fast path",
            duplicate_backoff_errors,
        )

        comment_probe_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["incremental_fast_path"]
            ["linear_detection"].update(newest_comment_order_assumption="newest_first")
        )
        self.assertIn(
            "Ledger Supervisor must keep the bounded incremental no-change fast path",
            comment_probe_errors,
        )

        assignee_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]
            ["linear_assignee_projection"].update(
                repair_selection="all_issues_every_heartbeat",
            )
        )
        self.assertIn(
            "Ledger Supervisor must keep one authorized human assignee projection with drift-only repair",
            assignee_errors,
        )

        executor_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["bounded_executor_policy"].update(
                archived_history_policy="resume_when_triggered",
            )
        )
        self.assertIn(
            "Ledger Supervisor must never resume an archived bounded executor",
            executor_errors,
        )

        backlog_taxonomy_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["execution_modes"].pop(
                "backlog"
            )
        )
        self.assertIn(
            "Ledger Supervisor must separate planned managed backlog from long-horizon manual on_demand",
            backlog_taxonomy_errors,
        )

        on_demand_scope_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["execution_modes"]
            ["on_demand"].update(eligible_classes=["managed_objective"])
        )
        self.assertIn(
            "Ledger Supervisor must separate planned managed backlog from long-horizon manual on_demand",
            on_demand_scope_errors,
        )

        taxonomy_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["native_owner_tools"].update(
                list_threads_max_limit=100,
            )
        )
        self.assertIn(
            "Ledger Supervisor native owner tools must keep the bounded failure taxonomy",
            taxonomy_errors,
        )

        timeout_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["comment_delivery"].update(
                cursor_advance_gate="destination_delivery_confirmed",
            )
        )
        self.assertIn(
            "Ledger Supervisor comment delivery must reconcile timeout and close reply readback before cursor advance",
            timeout_errors,
        )

        marker_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["comment_delivery"]["automated_reply"].update(
                first_line="Codex owner",
            )
        )
        self.assertIn(
            "Ledger Supervisor automated replies must carry marker and answer provenance",
            marker_errors,
        )

    def test_ledger_supervisor_reference_keeps_incremental_no_change_semantics(self) -> None:
        reference = (
            REPO_ROOT / "skills" / "opl-flow" / "references" / "ledger-supervisor.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(reference.split())

        self.assertNotIn(
            "Call `read_thread` for each managed objective",
            reference,
        )
        self.assertIn("With no event,", reference)
        self.assertIn("zero `wait_threads`", reference)
        self.assertIn("The global Supervisor does not resident-poll either role.", reference)
        self.assertIn(
            "zero `read_thread`, zero comment calls, zero authority checks, and zero semantic writes",
            normalized,
        )
        self.assertIn(
            "Do not create a duplicate `next_authority_check_at` field.",
            normalized,
        )

    def test_ledger_references_do_not_resurrect_retired_workbench_alias(self) -> None:
        references = "\n".join(
            (
                REPO_ROOT / relative_path
            ).read_text(encoding="utf-8")
            for relative_path in (
                "skills/opl-flow/references/ledger-start.md",
                "skills/opl-flow/references/ledger-supervisor.md",
            )
        )

        self.assertNotIn("persistent_workbench", references)
        self.assertIn("interactive_longline", references)

    def test_every_skill_requires_safe_repository_relative_source_path(self) -> None:
        for invalid_path in ("../skills/opl-flow", "/skills/opl-flow", r"skills\opl-flow"):
            with self.subTest(source_path=invalid_path):
                errors = self.workflow_policy_errors_after(
                    lambda policy, value=invalid_path: next(
                        item
                        for item in policy["provides"]
                        if item["kind"] == "codex_skill" and item["id"] == "opl-flow"
                    ).update(source_path=value)
                )
                self.assertIn(
                    "all codex_skill capabilities must declare their original GitHub source "
                    "and repository-relative source_path",
                    errors,
                )

    def test_agent_reach_accepts_optional_open_composition_metadata(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: next(
                item
                for item in policy["experience_baseline"]
                if item["kind"] == "codex_skill" and item["id"] == "agent-reach"
            ).update(
                version_requirement=">=0.0.0",
            )
        )

        self.assertEqual(errors, [])

    def test_agent_reach_is_baseline_not_operational_dependency(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: policy["requires"].append(
                next(
                    item
                    for item in policy["experience_baseline"]
                    if item["kind"] == "codex_skill" and item["id"] == "agent-reach"
                ).copy()
            )
        )

        self.assertIn(
            "agent-reach must not make the OPL Flow package operational dependency set",
            errors,
        )

    def test_software_development_router_stays_in_the_plugin_payload(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: policy["provides"].remove(
                next(
                    item
                    for item in policy["provides"]
                    if item["kind"] == "codex_skill" and item["id"] == "software-development"
                )
            )
        )

        self.assertIn(
            "workflow policy provided Plugin and Skills must match the package payload",
            errors,
        )

    def test_capability_bundles_cover_each_member_once(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: next(
                bundle
                for bundle in policy["capability_bundles"]
                if bundle["id"] == "office-authoring"
            )["member_refs"].remove("cli:officecli")
        )

        self.assertIn(
            "workflow policy capability bundles must cover every baseline and optional capability exactly once",
            errors,
        )

    def test_full_offline_selection_is_owned_by_flow(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: next(
                item
                for item in policy["experience_baseline"]
                if item["kind"] == "codex_skill" and item["id"] == "agent-reach"
            ).update(offline_bundle="full")
        )

        self.assertIn(
            "workflow policy Full offline seeds must be selected only by Flow policy",
            errors,
        )

    def test_specialist_tools_use_framework_managed_owner_adapters(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: next(
                item
                for item in policy["experience_baseline"]
                if item["kind"] == "cli" and item["id"] == "gh-stack"
            ).update(lifecycle_owner="github-cli")
        )

        self.assertIn(
            "specialist tool dependencies must use Framework-managed owner adapters",
            errors,
        )

    def test_skill_source_schema_patterns_reject_non_github_and_unsafe_paths(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8")
        )
        properties = (
            schema["$defs"]["capability"]["allOf"][0]["then"]["properties"]
        )
        source_pattern = properties["source"]["pattern"]
        path_pattern = properties["source_path"]["pattern"]

        self.assertIsNotNone(
            re.fullmatch(source_pattern, "https://github.com/Panniantong/Agent-Reach")
        )
        self.assertIsNone(re.fullmatch(source_pattern, "skills-manager:agent-reach"))
        self.assertIsNotNone(re.fullmatch(path_pattern, "agent_reach/skill"))
        self.assertIsNotNone(re.fullmatch(path_pattern, "."))
        for invalid_path in ("../skill", "/skill", r"skills\agent-reach"):
            with self.subTest(schema_source_path=invalid_path):
                self.assertIsNone(re.fullmatch(path_pattern, invalid_path))

if __name__ == "__main__":
    unittest.main()
