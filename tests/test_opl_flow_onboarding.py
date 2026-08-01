from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "skills" / "opl-flow" / "references" / "start-onboarding.json"
SKILL_PATH = REPO_ROOT / "skills" / "opl-flow" / "SKILL.md"
LEDGER_START_PATH = REPO_ROOT / "skills" / "opl-flow" / "references" / "ledger-start.md"
CODEX_BASELINE_PATH = REPO_ROOT / "skills" / "opl-flow" / "references" / "codex-baseline.md"
APP_INTEGRATION_PATH = REPO_ROOT / "skills" / "opl-flow" / "references" / "app-integration.md"
TERMINAL_READBACK_PATH = REPO_ROOT / "skills" / "opl-flow" / "references" / "terminal-readback.md"
VALIDATOR_PATH = REPO_ROOT / "skills" / "opl-flow" / "scripts" / "validate_start_onboarding.py"
README_PATH = REPO_ROOT / "README.md"
README_ZH_PATH = REPO_ROOT / "README.zh-CN.md"
PLUGIN_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"
AGENT_PATH = REPO_ROOT / "skills" / "opl-flow" / "agents" / "openai.yaml"

SPEC = importlib.util.spec_from_file_location("opl_flow_start_onboarding_validator", VALIDATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"cannot load onboarding validator from {VALIDATOR_PATH}")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
validate_receipt = VALIDATOR.validate_receipt


def valid_receipt() -> dict[str, object]:
    return {
        "schema": "opl_flow_start_onboarding_receipt.v1",
        "status": "passed",
        "action": "start",
        "installation_side_effects": "none",
        "objective_fingerprint": "opl-ledger-dashboard",
        "project": {"id": "project-1", "saved": True, "execution_environment": "local"},
        "dashboard": {"thread_id": "thread-1", "match_count": 1, "pinned": True, "reused": True},
        "bead": {"id": "opl-1", "external_ref": "codex://thread/thread-1", "match_count": 1},
        "heartbeat": {
            "id": "heartbeat-1",
            "match_count": 1,
            "kind": "heartbeat",
            "target_thread_id": "thread-1",
            "status": "ACTIVE",
            "schedule": "hourly",
            "display_name": "OPL Flow Supervisor",
        },
        "supervisor": {
            "display_name": "OPL Flow Supervisor",
            "registered_linear_project_ids": ["linear-opl-ledger"],
            "single_heartbeat_for_registered_projects": True,
            "decisions": [
                "continue",
                "resume",
                "scope_correct",
                "parallelize",
                "merge_scope",
                "event_trigger_idle",
                "terminal_review",
            ],
            "writes_ledger_facts": True,
            "performs_adjustments": True,
        },
        "ledger": {"pull": "passed", "push": "no_change", "parity": "passed"},
        "linear": {
            "connector": "official_linear_connector",
            "registered_projects": [
                {
                    "id": "linear-opl-ledger",
                    "name": "OPL Ledger",
                    "managed_by": "local_codex",
                    "coverage_parity": "passed",
                    "last_processed_comment_id": "comment-42",
                }
            ],
            "ledger_bead_count": 8,
            "projected_issue_count": 8,
            "missing_bead_ids": [],
            "duplicate_bead_ids": [],
            "hierarchy_parity": "passed",
            "projected_fields": [
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
            ],
            "field_authority": {
                "linear_to_beads": [
                    "human_intent",
                    "priority",
                    "due",
                    "codex_ready",
                    "codex_paused",
                    "cancel",
                ],
                "beads_to_linear": ["execution_state", "execution_mode", "display_status", "blocker", "result"],
            },
            "execution_status": {
                "execution_modes": [
                    "active",
                    "waiting_user",
                    "waiting_external",
                    "monitoring",
                    "aggregate",
                ],
                "linear_display_statuses": [
                    "Backlog",
                    "Todo",
                    "In Progress",
                    "Needs Action",
                    "Blocked",
                    "Monitoring",
                    "Done",
                ],
                "linear_to_beads_normalization": {
                    "Backlog": "deferred",
                    "Todo": "open",
                    "In Progress": "in_progress",
                    "Needs Action": ["in_progress", "blocked"],
                    "Blocked": ["in_progress", "blocked"],
                    "Monitoring": "in_progress",
                    "Done": "closed",
                },
                "drift_issue_ids": [],
                "unknown_mode_count": 0,
            },
            "execution_admission": {
                "default": "local_codex_managed",
                "codex_ready": "compatibility_optional",
                "codex_paused": "dispatch_only_reconciliation_and_comment_intake_continue",
                "paused_issue_ids": ["linear-issue-7"],
                "reconciled_paused_issue_ids": ["linear-issue-7"],
                "dispatched_paused_issue_ids": [],
            },
            "comment_intake": {
                "route": "mcp__codex_apps__linear_list_comments",
                "cursor_scope": "per_registered_project",
                "cursor_kind": "linear_comment_id_high_watermark",
                "idempotency_key": "linear_comment_id",
                "authorized_user_comment_ids": ["comment-43", "comment-44"],
                "delivered_comment_ids": ["comment-43", "comment-44"],
                "ignored_non_user_comment_ids": ["comment-45"],
                "duplicate_delivery_count": 0,
                "non_user_comments_ignored": True,
                "paused_issue_reconciliation_continues": True,
                "paused_issue_comment_intake_continues": True,
                "cursor_advance": "after_successful_delivery_or_documented_non_user_ignore",
                "processed_by": "next_heartbeat",
                "cloud_delegate_conflict_count": 0,
            },
            "excluded_fields_absent": True,
            "terminal_readback": "passed",
            "bd_linear_sync_used": False,
        },
        "ambient_ops": {
            "registered": True,
            "owner": "opl-fleet",
            "role": "observability_extension",
        },
        "boundaries": {
            "task_ssot": "beads_dolt",
            "ledger_meaning": "complete_owner_human_ledger",
            "codex_cloud_used": False,
            "cloud_delegate_used": False,
            "automatic_archive_performed": False,
        },
    }


