from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import fleet_inventory as inventory  # noqa: E402


def fixture() -> dict[str, object]:
    return {
        "schema": "codex_fleet_inventory.v1",
        "node_id": "fictional-node",
        "observed_at": "2026-07-27T00:00:00+00:00",
        "host": {
            "system": "darwin",
            "os_name": "macOS",
            "os_version": "26.0",
            "build": "25A1",
            "manufacturer": "Example",
            "model": "Example Computer",
            "model_identifier": "Example1,1",
        },
        "execution": {
            "kind": "native",
            "os_name": "macOS",
            "os_version": "26.0",
            "kernel": "25.0.0",
            "architecture": "arm64",
        },
        "hardware": {
            "cpu_model": "Example CPU",
            "logical_cores": 8,
            "memory_bytes": 32 * 1024**3,
            "gpus": [],
        },
        "storage": {
            "scope": "execution-home",
            "total_bytes": 1024**4,
            "free_bytes": 512 * 1024**3,
        },
        "baseline": {
            "codex": {"ready": True, "kind": "mac_app", "version": "1.0"},
            "ssh": {"installed": True, "listening": None},
            "tailscale": {
                "installed": True,
                "online": True,
                "version": "1.84",
                "owner": "native",
            },
        },
        "software": {
            "git": {"present": True, "version": "git version 2.50.0"}
        },
        "specialized_software": [],
    }


