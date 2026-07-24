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
    def test_check_reports_missing_profile_without_requiring_repo_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            result = repo_profile.check_repo(repo)

            self.assertFalse(result["ok"])
            self.assertEqual(result["mode"], "check")
            self.assertIn("contracts/opl-native-profile.json", result["missing"])
            self.assertFalse((repo / "contracts" / "opl-native-profile.json").exists())
            self.assertFalse((repo / "AGENTS.md").exists())

    def test_sync_dry_run_reports_planned_changes_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "AGENTS.md").write_text("custom agents\n", encoding="utf-8")

            result = repo_profile.sync_repo(repo, apply=False)

            self.assertFalse(result["ok"])
            self.assertEqual(result["mode"], "sync")
            self.assertFalse(result["apply"])
            self.assertEqual(
                sorted(item["path"] for item in result["planned_changes"]),
                ["contracts/opl-native-profile.json"],
            )
            self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), "custom agents\n")
            self.assertFalse((repo / "contracts" / "opl-native-profile.json").exists())

    def test_sync_apply_creates_profile_without_managing_repo_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "AGENTS.md").write_text("# Repo Agents\n\nLocal rule.\n", encoding="utf-8")
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
            self.assertEqual(profile["managed_by_plugins"]["opl-flow"]["managed_surfaces"], [])

            agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(agents, "# Repo Agents\n\nLocal rule.\n")

            second = repo_profile.sync_repo(repo, apply=True)
            self.assertTrue(second["ok"])
            self.assertEqual(second["planned_changes"], [])
            self.assertEqual(agents, (repo / "AGENTS.md").read_text(encoding="utf-8"))

    def test_sync_removes_legacy_managed_block_and_preserves_repo_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "contracts").mkdir()
            (repo / "contracts" / "opl-native-profile.json").write_text(
                json.dumps(repo_profile.desired_profile(None), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (repo / "AGENTS.md").write_text(
                "# Repo Agents\n\nLocal rule.\n\n"
                f"{repo_profile.LEGACY_MANAGED_START}\n"
                "stale pointer\n"
                f"{repo_profile.LEGACY_MANAGED_END}\n\n"
                "<!-- CODEGRAPH_START -->\nCodeGraph\n<!-- CODEGRAPH_END -->\n",
                encoding="utf-8",
            )

            result = repo_profile.sync_repo(repo, apply=True)

            self.assertTrue(result["ok"])
            agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(
                agents,
                "# Repo Agents\n\nLocal rule.\n\n"
                "<!-- CODEGRAPH_START -->\nCodeGraph\n<!-- CODEGRAPH_END -->\n",
            )

    def test_user_profile_template_is_minimal_and_bootstraps_codegraph(self) -> None:
        agents = (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")
        taste = (REPO_ROOT / "templates" / "TASTE.md").read_text(encoding="utf-8")

        self.assertIn("先给结论", agents)
        self.assertIn("开发默认 progress-first", agents)
        self.assertIn("$develop-and-deliver", agents)
        self.assertIn("$architect-and-simplify", agents)
        self.assertIn("$task-mode-gate", agents)
        self.assertIn("codegraph init .", agents)
        self.assertNotIn("## ", agents)
        self.assertNotIn("## Guardrails", agents)
        self.assertNotIn("## Ops And Authority Core", agents)
        self.assertIn("可验收终态优先", taste)
        self.assertIn("开发与生产分离", taste)
        self.assertIn("进展优先", taste)
        self.assertIn("AI 判断，机器守界", taste)
        self.assertIn("声明与证据同级", taste)
        self.assertIn("简单、精准、规则克制", taste)
        self.assertIn("非运行时治理参考", taste)
        self.assertIn("不宣称被自动编译、自动注入或自动生效", taste)

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
