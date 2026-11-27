import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fleet import fleet_flow_baseline as baseline
from fleet import fleet_reconcile
from fleet.fleet_reconcile import reconcile_flow_experience_baseline


def reply(payload, code=0):
    return subprocess.CompletedProcess([], code, json.dumps(payload), "")


def error(code):
    return reply({"error": {"code": code}}, 2)


class V2FlowBaselineTests(TestCase):
    def test_registered_flow_reconciles_missing_carrier_with_pack_ensure(self):
        missing = {"status": "unavailable", "framework_managed": True,
                   "reason": "codex_plugin_missing_or_disabled"}
        current = {**missing, "status": "current", "reason": None, "failure_ids": []}
        for readback, expected in ((current, "repaired"), (missing, "repair_failed")):
            with (
                self.subTest(expected=expected),
                mock.patch.object(baseline, "read_v2_baseline", side_effect=[missing, readback]),
                mock.patch.object(fleet_reconcile, "run", return_value=reply({})) as command,
            ):
                receipt = reconcile_flow_experience_baseline(opl_command="/opt/opl")
                self.assertEqual(receipt["status"], expected)
                self.assertTrue(receipt["repair_attempted"])
                command.assert_called_once_with(
                    ["/opt/opl", "pack", "ensure", "opl-flow", "--json"],
                    check=False,
                    timeout=900,
                )

    def test_registered_flow_does_not_claim_repair_for_missing_baseline_skill(self):
        degraded = {
            "status": "degraded",
            "framework_managed": True,
            "repair_attempted": False,
            "reason": "baseline_capabilities_unavailable",
            "failure_ids": ["owner-skill"],
        }
        with (mock.patch.object(baseline, "read_v2_baseline", return_value=degraded),
              mock.patch.object(fleet_reconcile, "run") as command):
            receipt = reconcile_flow_experience_baseline(opl_command="/opt/opl")
        self.assertEqual(receipt["status"], "degraded")
        self.assertFalse(receipt["repair_attempted"])
        command.assert_not_called()

    def test_registered_and_native_only_flow_read_the_installed_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            native_root = root / "plugin"
            (native_root / "contracts").mkdir(parents=True)
            (native_root / "contracts/workflow-policy.json").write_text(json.dumps({
                "schema": "opl_flow_workflow_policy.v4",
                "package": {"id": "opl-flow", "version": "1.2.3"},
                "experience_baseline": [{"id": "test-flow-baseline-capability", "kind": "codex_skill",
                                         "readiness_adapter": "codex_skill_payload"}],
            }))
            skill = root / "skills/test-flow-baseline-capability/SKILL.md"
            skill.parent.mkdir(parents=True)
            for origin in (None, "opl", "external"):
                for ready in (False, True):
                    with self.subTest(origin=origin, ready=ready):
                        if ready:
                            skill.touch()
                        else:
                            skill.unlink(missing_ok=True)
                        plugin_id = "opl-flow@opl-local" if origin == "opl" else "opl-flow@opl-flow"
                        cli = reply({"installed": {"package_id": "opl-flow", "enabled": True, "version": "1.2.3",
                                                  "origin": origin, "install_path": str(native_root)}}) if origin else error("PACK_NOT_FOUND")
                        native = reply({"installed": [{"pluginId": plugin_id, "enabled": True, "installed": True,
                                                      "version": "1.2.3", "source": {"path": str(native_root)}}]})
                        with (mock.patch.object(baseline, "effective_codex_home", return_value=root),
                              mock.patch.object(baseline, "_probe", side_effect=[cli, native]) as calls):
                            receipt = reconcile_flow_experience_baseline(opl_command="opl")
                        self.assertEqual(receipt["status"], "current" if ready else "degraded")
                        self.assertEqual(receipt["framework_registered"], origin is not None)
                        self.assertEqual(receipt["framework_managed"], origin == "opl")
                        self.assertEqual(receipt["carrier_id"], plugin_id)
                        self.assertEqual(receipt["failure_ids"], [] if ready else ["test-flow-baseline-capability"])
                        self.assertFalse(receipt["repair_attempted"])
                        self.assertEqual(calls.call_args_list, [mock.call(["opl", "pack", "inspect", "opl-flow", "--json"]),
                                                               mock.call(["codex", "plugin", "list", "--json"])])

    def test_disabled_package_or_failed_inspection_do_not_inherit_native_status(self):
        for inspect, reason in [(reply({"installed": {"package_id": "opl-flow", "enabled": False}}),
                                 "framework_package_disabled"), (error("UNAVAILABLE"), "pack_inspect_unavailable")]:
            with self.subTest(reason=reason), mock.patch.object(baseline, "_probe", return_value=inspect) as probe:
                receipt = baseline.read_v2_baseline("opl", {"status": "unavailable"}, lambda _: ())
                self.assertEqual(receipt["reason"], reason)
                self.assertEqual(receipt["status"], "unavailable")
                probe.assert_called_once()

    def test_other_native_plugin_does_not_verify_flow(self):
        native = reply({"installed": [{"pluginId": "opl-flow@other", "enabled": True, "installed": True}]})
        with mock.patch.object(baseline, "_probe", side_effect=[error("PACK_NOT_FOUND"), native]):
            receipt = baseline.read_v2_baseline("opl", {"status": "unavailable"}, lambda _: ())
        self.assertEqual(receipt["reason"], "codex_plugin_missing_or_disabled")
