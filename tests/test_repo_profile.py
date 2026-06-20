from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import repo_profile


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "repo_profile.py"


class RepoProfileTests(unittest.TestCase):
    def test_check_reports_missing_profile_and_repo_guidance_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            result = repo_profile.check_repo(repo)

            self.assertFalse(result["ok"])
            self.assertEqual(result["mode"], "check")
            self.assertIn("contracts/opl-native-profile.json", result["missing"])
            self.assertIn("AGENTS.md", result["missing"])
            self.assertIn("TASTE.md", result["missing"])
            self.assertFalse((repo / "contracts" / "opl-native-profile.json").exists())
            self.assertFalse((repo / "AGENTS.md").exists())
            self.assertFalse((repo / "TASTE.md").exists())

    def test_sync_dry_run_reports_planned_changes_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "AGENTS.md").write_text("custom agents\n", encoding="utf-8")
            (repo / "TASTE.md").write_text("custom taste\n", encoding="utf-8")

            result = repo_profile.sync_repo(repo, apply=False)

            self.assertFalse(result["ok"])
            self.assertEqual(result["mode"], "sync")
            self.assertFalse(result["apply"])
            self.assertEqual(
                sorted(item["path"] for item in result["planned_changes"]),
                ["AGENTS.md", "TASTE.md", "contracts/opl-native-profile.json"],
            )
            self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), "custom agents\n")
            self.assertEqual((repo / "TASTE.md").read_text(encoding="utf-8"), "custom taste\n")
            self.assertFalse((repo / "contracts" / "opl-native-profile.json").exists())

    def test_sync_apply_creates_profile_and_managed_blocks_preserving_repo_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "AGENTS.md").write_text("# Repo Agents\n\nLocal rule.\n", encoding="utf-8")
            (repo / "TASTE.md").write_text("# Repo Taste\n\nLocal preference.\n", encoding="utf-8")
            (repo / "contracts").mkdir()
            (repo / "contracts" / "opl-native-profile.json").write_text(
                json.dumps({"repo_overlay": {"owner": "local"}}, indent=2) + "\n",
                encoding="utf-8",
            )

            result = repo_profile.sync_repo(repo, apply=True)

            self.assertTrue(result["ok"])
            self.assertTrue(result["apply"])
            profile = json.loads((repo / "contracts" / "opl-native-profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["flow_profile"], repo_profile.DEFAULT_FLOW_PROFILE)
            self.assertEqual(profile["managed_by_plugins"]["opl-flow"]["version"], repo_profile.FLOW_VERSION)
            self.assertEqual(profile["repo_overlay"], {"owner": "local"})
            self.assertIn(
                {"path": "AGENTS.md", "management": "managed_block", "kind": "repo_agent_instructions"},
                profile["managed_by_plugins"]["opl-flow"]["managed_surfaces"],
            )
            self.assertIn(
                {"path": "TASTE.md", "management": "managed_block", "kind": "maintenance_preferences"},
                profile["managed_by_plugins"]["opl-flow"]["managed_surfaces"],
            )

            agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            taste = (repo / "TASTE.md").read_text(encoding="utf-8")
            self.assertIn("Local rule.", agents)
            self.assertIn(repo_profile.MANAGED_START, agents)
            self.assertIn("contracts/opl-native-profile.json", agents)
            self.assertIn("Local preference.", taste)
            self.assertIn(repo_profile.MANAGED_START, taste)
            self.assertIn("contracts/opl-native-profile.json", taste)

            second = repo_profile.sync_repo(repo, apply=True)
            self.assertTrue(second["ok"])
            self.assertEqual(second["planned_changes"], [])
            self.assertEqual(agents, (repo / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertEqual(taste, (repo / "TASTE.md").read_text(encoding="utf-8"))

    def test_user_profile_templates_preserve_root_cause_supervision(self) -> None:
        agents = (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")
        taste = (REPO_ROOT / "templates" / "TASTE.md").read_text(encoding="utf-8")

        self.assertIn("本因诊断", agents)
        self.assertIn("blocker-to-owner map", agents)
        self.assertIn("本因诊断优先于状态复述", taste)

    def test_cli_defaults_to_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo-root", tmp],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "check")
            self.assertFalse(payload["apply"])


if __name__ == "__main__":
    unittest.main()
