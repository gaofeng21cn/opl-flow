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

    def test_prepare_updates_current_framework_projection_without_legacy_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            owner_root = root / "owner"
            framework_root = root / "framework"
            owner_root.mkdir()
            package_path = (
                framework_root
                / "contracts/opl-framework/packages/opl-flow.json"
            )
            package_path.parent.mkdir(parents=True)
            release.write_json(
                package_path,
                {
                    "package_id": "opl-flow",
                    "version": "0.1.48",
                    "source_repo": "https://github.com/gaofeng21cn/opl-flow.git",
                    "codex_surface": {
                        "plugin_payload_manifest_url": "payloads/opl-flow-0.1.48.json",
                        "carrier_source_commit": "old-commit",
                    },
                },
            )
            payload_path = package_path.parent / "payloads/opl-flow-0.1.49.json"

            def generate_payload(
                argv: list[str], **_: object
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(Path(argv[1]).name, "first-party-package-payload.mjs")
                payload_path.parent.mkdir(parents=True)
                release.write_json(
                    payload_path,
                    {
                        "package_id": "opl-flow",
                        "package_version": "0.1.49",
                        "source_commit": "new-commit",
                    },
                )
                return subprocess.CompletedProcess(argv, 0, "", "")

            args = argparse.Namespace(
                package_id="opl-flow",
                owner_root=str(owner_root),
                framework_root=str(framework_root),
            )
            owner_manifest = {
                "package_id": "opl-flow",
                "version": "0.1.49",
                "source_repo": "https://github.com/gaofeng21cn/opl-flow.git",
            }
            with (
                patch.object(
                    release,
                    "require_owner_release",
                    return_value=(owner_manifest, "0.1.49", "new-commit"),
                ),
                patch.object(release, "repo_slug", return_value="gaofeng21cn/opl-flow"),
                patch.object(release, "command", side_effect=generate_payload),
            ):
                result = release.prepare(args)

            package = release.read_json(package_path)
            self.assertEqual(package["version"], "0.1.49")
            self.assertEqual(
                package["codex_surface"]["plugin_payload_manifest_url"],
                "payloads/opl-flow-0.1.49.json",
            )
            self.assertEqual(
                package["codex_surface"]["carrier_source_commit"], "new-commit"
            )
            self.assertEqual(
                result["updated_files"], [str(package_path), str(payload_path)]
            )
            self.assertFalse(
                (
                    framework_root
                    / "contracts/opl-framework/bundled-full-runtime-package-catalog.json"
                ).exists()
            )

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

    def test_publish_approves_only_the_exact_release_environment(self) -> None:
        pending = [{
            "environment": {"id": 42, "name": "release-stable"},
            "current_user_can_approve": True,
        }]
        with patch.object(release, "command_json", side_effect=[pending, [{"id": 7}]]) as command:
            result = release.approve_release_environment("owner/repo", 123, "request-1")

        self.assertEqual(
            result,
            {"status": "approved", "environment": "release-stable", "environment_id": 42},
        )
        self.assertEqual(
            command.call_args_list[1].args[0],
            [
                "gh", "api", "--method", "POST",
                "repos/owner/repo/actions/runs/123/pending_deployments",
                "-F", "environment_ids[]=42",
                "-f", "state=approved",
                "-f", "comment=Authorized OPL Package publication request-1",
            ],
        )

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
                if argv[1:3] == ["packages", "update"]:
                    return {
                        "opl_agent_package_update": {
                            "status": "updated",
                            "target_version": "0.1.40",
                            "observed_version": "0.1.40",
                            "release_catalog_digest": "sha256:digest",
                        }
                    }
                return {
                    "opl_agent_package_status": {
                        "status": "available",
                        "installed_package_count": 1,
                        "operational_ready": True,
                        "launch_state": "ready",
                        "managed_policy_currentness": {"status": "current"},
                    }
                }

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
            self.assertEqual(result["package_status"]["operational_ready"], True)
            self.assertNotIn("opl_agent_package_status", result["package_status"])


if __name__ == "__main__":
    unittest.main()
