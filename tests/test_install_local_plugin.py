from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import install_local_plugin


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstallLocalPluginTests(unittest.TestCase):
    def test_install_profile_writes_fresh_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex"

            result = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            self.assertEqual(result["status"], "installed")
            self.assertTrue((codex_home / "AGENTS.md").exists())
            self.assertTrue((codex_home / "TASTE.md").exists())
            self.assertTrue((codex_home / "prompts" / "planner.md").exists())

    def test_install_profile_does_not_overwrite_existing_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex"
            codex_home.mkdir()
            existing = "custom user profile\n"
            (codex_home / "AGENTS.md").write_text(existing, encoding="utf-8")

            result = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            self.assertEqual(result["status"], "requires_codex_semantic_merge")
            self.assertEqual((codex_home / "AGENTS.md").read_text(encoding="utf-8"), existing)
            self.assertEqual(result["changed"], [])
            packet = Path(result["merge_packet"])
            self.assertTrue((packet / "existing" / "AGENTS.md").exists())
            self.assertTrue((packet / "candidate" / "AGENTS.md").exists())
            self.assertTrue((packet / "candidate" / "profile" / "manifest.json").exists())
            self.assertTrue((packet / "prompt.md").exists())
            plan = json.loads((packet / "merge-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["script_merge_policy"], "disabled")
            self.assertEqual(plan["status"], "requires_codex_semantic_merge")

    def test_install_profile_current_profile_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex"
            first = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            second = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            self.assertEqual(first["status"], "installed")
            self.assertEqual(second["status"], "current")
            self.assertEqual(second["changed"], [])

    def test_verify_reports_merge_required_for_existing_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex"
            plugins_dir = root / "plugins"
            marketplace = root / "marketplace.json"
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text("custom user profile\n", encoding="utf-8")

            install_result = install_local_plugin.install(
                REPO_ROOT,
                plugins_dir,
                marketplace,
                codex_home,
                profile=True,
            )
            verify_result = install_local_plugin.verify(
                REPO_ROOT,
                plugins_dir,
                marketplace,
                codex_home,
                profile=True,
            )

            self.assertEqual(install_result["profile"]["status"], "requires_codex_semantic_merge")
            self.assertFalse(verify_result["ok"])
            self.assertEqual(verify_result["profile_status"], "merge_required")
            self.assertEqual(verify_result["profile_merge_packet"], install_result["profile"]["merge_packet"])
            self.assertEqual((codex_home / "AGENTS.md").read_text(encoding="utf-8"), "custom user profile\n")


if __name__ == "__main__":
    unittest.main()
