from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from scripts.verify import (
    CORE_SKILL_IDS,
    CORE_TEST_MODULES,
    REQUIRED_FILES,
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

    def test_plugin_exposes_the_eight_bounded_flow_skills(self) -> None:
        self.assertEqual(check_plugin_json(REPO_ROOT), [])

        discoverable = {
            path.name
            for path in (REPO_ROOT / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").exists()
        }
        self.assertEqual(discoverable, set(CORE_SKILL_IDS))

    def test_codex_app_owner_migration_skill_declares_native_visibility_boundary(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "codex-app-owner-migration" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("native, user-visible Codex App task", skill)
        self.assertIn("headless `codex` process is never accepted", skill)
        self.assertIn("Migration is optional for delivery", skill)

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

    def test_workflow_policy_requires_canonical_github_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            ui_ux = next(
                item for item in policy["experience_baseline"]
                if item["id"] == "ui-ux-pro-max"
            )
            ui_ux["source"] = "https://github.com/example/ui-ux-pro-max-skill"
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
        fast_path_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["incremental_fast_path"]
            ["no_change_budget"].update(read_thread_calls=1)
        )
        self.assertIn(
            "Ledger Supervisor must keep the bounded incremental no-change fast path",
            fast_path_errors,
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

        executor_errors = self.workflow_policy_errors_after(
            lambda policy: policy["ledger_supervisor_policy"]["bounded_executor_policy"].update(
                archived_history_policy="resume_when_triggered",
            )
        )
        self.assertIn(
            "Ledger Supervisor must never resume an archived bounded executor",
            executor_errors,
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
        self.assertIn(
            "An unchanged cursor does not require `read_thread`.",
            reference,
        )
        self.assertIn(
            "zero `read_thread`, zero comment calls, zero authority checks, and zero semantic writes",
            normalized,
        )
        self.assertIn(
            "Do not create a duplicate `next_authority_check_at` field.",
            normalized,
        )

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

    def test_architect_and_simplify_stays_optional_and_not_auto_repaired(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda policy: next(
                item
                for item in policy["compatible_optional"]
                if item["kind"] == "codex_skill" and item["id"] == "architect-and-simplify"
            ).update(online_install_default=True)
        )

        self.assertIn(
            "architect-and-simplify must remain an observed optional OPL Skills capability",
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

    def test_core_skill_retirement_requires_exact_former_owner_provenance(self) -> None:
        mutation_cases = (
            lambda source: source.update(source="other/skills"),
            lambda source: source.update(source_url="https://github.com/other/skills.git"),
            lambda source: source["skill_paths"].update(
                {"develop-and-deliver": "skills/other/SKILL.md"}
            ),
        )
        for mutate in mutation_cases:
            with self.subTest(mutate=mutate):
                errors = self.workflow_policy_errors_after(
                    lambda policy, change=mutate: change(
                        next(
                            item
                            for item in policy["retires"]
                            if item["id"] == "opl-skills-core-workflow-projections"
                        )["skill_source"]
                    )
                )
                self.assertIn(
                    "core Skill retirement must require exact former OPL Skills lock provenance",
                    errors,
                )


if __name__ == "__main__":
    unittest.main()