class OplFlowOnboardingTests(unittest.TestCase):
    def test_contract_declares_native_idempotent_supervisor_route(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(contract["action"], "start")
        self.assertEqual(contract["defaults"]["execution_environment"], "local")
        self.assertEqual(contract["defaults"]["cadence"], "hourly")
        self.assertEqual(contract["defaults"]["supervisor_display_name"], "OPL Flow Supervisor")
        self.assertEqual(contract["invocation"]["onboarding_trigger"], "explicit_opl_flow_start_only")
        self.assertEqual(contract["invocation"]["installation_side_effects"], "none")
        self.assertIn("complete_human_ledger", contract["ledger_definition"])
        self.assertEqual(
            set(contract["native_tool_routes"].values()),
            {
                "list_projects",
                "list_threads",
                "create_thread",
                "read_thread",
                "send_message_to_thread",
                "wait_threads",
                "set_thread_pinned",
                "automation_update",
                "mcp__codex_apps__linear_list_issues",
                "mcp__codex_apps__linear_search",
                "mcp__codex_apps__linear_get_issue",
                "mcp__codex_apps__linear_save_issue",
                "mcp__codex_apps__linear_list_comments",
            },
        )
        self.assertEqual(
            contract["uniqueness"]["collision_policy"],
            "reuse_or_update_existing; fail_closed_on_multiple_matches",
        )
        self.assertEqual(
            contract["automation_discovery"]["glob"],
            "$CODEX_HOME/automations/*/automation.toml",
        )
        self.assertEqual(
            contract["automation_discovery"]["required_fields"],
            ["id", "kind", "target_thread_id", "prompt"],
        )
        self.assertEqual(
            contract["automation_discovery"]["failure_policy"],
            "fail_closed_on_unreadable_config_parse_error_or_multiple_matches",
        )
        linear = contract["linear_projection"]
        self.assertEqual(
            linear["availability"],
            "required_for_start_when_user_ledger_is_created_or_reused",
        )
        self.assertEqual(linear["coverage_scope"], "all_user_ledger_beads_including_dashboard_children")
        self.assertEqual(linear["forbidden_route"], "bd linear sync")
        self.assertEqual(
            linear["field_authority"],
            {
                "linear_to_beads": [
                    "human_intent",
                    "priority",
                    "due",
                    "codex_ready",
                    "codex_paused",
                    "cancel",
                ],
                "beads_to_linear": ["execution_state", "execution_mode", "display_status", "blocker", "result"],
            },
        )
        self.assertEqual(
            linear["execution_state_model"]["linear_to_beads_normalization"]["Needs Action"],
            ["in_progress", "blocked"],
        )
        self.assertEqual(
            linear["execution_state_model"]["linear_to_beads_normalization"]["Blocked"],
            ["in_progress", "blocked"],
        )
        self.assertEqual(
            linear["execution_state_model"]["linear_to_beads_normalization"]["Monitoring"],
            "in_progress",
        )
        self.assertEqual(linear["execution_admission"]["codex_ready"], "compatibility_hint_not_required_on_each_issue")
        self.assertEqual(
            linear["execution_admission"]["codex_paused"],
            "blocks_dispatch_only_reconciliation_and_comment_intake_continue",
        )
        self.assertEqual(linear["comment_intake"]["route"], "mcp__codex_apps__linear_list_comments")
        self.assertEqual(linear["comment_intake"]["cursor_kind"], "linear_comment_id_high_watermark")
        self.assertEqual(linear["comment_intake"]["idempotency_key"], "linear_comment_id")
        self.assertEqual(
            linear["comment_intake"]["cursor_advance"],
            "only_after_successful_delivery_or_documented_non_user_ignore",
        )
        self.assertEqual(linear["registered_projects"]["cardinality"], "one_or_more")
        self.assertEqual(contract["supervisor_identity"]["display_name"], "OPL Flow Supervisor")
        self.assertEqual(contract["supervisor_identity"]["heartbeat_cardinality"], "one_for_all_registered_linear_projects")
        self.assertIn("ambient_ops", " ".join(contract["supervisor_actions"]))
        self.assertEqual(contract["boundaries"]["codex_cloud"], "forbidden")
        self.assertEqual(
            contract["boundaries"]["automatic_archive"],
            "forbidden_without_fresh_user_approval",
        )

    def test_skill_routes_start_to_the_machine_contract(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        ledger_start = LEDGER_START_PATH.read_text(encoding="utf-8")
        progressive_route = f"{skill}\n{ledger_start}"

        self.assertIn("$opl-flow start", skill)
        self.assertIn("references/start-onboarding.json", skill)
        self.assertIn("validate_start_onboarding.py --receipt", skill)
        self.assertIn("every user-ledger Bead", progressive_route)
        self.assertIn("official Connector", progressive_route)
        self.assertIn("Do not use `bd linear sync`", progressive_route)
        self.assertIn("OPL Flow Supervisor", progressive_route)
        self.assertIn("mcp__codex_apps__linear_list_comments", progressive_route)
        self.assertIn("codex-paused", progressive_route)
        self.assertIn("Ambient Ops", progressive_route)
        self.assertIn("Installation never runs `start`", progressive_route)

    def test_primary_router_declares_six_actions_and_status_planes(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        baseline = CODEX_BASELINE_PATH.read_text(encoding="utf-8")
        app_integration = APP_INTEGRATION_PATH.read_text(encoding="utf-8")

        for action in ("doctor", "setup", "tune", "update", "start", "fleet"):
            with self.subTest(action=action):
                self.assertIn(f"$opl-flow {action}", skill)
        for plane in (
            "package_operational",
            "experience_baseline",
            "specialized_capabilities",
        ):
            with self.subTest(plane=plane):
                self.assertIn(plane, skill)
                self.assertIn(plane, baseline)
        self.assertIn("`gpt-5.6-sol` and `max`", baseline)
        self.assertIn("`opl_flow_context` is metadata", app_integration)
        self.assertIn("prompt body", app_integration)
        self.assertIn("only when fresh package projection says", app_integration)
        self.assertIn("Flow absence means omit the metadata", app_integration)

    def test_receipt_validator_accepts_one_reused_dashboard(self) -> None:
        result = validate_receipt(valid_receipt())

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["linear_projected_issue_count"], 8)
        self.assertEqual(result["registered_linear_project_count"], 1)
        self.assertEqual(result["paused_linear_issue_count"], 1)
        self.assertEqual(result["delivered_linear_comment_count"], 2)
        self.assertEqual(result["ignored_non_user_comment_count"], 1)
        self.assertEqual(
            result["duplicate_counts"],
            {"dashboard": 0, "bead": 0, "heartbeat": 0, "linear_issue": 0},
        )

    def test_receipt_validator_accepts_two_projects_on_one_supervisor(self) -> None:
        receipt = valid_receipt()
        receipt["supervisor"]["registered_linear_project_ids"].append("linear-ambient-ops")
        receipt["linear"]["registered_projects"].append(
            {
                "id": "linear-ambient-ops",
                "name": "Ambient Operations",
                "managed_by": "local_codex",
                "coverage_parity": "passed",
                "last_processed_comment_id": "ambient-comment-9",
            }
        )

        result = validate_receipt(receipt)

        self.assertEqual(result["registered_linear_project_count"], 2)
        self.assertEqual(receipt["heartbeat"]["match_count"], 1)

    def test_readme_and_discovery_surfaces_explain_explicit_start(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        readme_zh = README_ZH_PATH.read_text(encoding="utf-8")
        terminal_readback = TERMINAL_READBACK_PATH.read_text(encoding="utf-8")
        plugin = json.loads(PLUGIN_PATH.read_text(encoding="utf-8"))
        agent = AGENT_PATH.read_text(encoding="utf-8")

        for surface in (readme, readme_zh):
            with self.subTest(surface="readme"):
                self.assertIn("OPL Flow Supervisor", surface)
                self.assertIn("codex-paused", surface)
                self.assertIn("comment-ID", surface)
                self.assertIn("$opl-flow start", surface)
        self.assertIn("Installation deploys capability only", readme)
        self.assertIn("安装只部署能力", readme_zh)
        self.assertIn("registered Linear projects", terminal_readback)
        self.assertIn("comment-ID high-watermarks", terminal_readback)
        self.assertIn("onboard and supervise my complete Ledger", plugin["interface"]["defaultPrompt"])
        self.assertIn("onboard and supervise my complete Ledger", agent)

    def test_receipt_validator_rejects_duplicate_or_misbound_surfaces(self) -> None:
        mutations = (
            ("duplicate dashboard", lambda value: value["dashboard"].update(match_count=2)),
            ("duplicate Bead", lambda value: value["bead"].update(match_count=2)),
            ("wrong Bead link", lambda value: value["bead"].update(external_ref="codex://thread/other")),
            ("duplicate heartbeat", lambda value: value["heartbeat"].update(match_count=2)),
            ("cron workaround", lambda value: value["heartbeat"].update(kind="cron")),
            ("renamed supervisor", lambda value: value["heartbeat"].update(display_name="OPL Supervisor")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                receipt = copy.deepcopy(valid_receipt())
                mutate(receipt)
                with self.assertRaises(ValueError):
                    validate_receipt(receipt)

    def test_receipt_validator_requires_supervision_and_terminal_boundaries(self) -> None:
        mutations = (
            ("install side effect", lambda value: value.update(installation_side_effects="performed")),
            ("passive poll", lambda value: value["supervisor"].update(performs_adjustments=False)),
            ("missing decision", lambda value: value["supervisor"]["decisions"].remove("scope_correct")),
            ("second heartbeat policy", lambda value: value["supervisor"].update(single_heartbeat_for_registered_projects=False)),
            ("project registration drift", lambda value: value["supervisor"].update(registered_linear_project_ids=["other"])),
            ("no Dolt parity", lambda value: value["ledger"].update(parity="unknown")),
            ("partial Linear coverage", lambda value: value["linear"].update(projected_issue_count=7)),
            ("missing Linear Bead", lambda value: value["linear"].update(missing_bead_ids=["opl-8"])),
            ("duplicate Linear mapping", lambda value: value["linear"].update(duplicate_bead_ids=["opl-3"])),
            ("wrong hierarchy", lambda value: value["linear"].update(hierarchy_parity="failed")),
            ("wrong Linear authority", lambda value: value["linear"]["field_authority"]["linear_to_beads"].remove("cancel")),
            ("codex-ready required", lambda value: value["linear"]["execution_admission"].update(codex_ready="required")),
            ("paused dispatch", lambda value: value["linear"]["execution_admission"].update(dispatched_paused_issue_ids=["linear-issue-7"])),
            ("paused issue not reconciled", lambda value: value["linear"]["execution_admission"].update(reconciled_paused_issue_ids=[])),
            ("missing codex-paused", lambda value: value["linear"]["projected_fields"].remove("codex_paused")),
            ("missing comment cursor", lambda value: value["linear"]["registered_projects"][0].update(last_processed_comment_id="")),
            ("wrong comment route", lambda value: value["linear"]["comment_intake"].update(route="linear_search")),
            ("duplicate comment delivery", lambda value: value["linear"]["comment_intake"].update(duplicate_delivery_count=1)),
            ("comment loop", lambda value: value["linear"]["comment_intake"].update(non_user_comments_ignored=False)),
            ("missed comment", lambda value: value["linear"]["comment_intake"].update(delivered_comment_ids=["comment-43"])),
            ("duplicate comment id", lambda value: value["linear"]["comment_intake"].update(delivered_comment_ids=["comment-43", "comment-43"])),
            ("delivered Agent comment", lambda value: value["linear"]["comment_intake"].update(ignored_non_user_comment_ids=["comment-44"])),
            ("paused issue stops reconciliation", lambda value: value["linear"]["comment_intake"].update(paused_issue_reconciliation_continues=False)),
            ("paused issue stops comments", lambda value: value["linear"]["comment_intake"].update(paused_issue_comment_intake_continues=False)),
            ("early cursor advance", lambda value: value["linear"]["comment_intake"].update(cursor_advance="before_delivery")),
            ("Cloud delegate conflict", lambda value: value["linear"]["comment_intake"].update(cloud_delegate_conflict_count=1)),
            ("sensitive Linear field", lambda value: value["linear"].update(excluded_fields_absent=False)),
            ("bd Linear sync", lambda value: value["linear"].update(bd_linear_sync_used=True)),
            ("missing Ambient Ops", lambda value: value["ambient_ops"].update(registered=False)),
            ("Codex Cloud", lambda value: value["boundaries"].update(codex_cloud_used=True)),
            ("Cloud delegate", lambda value: value["boundaries"].update(cloud_delegate_used=True)),
            ("automatic archive", lambda value: value["boundaries"].update(automatic_archive_performed=True)),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                receipt = copy.deepcopy(valid_receipt())
                mutate(receipt)
                with self.assertRaises(ValueError):
                    validate_receipt(receipt)


if __name__ == "__main__":
    unittest.main()
