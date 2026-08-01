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
VALIDATOR_PATH = REPO_ROOT / "skills" / "opl-flow" / "scripts" / "validate_start_onboarding.py"

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
        },
        "supervisor": {
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
                "priority",
                "due",
                "codex_ready",
                "cancel",
                "short_blocker",
                "short_result",
                "links",
            ],
            "field_authority": {
                "linear_to_beads": ["human_intent", "priority", "due", "codex_ready", "cancel"],
                "beads_to_linear": ["execution_state", "blocker", "result"],
            },
            "excluded_fields_absent": True,
            "terminal_readback": "passed",
            "bd_linear_sync_used": False,
        },
        "boundaries": {
            "task_ssot": "beads_dolt",
            "codex_cloud_used": False,
            "automatic_archive_performed": False,
        },
    }


class OplFlowOnboardingTests(unittest.TestCase):
    def test_contract_declares_native_idempotent_supervisor_route(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(contract["action"], "start")
        self.assertEqual(contract["defaults"]["execution_environment"], "local")
        self.assertEqual(contract["defaults"]["cadence"], "hourly")
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
                "linear_to_beads": ["human_intent", "priority", "due", "codex_ready", "cancel"],
                "beads_to_linear": ["execution_state", "blocker", "result"],
            },
        )
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
        self.assertEqual(
            result["duplicate_counts"],
            {"dashboard": 0, "bead": 0, "heartbeat": 0, "linear_issue": 0},
        )

    def test_receipt_validator_rejects_duplicate_or_misbound_surfaces(self) -> None:
        mutations = (
            ("duplicate dashboard", lambda value: value["dashboard"].update(match_count=2)),
            ("duplicate Bead", lambda value: value["bead"].update(match_count=2)),
            ("wrong Bead link", lambda value: value["bead"].update(external_ref="codex://thread/other")),
            ("duplicate heartbeat", lambda value: value["heartbeat"].update(match_count=2)),
            ("cron workaround", lambda value: value["heartbeat"].update(kind="cron")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                receipt = copy.deepcopy(valid_receipt())
                mutate(receipt)
                with self.assertRaises(ValueError):
                    validate_receipt(receipt)

    def test_receipt_validator_requires_supervision_and_terminal_boundaries(self) -> None:
        mutations = (
            ("passive poll", lambda value: value["supervisor"].update(performs_adjustments=False)),
            ("missing decision", lambda value: value["supervisor"]["decisions"].remove("scope_correct")),
            ("no Dolt parity", lambda value: value["ledger"].update(parity="unknown")),
            ("partial Linear coverage", lambda value: value["linear"].update(projected_issue_count=7)),
            ("missing Linear Bead", lambda value: value["linear"].update(missing_bead_ids=["opl-8"])),
            ("duplicate Linear mapping", lambda value: value["linear"].update(duplicate_bead_ids=["opl-3"])),
            ("wrong hierarchy", lambda value: value["linear"].update(hierarchy_parity="failed")),
            ("wrong Linear authority", lambda value: value["linear"]["field_authority"]["linear_to_beads"].remove("cancel")),
            ("sensitive Linear field", lambda value: value["linear"].update(excluded_fields_absent=False)),
            ("bd Linear sync", lambda value: value["linear"].update(bd_linear_sync_used=True)),
            ("Codex Cloud", lambda value: value["boundaries"].update(codex_cloud_used=True)),
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
