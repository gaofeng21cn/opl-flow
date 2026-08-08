from __future__ import annotations

import argparse
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "opl-flow" / "scripts" / "package_release.py"
SPEC = importlib.util.spec_from_file_location("package_release", SCRIPT_PATH)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PackageReleaseTests(unittest.TestCase):
    def test_repo_slug_accepts_https_scp_and_github_ssh_port(self) -> None:
        remotes = {
            "https://github.com/gaofeng21cn/opl-flow.git": "gaofeng21cn/opl-flow",
            "git@github.com:gaofeng21cn/opl-flow.git": "gaofeng21cn/opl-flow",
            "ssh://git@ssh.github.com:443/gaofeng21cn/one-person-lab.git": (
                "gaofeng21cn/one-person-lab"
            ),
        }
        for remote, expected in remotes.items():
            with self.subTest(remote=remote), patch.object(
                release, "git_value", return_value=remote
            ):
                self.assertEqual(release.repo_slug(Path("/fixture")), expected)

    def test_latest_stable_absence_is_distinct_from_registry_failure(self) -> None:
        missing = subprocess.CompletedProcess(
            ["oras"], 1, "", "Error response: manifest unknown"
        )
        with patch.object(release, "command", return_value=missing):
            self.assertEqual(release.latest_stable_predecessor("ghcr.io/x/y"), "none")

        failure = subprocess.CompletedProcess(["oras"], 1, "", "connection reset")
        with patch.object(release, "command", return_value=failure):
            with self.assertRaisesRegex(release.ReleaseError, "cannot read"):
                release.latest_stable_predecessor("ghcr.io/x/y")

    def test_profile_delta_reports_merge_without_writing_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            user_path = Path(temporary) / "AGENTS.md"
            user_path.write_text("user override\n", encoding="utf-8")
            result = release.profile_delta(
                ("old", b"old default\n"),
                ("new", b"new default\n"),
                user_path,
            )
            self.assertEqual(result["status"], "profile_merge_required")
            self.assertTrue(result["profile_merge_required"])
            self.assertIn("-old default", result["default_profile_diff"])
            self.assertEqual(user_path.read_text(encoding="utf-8"), "user override\n")
            self.assertFalse(result["automatic_write_performed"])

    def test_activate_delegates_marketplace_refresh_to_one_framework_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "installed"
            for skill_id in ("opl-flow", "develop-and-deliver"):
                path = source / "skills" / skill_id
                path.mkdir(parents=True)
                (path / "SKILL.md").write_text(f"# {skill_id}\n", encoding="utf-8")
            package_path = root / "contracts/opl-framework/packages/opl-flow.json"
            package_path.parent.mkdir(parents=True)
            release.write_json(
                package_path,
                {
                    "package_id": "opl-flow",
                    "version": "0.1.40",
                    "codex_surface": {
                        "required_skill_ids": ["opl-flow", "develop-and-deliver"],
                        "configured_codex_plugin_carrier": {
                            "plugin_selector": "opl-flow@opl-flow-local"
                        },
                    },
                },
            )
            before = {
                "pluginId": "opl-flow@opl-flow-local",
                "version": "0.1.39",
                "enabled": True,
                "source": {"path": str(source)},
            }
            after = {**before, "version": "0.1.40"}
            calls: list[list[str]] = []

            def command_json(argv: list[str], **_: object) -> dict[str, object]:
                calls.append(argv)
                return {"status": "ok"}

            args = argparse.Namespace(
                package_id="opl-flow",
                framework_root=str(root),
                codex_bin="codex",
                opl_bin="opl",
                user_profile=str(root / "AGENTS.md"),
                timeout=30,
            )
            with (
                patch.object(release, "plugin_entry", side_effect=[before, after]),
                patch.object(release, "installed_profile", return_value=(None, None)),
                patch.object(release, "command_json", side_effect=command_json),
            ):
                result = release.activate(args)

            self.assertEqual(
                calls,
                [
                    ["opl", "packages", "update", "opl-flow", "--json"],
                    ["opl", "packages", "status", "--package-id", "opl-flow", "--json"],
                ],
            )
            self.assertEqual(result["status"], "installed_and_read_back")
            self.assertTrue(result["fresh_discovery_required"])
            self.assertEqual(result["missing_skill_ids"], [])


if __name__ == "__main__":
    unittest.main()