class FleetInventoryTests(unittest.TestCase):
    def test_optional_command_timeout_fails_closed(self) -> None:
        completed = inventory.subprocess.CompletedProcess(["owner-tool"], 0, "", "")
        with mock.patch.object(inventory, "run", return_value=completed) as command:
            self.assertTrue(
                inventory.command_succeeds(["owner-tool"], timeout_seconds=5)
            )
        command.assert_called_once_with(["owner-tool"], timeout_seconds=5)

        with mock.patch.object(
            inventory,
            "run",
            side_effect=inventory.subprocess.TimeoutExpired(["owner-tool"], 5),
        ):
            self.assertFalse(
                inventory.command_succeeds(["owner-tool"], timeout_seconds=5)
            )

    def test_mac_power_reports_ac_attached_battery(self) -> None:
        completed = inventory.subprocess.CompletedProcess(
            ["pmset", "-g", "batt"],
            0,
            "Now drawing from 'AC Power'\n"
            " -InternalBattery-0\t80%; AC attached; not charging present: true\n",
            "",
        )
        with mock.patch.object(inventory, "run", return_value=completed):
            result = inventory.mac_power()
        self.assertEqual(
            result,
            {
                "source": "ac",
                "battery_present": True,
                "charging": False,
                "percent": 80,
            },
        )

    def test_scheduling_enforces_ac_disk_and_busy_gates(self) -> None:
        registry = {
            "nodes": {
                "fictional-node": {
                    "scheduling": {
                        "requires_ac": True,
                        "min_free_gb": 100,
                        "occupancy_required": True,
                        "idle_threshold_seconds": 900,
                        "preferred_for": ["mac-gui"],
                    }
                }
            }
        }
        capabilities = {
            "power": {"source": "battery"},
            "gui": {"interactive_session": True, "idle_seconds": 30},
            "workload": {"busy": False, "thermal_state": "nominal"},
        }
        result = inventory.scheduling_status(
            "fictional-node",
            registry,
            capabilities,
            200 * 1024**3,
        )
        self.assertFalse(result["power_ok"])
        self.assertTrue(result["interactive_busy"])
        self.assertFalse(result["eligible"])
        self.assertNotIn("preemptible", result)
        self.assertNotIn("reservation_state", result)

        capabilities["power"]["source"] = "ac"
        capabilities["gui"]["interactive_session"] = False
        capabilities["gui"]["idle_seconds"] = None
        capabilities["workload"]["busy"] = True
        capabilities["workload"]["thermal_state"] = "warning"
        result = inventory.scheduling_status(
            "fictional-node",
            registry,
            capabilities,
            50 * 1024**3,
        )
        self.assertFalse(result["storage_ok"])
        self.assertTrue(result["busy"])
        self.assertFalse(result["thermal_ok"])
        self.assertFalse(result["eligible"])

        capabilities["workload"]["busy"] = False
        capabilities["workload"]["thermal_state"] = "nominal"
        result = inventory.scheduling_status(
            "fictional-node",
            registry,
            capabilities,
            200 * 1024**3,
        )
        self.assertTrue(result["eligible"])

    def test_scheduling_separates_gui_session_from_live_occupancy(self) -> None:
        registry = {
            "nodes": {
                "fictional-node": {
                    "scheduling": {
                        "requires_ac": False,
                        "min_free_gb": 10,
                        "occupancy_required": True,
                        "idle_threshold_seconds": 900,
                        "preferred_for": ["mac-gui"],
                    }
                }
            }
        }
        capabilities = {
            "power": {"source": "ac"},
            "gui": {"interactive_session": True, "idle_seconds": 1200},
            "workload": {"busy": False, "thermal_state": "nominal"},
        }
        idle = inventory.scheduling_status(
            "fictional-node",
            registry,
            capabilities,
            100 * 1024**3,
        )
        self.assertTrue(idle["interactive_session"])
        self.assertFalse(idle["interactive_busy"])
        self.assertTrue(idle["eligible"])

        capabilities["gui"]["idle_seconds"] = 30
        recent_input = inventory.scheduling_status(
            "fictional-node",
            registry,
            capabilities,
            100 * 1024**3,
        )
        self.assertTrue(recent_input["interactive_busy"])
        self.assertFalse(recent_input["eligible"])

        capabilities["gui"]["idle_seconds"] = None
        unknown = inventory.scheduling_status(
            "fictional-node",
            registry,
            capabilities,
            100 * 1024**3,
        )
        self.assertIsNone(unknown["interactive_busy"])
        self.assertFalse(unknown["eligible"])

    def test_mac_hid_idle_seconds_parses_windowserver_assertion(self) -> None:
        completed = inventory.subprocess.CompletedProcess(
            ["pmset"],
            0,
            "   UserIsActive                   1\n"
            "   pid 433(WindowServer): 00:20:34 UserIsActive named: input\n",
            "",
        )
        with mock.patch.object(inventory, "run", return_value=completed):
            self.assertEqual(inventory.mac_hid_idle_seconds(), 1234)

    def test_nvidia_probe_is_optional_when_owner_command_is_absent(self) -> None:
        with (
            mock.patch.object(inventory.shutil, "which", return_value=None),
            mock.patch.object(inventory.Path, "is_file", return_value=False),
            mock.patch.object(inventory, "run") as command,
        ):
            result = inventory.nvidia_gpus()
        self.assertEqual(result, [])
        command.assert_not_called()

    def test_validation_rejects_paths_and_identity_fields(self) -> None:
        leaked_path = copy.deepcopy(fixture())
        leaked_path["host"]["model"] = "/Users/owner/private"
        with self.assertRaisesRegex(inventory.InventoryError, "sensitive"):
            inventory.validate_inventory(leaked_path)

        leaked_serial = copy.deepcopy(fixture())
        leaked_serial["hardware"]["serial_number"] = "secret"
        with self.assertRaisesRegex(inventory.InventoryError, "forbidden"):
            inventory.validate_inventory(leaked_serial)

    def test_validation_accepts_legacy_and_enriched_inventory(self) -> None:
        legacy = fixture()
        self.assertEqual(inventory.validate_inventory(legacy), legacy)
        enriched = copy.deepcopy(legacy)
        enriched["capabilities"] = {
            "power": {"source": "ac"},
            "workload": {"busy": False},
        }
        enriched["scheduling"] = {
            "requires_ac": False,
            "power_ok": True,
            "preferred_for": [],
            "occupancy_required": True,
            "idle_threshold_seconds": 900,
            "interactive_session": True,
            "interactive_busy": False,
            "idle_seconds": 1200,
            "busy": False,
            "storage_ok": True,
            "thermal_ok": True,
            "eligible": True,
        }
        self.assertEqual(inventory.validate_inventory(enriched), enriched)

    def test_versions_are_allowlisted_and_missing_tools_are_explicit(self) -> None:
        completed = inventory.subprocess.CompletedProcess(
            ["git", "--version"], 0, "git version 2.50.0\n", ""
        )
        with (
            mock.patch.object(inventory.shutil, "which", side_effect=["/usr/bin/git", None]),
            mock.patch.object(inventory, "run", return_value=completed),
        ):
            result = inventory.software_versions(["git", "docker"])
        self.assertTrue(result["git"]["present"])
        self.assertFalse(result["docker"]["present"])
        with self.assertRaisesRegex(inventory.InventoryError, "unsupported"):
            inventory.software_versions(["everything-installed"])

    def test_versions_support_homebrew_as_the_package_manager_owner(self) -> None:
        completed = inventory.subprocess.CompletedProcess(
            ["brew", "--version"], 0, "Homebrew 4.6.0\n", ""
        )
        with (
            mock.patch.object(inventory.shutil, "which", return_value="/opt/homebrew/bin/brew"),
            mock.patch.object(inventory, "run", return_value=completed) as command,
        ):
            result = inventory.software_versions(["brew"])
        self.assertEqual(result["brew"], {"present": True, "version": "Homebrew 4.6.0"})
        command.assert_called_once_with(["/opt/homebrew/bin/brew", "--version"])

    def test_versions_include_owner_installed_user_bin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / ".local/bin/codegraph"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            completed = inventory.subprocess.CompletedProcess(
                [str(executable), "--version"], 0, "1.5.0\n", ""
            )
            with (
                mock.patch.object(inventory.Path, "home", return_value=Path(temporary)),
                mock.patch.object(inventory.shutil, "which", return_value=None),
                mock.patch.object(inventory, "run", return_value=completed) as command,
            ):
                result = inventory.software_versions(["codegraph"])
        self.assertEqual(result["codegraph"], {"present": True, "version": "1.5.0"})
        command.assert_called_once_with([str(executable), "--version"])

    def test_wsl_remote_control_accepts_normalized_task_principal(self) -> None:
        captured: list[str] = []

        def read_status(script: str) -> dict[str, bool]:
            captured.append(script)
            return {"startup_configured": True, "running": True}

        with mock.patch.object(inventory, "powershell_json", side_effect=read_status):
            result = inventory.remote_control_status(True)

        self.assertEqual(result, {"startup_configured": True, "running": True})
        script = captured[0]
        self.assertIn('$leaf=@($user -split "\\\\")[-1]', script)
        self.assertIn('$taskUser -notmatch "[\\\\@]"', script)
        self.assertIn("$logon -and $principal -and", script)
        self.assertNotIn("$task.Principal.UserId -ieq $user", script)

    def test_specialized_software_reports_only_approved_matches(self) -> None:
        installed = [
            {"name": "Fan Control", "version": "V230"},
            {"name": "Unrelated Private App", "version": "9"},
        ]
        definitions = [
            {
                "id": "gpu-fan-management",
                "purpose": "GPU fan and thermal management",
                "windows_display_name_patterns": ["Fan Control"],
            }
        ]
        with mock.patch.object(inventory, "powershell_json", return_value=installed):
            result = inventory.specialized_software(definitions, True)
        self.assertEqual(
            json.loads(json.dumps(result)),
            [
                {
                    "id": "gpu-fan-management",
                    "purpose": "GPU fan and thermal management",
                    "name": "Fan Control",
                    "version": "V230",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
